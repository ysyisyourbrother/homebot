"""Gateway startup for homebot."""

import asyncio
import os
import sys
import termios
import traceback
import tty
from pathlib import Path

from loguru import logger

from homebot.config.schema import Config
from homebot.providers.base import GenerationSettings
from homebot.providers.openai_compat_provider import OpenAICompatProvider
from homebot.providers.registry import find_by_name
from homebot.utils.helpers import sync_workspace_templates


def _make_provider(config: Config):
    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    spec = find_by_name(provider_name) if provider_name else None

    if not p or not p.api_key:
        print("Error: No API key configured.")
        print("Set one in ~/.homebot/config.json under providers section")
        raise SystemExit(1)

    provider = OpenAICompatProvider(
        api_key=p.api_key,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers,
        spec=spec,
    )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


def _load_runtime_config(config: str | None = None, workspace: str | None = None) -> Config:
    from homebot.config.loader import load_config, resolve_config_env_vars, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            print(f"Error: Config file not found: {config_path}")
            raise SystemExit(1)
        set_config_path(config_path)
        print(f"Using config: {config_path}")

    try:
        loaded = resolve_config_env_vars(load_config(config_path))
    except ValueError as e:
        print(f"Error: {e}")
        raise SystemExit(1)
    _warn_deprecated_config_keys(config_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


def _warn_deprecated_config_keys(config_path: Path | None) -> None:
    import json

    from homebot.config.loader import get_config_path

    path = config_path or get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if "memoryWindow" in raw.get("agents", {}).get("defaults", {}):
        print("Hint: `memoryWindow` in your config is no longer used and can be safely removed.")


def run(config: Config, *, port: int | None = None) -> None:
    """Start the homebot gateway."""
    from homebot.agent.loop import AgentLoop
    from homebot.agent.tools.browser import BrowserTool
    from homebot.bus.queue import MessageBus
    from homebot.channels.manager import ChannelManager
    from homebot.cron.browser_refresh import register_browser_refresh
    from homebot.cron.service import CronService
    from homebot.cron.types import CronJob
    from homebot.session.manager import SessionManager

    gateway_port = port if port is not None else config.gateway.port
    gateway_host = config.gateway.host
    print(f"🏠 Gateway started on port {gateway_port}.")
    sync_workspace_templates(config.workspace_path)
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path, bus=bus)

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_config=config.tools.web,
        web_search_config=config.tools.web_search,
        context_block_limit=config.agents.defaults.context_block_limit,
        max_tool_result_chars=config.agents.defaults.max_tool_result_chars,
        provider_retry_mode=config.agents.defaults.provider_retry_mode,
        exec_config=config.tools.exec,
        browser_config=config.tools.browser,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        disabled_skills=config.agents.defaults.disabled_skills,
        tools_config=config.tools,
        channels_config=config.channels,
        timezone=config.agents.defaults.timezone,
        unified_session=config.agents.defaults.unified_session,
    )

    async def on_cron_job(job: CronJob) -> str | None:
        from homebot.agent.tools.message import MessageTool

        reminder_note = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )

        async def _silent(*_args, **_kwargs):
            pass

        resp = await agent.process_direct(
            reminder_note,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "direct",
            chat_id=job.payload.to or "direct",
            on_progress=_silent,
            ephemeral=True,
        )

        response = resp.content if resp else ""

        message_tool = agent.tools.get("message")
        if job.payload.deliver and isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response

        if job.payload.deliver and job.payload.to and response:
            from homebot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "direct",
                chat_id=job.payload.to,
                content=response,
            ))
        return response

    cron.on_job = on_cron_job

    browser_tool = agent.tools.get("browser")
    if isinstance(browser_tool, BrowserTool):
        refresh_config = config.tools.browser.session_refresh
        register_browser_refresh(
            cron,
            browser_tool,
            refresh_config.urls,
            refresh_config.interval_hours,
        )

    channels = ChannelManager(config, bus, session_manager=session_manager)
    agent.set_cancel_callback(channels.cancel_active_interactions)

    async def _watch_escape() -> None:
        if not sys.stdin.isatty():
            await asyncio.Future()

        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
        was_blocking = os.get_blocking(fd)
        event_loop = asyncio.get_running_loop()
        escape_pressed = asyncio.Event()

        def _read_key() -> None:
            try:
                if os.read(fd, 1) == b"\x1b":
                    escape_pressed.set()
            except BlockingIOError:
                pass

        try:
            tty.setcbreak(fd)
            os.set_blocking(fd, False)
            event_loop.add_reader(fd, _read_key)
            while True:
                await escape_pressed.wait()
                escape_pressed.clear()
                logger.info("用户按下 ESC 键主动暂停当前任务")
                await agent.cancel_all_active_tasks()
        finally:
            event_loop.remove_reader(fd)
            os.set_blocking(fd, was_blocking)
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)

    if channels.enabled_channels:
        print(f"Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        print("Warning: No channels enabled")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        print(f"Cron: {cron_status['jobs']} scheduled jobs")

    async def _health_server(host: str, health_port: int):
        import json as _json

        async def handle(reader, writer):
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=5)
            except (asyncio.TimeoutError, ConnectionError):
                writer.close()
                return

            request_line = data.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
            parts = request_line.split(" ")
            method, path = "", ""
            if len(parts) >= 2:
                method, path = parts[0], parts[1]

            if method == "GET" and path == "/health":
                body = _json.dumps({"status": "ok"})
                resp = (
                    f"HTTP/1.0 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"\r\n{body}"
                )
            else:
                body = "Not Found"
                resp = (
                    f"HTTP/1.0 404 Not Found\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"\r\n{body}"
                )

            writer.write(resp.encode())
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, host, health_port)
        print(f"Health endpoint: http://{host}:{health_port}/health")
        async with server:
            await server.serve_forever()

    async def _run():
        try:
            await cron.start()
            tasks = [
                agent.run(),
                channels.start_all(),
                _health_server(gateway_host, gateway_port),
                _watch_escape(),
            ]
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception:
            print(f"\nError: Gateway crashed unexpectedly")
            traceback.print_exc()
        finally:
            cron.stop()
            agent.stop()
            if isinstance(browser_tool, BrowserTool):
                await browser_tool.close()
            await channels.stop_all()
            flushed = agent.sessions.flush_all()
            if flushed:
                logger.info("Shutdown: flushed {} session(s) to disk", flushed)

    asyncio.run(_run())
