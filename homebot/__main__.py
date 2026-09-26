"""
Entry point for homebot: python -m homebot
"""

import argparse
import sys

from homebot import __logo__, __version__


def configure_stdio() -> None:
    """Make stdout/stderr UTF-8 safe on every platform.

    When output is redirected to a file or a pipe, Windows Python falls back to
    the ANSI code page of the system locale (GBK on a Chinese install, cp1252 on
    a Western one).  The startup banner contains an emoji, so the process would
    otherwise die with ``UnicodeEncodeError`` before the gateway is up - which is
    exactly what happens when homebot runs as a service.  ``errors="replace"``
    guarantees that no future character can ever be fatal.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - detached stream
                pass


def main():
    configure_stdio()

    parser = argparse.ArgumentParser(
        prog="homebot",
        description=f"{__logo__} homebot - Personal AI Assistant (v{__version__})",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    sub.add_parser("init", help="Initialize homebot for first use")
    sub.add_parser("config", help="Configure homebot settings")
    gateway_parser = sub.add_parser("gateway", help="Start homebot gateway")
    gateway_parser.add_argument("--port", "-p", type=int, help="Gateway port for this run")
    gateway_parser.add_argument("--config", "-c", help="Path to config file")
    gateway_parser.add_argument("--workspace", "-w", help="Workspace directory")
    gateway_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.set_defaults(port=None, config=None, workspace=None, verbose=False)

    args = parser.parse_args()

    if args.command == "init":
        from homebot.cli.init import run_init

        run_init()

    elif args.command == "config":
        from homebot.cli.config import run_config

        run_config()

    else:
        # Default: start gateway
        from homebot.cli.gateway import _load_runtime_config, run

        if args.verbose:
            import logging
            logging.basicConfig(level=logging.DEBUG)

        cfg = _load_runtime_config(args.config, args.workspace)
        run(cfg, port=args.port)


if __name__ == "__main__":
    main()
