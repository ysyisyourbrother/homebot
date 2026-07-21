"""First-run setup for homebot."""

from pathlib import Path

from homebot.channels.voice import VoiceConfig
from homebot.config.loader import get_config_path, save_config
from homebot.config.schema import Config
from homebot.utils.helpers import sync_workspace_templates


def _show_current(value: str | None) -> str:
    return f"[{value}]" if value else "[not set]"


def _required_value(label: str, current: str | None = None, default: str | None = None) -> str:
    while True:
        display = _show_current(current or default)
        value = input(f"  {label} {display}: ").strip()
        if value:
            return value
        if current or default:
            return current or default
        print("    This value is required.")


def run_init() -> None:
    """Create the default workspace and collect required first-run settings."""
    config_path = get_config_path()
    if config_path.exists():
        print(f"Homebot is already initialized: {config_path}")
        print("Run 'python -m homebot config' to change settings.")
        return

    config = Config()
    workspace = Path("~/.homebot/workspace").expanduser()
    config.agents.defaults.workspace = "~/.homebot/workspace"

    print("=" * 50)
    print("  homebot init")
    print("=" * 50)
    print(f"Workspace: {workspace}")
    print("\n--- LLM ---")
    print("Configure an OpenAI-compatible LLM endpoint. Homebot will use this model by default.")

    provider = config.providers.deepseek
    config.agents.defaults.model = _required_value(
        "Model", config.agents.defaults.model, "deepseek-v4-flash"
    )
    provider.api_base = _required_value(
        "API Base URL", provider.api_base, "https://api.deepseek.com/v1"
    )
    provider.api_key = _required_value("API Key", provider.api_key)
    config.agents.defaults.provider = "deepseek"

    print("\n--- Voice ---")
    print("Homebot currently uses Alibaba Cloud DashScope for speech recognition and synthesis.")
    print("STT and TTS share one DashScope API key; the default voice settings will be used.")
    voice = getattr(config.channels, "voice", None)
    if not isinstance(voice, dict):
        voice = VoiceConfig().model_dump(by_alias=True)
        setattr(config.channels, "voice", voice)
    dashscope_api_key = _required_value("DashScope API Key", voice.get("sttApiKey") or voice.get("ttsApiKey"))
    wake_word = _required_value("Wake word")
    voice["enabled"] = True
    voice["sttApiKey"] = dashscope_api_key
    voice["ttsApiKey"] = dashscope_api_key
    voice["wakeWords"] = [wake_word]

    sync_workspace_templates(workspace)
    voice_dir = Path(voice.get("voiceDir", VoiceConfig().voice_dir)).expanduser().resolve()
    from homebot.cli.config import _download_kws_model, _generate_keywords_via_llm

    if not _download_kws_model(voice_dir):
        print("\nInitialization incomplete. Download the KWS model, then run 'python -m homebot init' again.")
        return
    if not _generate_keywords_via_llm(
        voice_dir,
        voice["wakeWords"],
        provider.api_key,
        provider.api_base,
        config.agents.defaults.model,
        config.agents.defaults.max_tokens,
        config.agents.defaults.temperature,
        config.agents.defaults.reasoning_effort,
    ):
        print("\nInitialization incomplete. Generate keywords.txt, then run 'python -m homebot init' again.")
        return

    save_config(config)
    print(f"\nConfig saved to {config_path}")
    print("Initialization complete. Start Homebot with: python -m homebot gateway")
    print("Use 'python -m homebot config' later for advanced settings.")
