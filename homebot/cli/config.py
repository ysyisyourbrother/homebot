"""Simplified config initialization for homebot — plain input/print, no TUI."""

import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

from homebot.config.loader import get_config_path, load_config, save_config
from homebot.config.schema import (
    AgentDefaults,
    ChannelsConfig,
    Config,
    ProviderConfig,
    ProvidersConfig,
    ToolsConfig,
)

_FIELD_HINTS: dict[str, dict[str, str]] = {
    "voice": {
        "voice_dir": "voice assets root directory",
        "stt_api_key": "DashScope API Key (required for speech recognition)",
        "tts_api_key": "DashScope API Key (required for speech synthesis)",
        "tts_model": "CosyVoice TTS model",
        "tts_voice": "CosyVoice TTS voice name",
        "silence_timeout": "seconds of silence before auto-cancel",
        "kws_score": "wake word detection threshold (lower = more sensitive)",
        "wake_words": "comma-separated wake words (e.g. 大虾米,小助手)",
    },
}
_KWS_MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
_SPEAKER_MODEL_NAME = "3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx"
_SPEAKER_DOWNLOAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    f"speaker-recongition-models/{_SPEAKER_MODEL_NAME}"
)
_KWS_DOWNLOAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    f"{_KWS_MODEL_NAME}.tar.bz2"
)
_VOICE_ASSETS = [
    "audio/wake_reply.wav",
    "audio/bye.wav",
]

_VOICE_ENROLLMENT_TEXTS = [
    "在这个万物互联的边缘计算时代，虽然系统的复杂度和算力需求在呈指数级增长，但我依然相信，最强大的调度算法也比不过家庭里那份温暖的连接。每一次的技术迭代，都是为了让未来的生活少一分延迟，多一分真切的陪伴。",
    "平时敲一天代码再累，只要周末能去厨房里忙活一下，研究点新菜谱，做一桌好吃的，就会觉得特别放松和解压，能让人暂时忘掉那些复杂的系统架构和代码逻辑。",
    "每次趁着假期出去自驾游，我都习惯带上相机记录沿途的风景。当这些影像数据自动同步到家庭服务器，再由智能管家为你分类归档时，你会发现，科技真正的温度就藏在这些点滴的回忆里。",
]


def _show_current(value, default=""):
    """Format a current value for display."""
    if value is None or value == "":
        return f"[not set]" if not default else f"[{default}]"
    return f"[{value}]"


def _list_browser_profiles(user_data_dir: Path) -> list[tuple[str, str]]:
    """List browser profiles under *user_data_dir*. Returns [(name, size_str), ...]."""
    profiles: list[tuple[str, str]] = []
    if not user_data_dir.is_dir():
        return profiles
    for child in sorted(user_data_dir.iterdir()):
        if not child.is_dir():
            continue
        prefs = child / "Preferences"
        if not prefs.is_file():
            continue
        name = child.name
        if name in ("System Profile", "Guest Profile"):
            continue
        try:
            total = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
            if total >= 1024 * 1024:
                size_str = f"{total / (1024 * 1024):.0f}M"
            elif total >= 1024:
                size_str = f"{total / 1024:.0f}K"
            else:
                size_str = f"{total}B"
        except Exception:
            size_str = "?"
        profiles.append((name, size_str))
    return profiles


def _get_package_asset(rel_path: str) -> Path:
    """Get the path to a voice asset within the homebot package."""
    return Path(__file__).resolve().parent.parent / "voice" / "assets" / rel_path


def _sync_voice_assets(voice_dir: Path, silent: bool = False) -> list[str]:
    """Copy voice assets (keywords, audio) from package to voice_dir. Only creates if missing."""
    added: list[str] = []
    for rel_path in _VOICE_ASSETS:
        src = _get_package_asset(rel_path)
        dest = voice_dir / rel_path
        if src.is_file() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            added.append(rel_path)
    if added and not silent:
        for name in added:
            print(f"  Synced voice asset: {name}")
    return added


def _download_progress(block_count, block_size, total_size, last_percent: list[int]) -> None:
    if total_size <= 0:
        return
    percent = min(block_count * block_size * 100 // total_size, 100)
    if percent == last_percent[0]:
        return
    last_percent[0] = percent
    width = 30
    filled = width * percent // 100
    downloaded = min(block_count * block_size, total_size) / (1024 * 1024)
    total = total_size / (1024 * 1024)
    print(
        f"\r  下载中: [{'█' * filled}{'░' * (width - filled)}] "
        f"{percent:3d}% ({downloaded:.1f}/{total:.1f} MB)",
        end="",
        flush=True,
    )


def _download_kws_model(voice_dir: Path) -> bool:
    """Download and extract the KWS model to voice_dir/model/. Returns True on success."""
    import tempfile

    model_dir = voice_dir / "model" / _KWS_MODEL_NAME
    if model_dir.is_dir():
        print(f"  KWS model already exists: {model_dir}")
        return True

    print("  正在下载唤醒词模型...")
    print(f"  下载链接：{_KWS_DOWNLOAD_URL}")
    print(f"  如下载缓慢，可手动下载后解压到：{model_dir.parent}")
    print(f"  最终模型目录：{model_dir}")
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        last_percent = [-1]
        urllib.request.urlretrieve(
            _KWS_DOWNLOAD_URL,
            str(tmp_path),
            lambda block_count, block_size, total_size: _download_progress(
                block_count, block_size, total_size, last_percent
            ),
        )
        print()

        print(f"  正在解压到：{model_dir.parent}")
        model_dir.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(str(tmp_path), "r:bz2") as tar:
            tar.extractall(path=str(model_dir.parent))

        if model_dir.is_dir():
            print(f"  唤醒词模型已就绪：{model_dir}")
            return True
        print("  错误：解压后未找到预期模型目录")
        return False
    except Exception as error:
        print(f"  唤醒词模型下载失败：{error}")
        print(f"  可手动下载：{_KWS_DOWNLOAD_URL}")
        print(f"  下载后请解压到：{model_dir.parent}")
        print(f"  最终模型目录应为：{model_dir}")
        return False
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _download_speaker_model(voice_dir: Path) -> Path | None:
    """Download the speaker verification model to voice_dir/model if missing."""
    import tempfile

    model_path = voice_dir / "model" / _SPEAKER_MODEL_NAME
    if model_path.is_file():
        print(f"  声纹模型已存在：{model_path}")
        return model_path

    print("  正在下载声纹模型...")
    print(f"  下载链接：{_SPEAKER_DOWNLOAD_URL}")
    print(f"  如下载缓慢，可手动下载后放到：{model_path}")
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        last_percent = [-1]
        urllib.request.urlretrieve(
            _SPEAKER_DOWNLOAD_URL,
            str(tmp_path),
            lambda block_count, block_size, total_size: _download_progress(
                block_count, block_size, total_size, last_percent
            ),
        )
        print()
        model_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_path), model_path)
    except Exception as error:
        print(f"  声纹模型下载失败：{error}")
        print(f"  可手动下载：{_SPEAKER_DOWNLOAD_URL}")
        print(f"  下载后请放到：{model_path}")
        return None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    print(f"  声纹模型已就绪：{model_path}")
    return model_path


def _configured_wake_words(section: dict | None) -> list[str]:
    """Return the configured wake words independent of config key casing."""
    if not isinstance(section, dict):
        return []
    return section.get("wakeWords") or section.get("wake_words") or []


def _generate_keywords_via_llm(
    voice_dir: Path,
    wake_words: list[str],
    api_key: str,
    api_base: str,
    model: str,
    max_tokens: int = 8192,
    temperature: float = 0.1,
    reasoning_effort: str | None = None,
    force: bool = False,
) -> bool:
    """Generate keywords.txt via LLM using the user's configured wake word."""
    import json as _json
    import urllib.request as _req

    keywords_path = voice_dir / "keywords.txt"
    existing_content = keywords_path.read_text(encoding="utf-8").strip() if keywords_path.is_file() else ""
    if existing_content and not force:
        return True

    if not wake_words:
        print("  No wake words configured, skipping keywords.txt generation")
        return False

    wake_word = wake_words[0]
    prompt = (
        f"为 sherpa-onnx KeywordSpotter 生成唤醒词「{wake_word}」的 keywords.txt。\n\n"
        f"=== 格式规则（严格遵守）===\n"
        f"每个汉字拆成「声母」和「韵母（带声调）」两个 token，空格分隔。\n"
        f"韵母的声调标在元音上（ā á ǎ à / ō ó ǒ ò / ē é ě è / ī í ǐ ì / ū ú ǔ ù / ǖ ǘ ǚ ǜ）。\n"
        f"轻声则韵母不标调（如 i 而非 ǐ）。\n"
        f"行末加「 @唤醒词」。\n\n"
        f"=== 完整示例：唤醒词「大虾米」===\n"
        f"拆分：大=d+à  虾=x+iā  米=m+ǐ\n"
        f"标准发音：d à x iā m ǐ @大虾米\n\n"
        f"变体规则：每个字可取「标准声调」或「轻声」，N字产生2^N行。\n"
        f"「大虾米」3字→8行变体：\n"
        f"d à x iā m ǐ @大虾米\n"
        f"d à x iā m i @大虾米\n"
        f"d à x ia m i @大虾米\n"
        f"d à x ia m ǐ @大虾米\n"
        f"d a x iā m ǐ @大虾米\n"
        f"d a x iā m i @大虾米\n"
        f"d a x ia m ǐ @大虾米\n"
        f"d a x ia m i @大虾米\n\n"
        f"=== 可用声母 ===\n"
        f"b p m f d t n l g k h j q x zh ch sh r z c s（零声母只写韵母）\n\n"
        f"=== 可用韵母 ===\n"
        f"无调：a ai an ang ao e ei en eng er i ia ian iang iao ie in ing iu o ong ou u ua uai uan uang ue ui un uo\n"
        f"带调：à á ā ǎ ài ái āi ǎi àn án ān ǎn àng áng āng ǎng ào áo āo ǎo\n"
        f"è é ē ě èi éi ēi ěi èn én ēn ěn èng éng ēng ěng èr ér ěr\n"
        f"ì í ī ǐ ìn ín īn ǐn ìng íng īng ǐng ò ó ō ǒ òng óng ōng ǒng òu óu ōu ǒu\n"
        f"ù ú ū ǔ ùn ún ūn ǔn ǘ ǚ\n"
        f"ià iá iā iǎ iàn ián iān iǎn iàng iáng iāng iǎng iào iáo iāo iǎo iè ié iē iě\n"
        f"iòng ióng iōng iǒng iù iú iū iǔ\n"
        f"uà uá uā uǎ uài uái uāi uǎi uàn uán uān uǎn uàng uáng uāng uǎng uè ué uē uě uì uí uī uǐ uò uó uō uǒ üè üě\n\n"
        f"只输出内容本身，一行一个变体，不要解释、markdown格式或代码块。"
    )

    base = api_base.rstrip("/")
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"

    if not existing_content:
        print("  正在访问大模型生成 keywords.txt...")

    try:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if "api.deepseek.com" in base:
            effort = (reasoning_effort or "").lower()
            payload["thinking"] = {"type": "enabled" if effort and effort not in {"minimal", "minimum"} else "disabled"}
        body = _json.dumps(payload).encode("utf-8")

        req = _req.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with _req.urlopen(req, timeout=30) as resp:
            result = _json.loads(resp.read().decode("utf-8"))

        content = result["choices"][0]["message"].get("content") or ""
        if not isinstance(content, str):
            content = ""
        content = content.strip()
        # Strip markdown code fences if the LLM wraps the output
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        if not content:
            print("  大模型返回的 keywords.txt 内容为空。请检查模型或 API 配置后重试。")
            return False

        keywords_path.parent.mkdir(parents=True, exist_ok=True)
        keywords_path.write_text(content + "\n", encoding="utf-8")
        print(f"  keywords.txt 已生成：{keywords_path}")
        return True

    except Exception as e:
        print(f"  Failed to generate keywords.txt: {e}")
        print(f"  You can create {keywords_path} manually with sherpa-onnx phoneme syntax.")
        return False


def _configure_provider(config: Config) -> None:
    """Configure the LLM provider (currently DeepSeek only)."""
    print("\n--- LLM Provider ---")
    print("  [1] DeepSeek")

    choice = input("Select [1, Enter to skip]: ").strip()
    if not choice or choice != "1":
        return

    p = config.providers.deepseek
    print("\nConfiguring DeepSeek:")

    current_key = _show_current(p.api_key)
    key = input(f"  API Key {current_key}: ").strip()
    if key:
        p.api_key = key

    current_base = _show_current(p.api_base)
    base = input(f"  API Base (optional) {current_base}: ").strip()
    if base:
        p.api_base = base


def _configure_voice_audio_devices(section: dict) -> None:
    """Let the user select the audio devices used only by the voice channel."""
    try:
        import sounddevice as sd
    except ImportError:
        print("  sounddevice is not installed; audio devices cannot be listed.")
        return

    def select(label: str, channel_key: str) -> None:
        devices = [
            device["name"]
            for device in sd.query_devices()
            if device[channel_key] > 0
        ]
        if not devices:
            print(f"  No {label.lower()} devices found.")
            return

        field = "inputDevice" if channel_key == "max_input_channels" else "outputDevice"
        current = section.get(field, section.get(field[0].lower() + field[1:], ""))
        print(f"\n  {label} device {_show_current(current, 'system default')}")
        print("    [0] System default")
        for index, name in enumerate(devices, 1):
            print(f"    [{index}] {name}")

        choice = input(f"  Select {label.lower()} device [Enter to keep]: ").strip()
        if not choice:
            return
        try:
            index = int(choice)
        except ValueError:
            print("    Expected a device number, keeping current value")
            return
        if index == 0:
            section[field] = ""
        elif 1 <= index <= len(devices):
            section[field] = devices[index - 1]
        else:
            print("    Invalid device number, keeping current value")

    print("  (These settings only affect Homebot voice; system defaults stay unchanged.)")
    select("Input", "max_input_channels")
    select("Output", "max_output_channels")


def _finalize_voice_config(config: Config, previous_voice_section: dict | None = None) -> bool:
    """Generate voice assets after a completed Voice Channel setting change."""
    voice_section = getattr(config.channels, "voice", None)
    if not isinstance(voice_section, dict) or not voice_section.get("enabled"):
        return True

    voice_dir = Path(voice_section.get("voiceDir", "~/.homebot/workspace/voice")).expanduser().resolve()
    _sync_voice_assets(voice_dir, silent=True)
    model_dir = voice_dir / "model" / _KWS_MODEL_NAME
    if not model_dir.is_dir():
        print(f"Voice configuration was not saved because the KWS model is missing: {model_dir}")
        print("Use Voice Channel > Enable / Disable Voice Channel to download it.")
        return False

    wake_words = _configured_wake_words(voice_section)
    if not wake_words:
        return True
    wake_words_changed = wake_words != _configured_wake_words(previous_voice_section)
    provider_api_key = config.get_api_key()
    provider_api_base = config.get_api_base()
    if provider_api_key and provider_api_base:
        if not _generate_keywords_via_llm(
            voice_dir,
            wake_words,
            provider_api_key,
            provider_api_base,
            config.agents.defaults.model,
            config.agents.defaults.max_tokens,
            config.agents.defaults.temperature,
            config.agents.defaults.reasoning_effort,
            force=wake_words_changed,
        ):
            print("Voice configuration was not saved because keywords.txt could not be generated.")
            return False
    else:
        print("Voice configuration was not saved because no LLM provider is configured.")
        return False
    return True


def _save_config(
    config: Config,
    prepare_voice: bool = False,
    previous_voice_section: dict | None = None,
) -> bool:
    """Persist configuration, preparing voice dependencies when requested."""
    if prepare_voice and not _finalize_voice_config(config, previous_voice_section):
        return False
    save_config(config)
    from homebot.utils.helpers import sync_workspace_templates

    sync_workspace_templates(Path(config.agents.defaults.workspace).expanduser().resolve())
    print(f"Config saved to {get_config_path()}")
    return True


def _configure_kws_settings(section: dict, defaults) -> None:
    """Configure wake word detector thresholds."""
    fields = [
        ("kwsScore", "KWS score", "kws_score", float),
        ("kwsThreshold", "KWS token threshold", "kws_threshold", float),
        ("kwsMaxActivePaths", "KWS max active paths", "kws_max_active_paths", int),
    ]
    print("\n--- KWS Detection Settings ---")
    print("  Enter keeps the current value.")
    for key, label, default_name, value_type in fields:
        current = section.get(key, getattr(defaults, default_name))
        value = input(f"  {label} {_show_current(current)}: ").strip()
        if not value:
            section[key] = current
            continue
        try:
            section[key] = value_type(value)
        except ValueError:
            print(f"    Expected a {value_type.__name__}, keeping current value")


def _configure_voice(config: Config) -> None:
    """Configure the voice channel and its local speaker profiles."""
    from homebot.channels.voice import VoiceConfig

    section = getattr(config.channels, "voice", None)
    if not isinstance(section, dict):
        section = {}
        setattr(config.channels, "voice", section)
    defaults = VoiceConfig()
    for key, default_name in (
        ("kwsScore", "kws_score"),
        ("kwsThreshold", "kws_threshold"),
        ("kwsMaxActivePaths", "kws_max_active_paths"),
    ):
        section.setdefault(key, getattr(defaults, default_name))

    while True:
        enabled = section.get("enabled", defaults.enabled)
        wake_words = _configured_wake_words(section)
        voice_dir = Path(section.get("voiceDir", defaults.voice_dir)).expanduser().resolve()
        profiles = _sync_speaker_profiles(section, voice_dir)
        recognition_enabled = section.get("speakerVerificationEnabled", defaults.speaker_verification_enabled)
        print("\n--- Voice Channel ---")
        print(f"  Status: {'enabled' if enabled else 'disabled'}")
        print(f"  Wake words: {', '.join(wake_words) or 'not set'}")
        print(f"  User recognition: {'enabled' if recognition_enabled else 'disabled'} ({len(profiles)} users)")
        print("  [1] Enable / Disable Voice Channel")
        print("  [2] Basic settings")
        print("  [3] Audio devices")
        print("  [4] User Recognition Settings")
        print("  [5] KWS Detection Settings")
        print("  [0] Back")
        choice = input("Choice [0-5]: ").strip()
        if not choice or choice == "0":
            return
        if choice == "1":
            if enabled:
                section["enabled"] = False
                _save_config(config)
                print("  Voice Channel disabled. Existing models and settings were kept.")
                continue
            voice_dir = Path(section.get("voiceDir", defaults.voice_dir)).expanduser().resolve()
            if not _download_kws_model(voice_dir):
                continue
            section["enabled"] = True
            _sync_voice_assets(voice_dir, silent=True)
            _save_config(config)
            print("  Voice Channel enabled.")
            keywords_missing = not (voice_dir / "keywords.txt").exists()
            _configure_voice_basic_settings(section, defaults)
            if _finalize_voice_config(config, {"enabled": False}):
                _save_config(config)
                if keywords_missing and _configured_wake_words(section):
                    return
        elif choice == "2":
            previous_voice_section = dict(section)
            voice_dir = Path(section.get("voiceDir", defaults.voice_dir)).expanduser().resolve()
            keywords_missing = not (voice_dir / "keywords.txt").exists()
            _configure_voice_basic_settings(section, defaults)
            if _finalize_voice_config(config, previous_voice_section):
                _save_config(config)
                if keywords_missing and _configured_wake_words(section):
                    return
        elif choice == "3":
            _configure_voice_audio_devices(section)
            _save_config(config)
        elif choice == "4":
            _configure_user_recognition(config)
        elif choice == "5":
            _configure_kws_settings(section, defaults)
            _save_config(config)
        else:
            print(f"Invalid choice: {choice}")


def _configure_voice_basic_settings(section: dict, defaults) -> None:
    """Configure the small set of Voice settings users need routinely."""
    fields = [
        ("sttApiKey", "STT API Key", "str"),
        ("ttsApiKey", "TTS API Key", "str"),
        ("ttsModel", "TTS model", "str"),
        ("ttsVoice", "TTS voice", "str"),
        ("wakeWords", "Wake words (comma-separated)", "list"),
        ("silenceTimeout", "Silence timeout (seconds)", "float"),
    ]
    print("\n--- Voice Basic Settings ---")
    print("  Enter keeps the current value.")
    for key, label, value_type in fields:
        field_name = {
            "sttApiKey": "stt_api_key",
            "ttsApiKey": "tts_api_key",
            "ttsModel": "tts_model",
            "ttsVoice": "tts_voice",
            "wakeWords": "wake_words",
            "silenceTimeout": "silence_timeout",
        }.get(key, key)
        current = section.get(key, getattr(defaults, field_name))
        if value_type == "bool":
            value = input(f"  {label} (yes/no) [{'yes' if current else 'no'}]: ").strip().lower()
            if value in ("yes", "no"):
                section[key] = value == "yes"
        elif value_type == "list":
            value = input(f"  {label} {_show_current(', '.join(current))}: ").strip()
            if value:
                section[key] = [word.strip() for word in value.split(",") if word.strip()]
        elif value_type == "float":
            value = input(f"  {label} {_show_current(current)}: ").strip()
            if value:
                try:
                    section[key] = float(value)
                except ValueError:
                    print("    Expected a number, keeping current value")
        else:
            value = input(f"  {label} {_show_current(current)}: ").strip()
            if value:
                section[key] = value


def _configure_channels(config: Config) -> None:
    """Configure chat channels. Uses channel auto-discovery for config models."""
    from homebot.channels.registry import discover_all

    all_channels = discover_all()
    # Show common channels the user may want to configure
    channel_list = [(n, c) for n, c in all_channels.items() if n in ("feishu", "telegram")]
    if not channel_list:
        print("No channels to configure.")
        return

    while True:
        print("\n--- Chat Channels ---")
        for i, (name, cls) in enumerate(channel_list, 1):
            section = getattr(config.channels, name, None)
            if section is None:
                section = {}
            enabled = section.get("enabled", False) if isinstance(section, dict) else getattr(section, "enabled", False)
            status = "*" if enabled else " "
            display_name = getattr(cls, "display_name", name.capitalize())
            print(f"  [{i}] [{status}] {display_name} ({name})")
        print("  [0] Back")

        choice = input("Select channel to configure [0-{}, Enter to skip]: ".format(len(channel_list))).strip()
        if not choice or choice == "0":
            break

        try:
            idx = int(choice) - 1
            name, cls = channel_list[idx]
        except (ValueError, IndexError):
            print(f"Invalid choice: {choice}")
            continue

        # Get or create channel config dict
        section = getattr(config.channels, name, None)
        if section is None or not isinstance(section, dict):
            section = {"enabled": False}
            setattr(config.channels, name, section)

        display_name = getattr(cls, "display_name", name.capitalize())

        # Try to find the channel's config model for field info
        try:
            import importlib
            mod = importlib.import_module(f"homebot.channels.{name}")
            config_name_pascal = cls.__name__.replace("Channel", "Config")
            config_cls = getattr(mod, config_name_pascal, None)
        except Exception:
            config_cls = None

        print(f"\nConfiguring {display_name}:")

        enabled_cur = "yes" if section.get("enabled", False) else "no"
        en = input(f"  Enable? (yes/no) [{enabled_cur}]: ").strip().lower()
        if en in ("yes", "no"):
            section["enabled"] = en == "yes"

        # Ask for common fields
        sensitive_fields = {"api_key", "app_secret", "token", "secret", "encrypt_key", "signing_secret", "verification_token"}
        general_fields = {"app_id", "group_policy", "streaming", "allow_from", "proxy"}
        skip_fields = {"enabled", "accounts"}  # complex nested fields

        if config_cls:
            model_fields = config_cls.model_fields if hasattr(config_cls, "model_fields") else {}
            # Show simple string/bool/int fields only
            simple_fields = {
                k: v for k, v in model_fields.items()
                if k not in skip_fields and str(v.annotation) in (
                    "<class 'str'>", "<class 'int'>", "<class 'float'>", "<class 'bool'>",
                    "str | None", "int | None", "bool | None",
                    "str", "int", "float", "bool",
                    "list[str]", "list",
                )
            }
            field_names = list(simple_fields.keys())
        else:
            field_names = sorted(sensitive_fields | general_fields)

        hints = _FIELD_HINTS.get(name, {})
        print(f"  (Configure fields below, Enter to keep current value)")
        for fname in field_names:
            # Resolve the JSON key (camelCase alias) for this field
            alias = fname
            if config_cls and fname in config_cls.model_fields:
                alias = config_cls.model_fields[fname].alias or fname

            # Look up current value in both snake_case and camelCase
            current = section.get(fname, "")
            if not current and alias != fname:
                current = section.get(alias, "")

            # Look up model default so we show it instead of "[not set]"
            model_default = ""
            if config_cls and fname in model_fields:
                field_info = model_fields[fname]
                if field_info.default_factory:
                    try:
                        df = field_info.default_factory()
                        if isinstance(df, (str, int, float)) and df != "":
                            model_default = str(df)
                    except Exception:
                        pass
                elif isinstance(field_info.default, (str, int, float)) and field_info.default != "":
                    model_default = str(field_info.default)
            is_sens = fname in sensitive_fields or "key" in fname or "secret" in fname or "token" in fname
            cur_display = _show_current(current, default=model_default)
            hint = hints.get(fname, "")
            label = f"{fname} ({hint})" if hint else fname
            val = input(f"  {label} {cur_display}: ").strip()
            if val:
                # Handle bool fields
                if isinstance(current, bool):
                    section[alias] = val.lower() in ("yes", "true", "1", "y")
                elif isinstance(current, int):
                    try:
                        section[alias] = int(val)
                    except ValueError:
                        print(f"    Expected integer, keeping current value")
                elif isinstance(current, list) or (
                    config_cls
                    and fname in model_fields
                    and "list" in str(model_fields[fname].annotation)
                ):
                    section[alias] = [w.strip() for w in val.split(",") if w.strip()]
                else:
                    section[alias] = val
                # Clean up snake_case key if it differs from alias
                if alias != fname and fname in section:
                    del section[fname]

        if name == "voice":
            _configure_voice_audio_devices(section)


def _discover_speaker_profiles(voice_dir: Path, existing_profiles: list[dict] | None = None) -> list[dict]:
    """Build speaker profiles from the user directories under speakers/."""
    existing_by_id = {
        profile.get("id"): profile
        for profile in existing_profiles or []
        if profile.get("id")
    }
    speakers_dir = voice_dir / "speakers"
    if not speakers_dir.is_dir():
        return []

    profiles = []
    for profile_dir in sorted(path for path in speakers_dir.iterdir() if path.is_dir()):
        profile_id = profile_dir.name
        existing = existing_by_id.get(profile_id, {})
        profiles.append({
            "id": profile_id,
            "name": existing.get("name") or profile_id.replace("-", " ").title(),
            "enrollmentWavs": [str(path) for path in sorted(profile_dir.glob("*.wav"))],
        })
    return profiles


def _sync_speaker_profiles(section: dict, voice_dir: Path) -> list[dict]:
    """Treat speaker profile directories as the source of truth."""
    profiles = _discover_speaker_profiles(voice_dir, section.get("speakerProfiles", []))
    section["speakerProfiles"] = profiles
    return profiles


def _configure_user_recognition(config: Config) -> None:
    """Configure local voice-based user recognition."""
    from homebot.channels.voice import VoiceConfig

    section = getattr(config.channels, "voice", None)
    if not isinstance(section, dict):
        section = {"enabled": False}
        setattr(config.channels, "voice", section)
    voice_dir = Path(section.get("voiceDir", VoiceConfig().voice_dir)).expanduser().resolve()
    profiles = _sync_speaker_profiles(section, voice_dir)

    while True:
        enabled = section.get("speakerVerificationEnabled", False)
        profiles = _sync_speaker_profiles(section, voice_dir)
        print("\n--- User Recognition Settings ---")
        print(f"  Status: {'enabled' if enabled else 'disabled'}")
        print(f"  Registered users: {len(profiles)}")
        print("  [1] Enable / Disable user recognition")
        print("  [2] Manage user profiles")
        print("  [0] Back")
        choice = input("Choice [0-2]: ").strip()
        if not choice or choice == "0":
            return
        if choice == "1":
            if enabled:
                section["speakerVerificationEnabled"] = False
                _save_config(config)
                print("  User recognition disabled. Existing profiles and model were kept.")
                continue
            model_path = _prepare_speaker_model(section, voice_dir)
            if model_path is None:
                continue
            section["speakerVerificationEnabled"] = True
            section["speakerModelPath"] = str(model_path)
            _save_config(config)
            print("  User recognition enabled.")
            if not profiles and input("  Configure user profiles now? (yes/no) [yes]: ").strip().lower() in ("", "yes"):
                _configure_family_members(config)
                _save_config(config)
        elif choice == "2":
            _configure_family_members(config)
            _save_config(config)
        else:
            print(f"Invalid choice: {choice}")


def _prepare_speaker_model(section: dict, voice_dir: Path) -> Path | None:
    """Resolve the configured speaker model, downloading the default when needed."""
    from homebot.channels.voice import VoiceConfig

    configured_path = Path(section.get("speakerModelPath", VoiceConfig().speaker_model_path)).expanduser()
    default_model_path = Path(VoiceConfig().speaker_model_path).expanduser()
    if configured_path == default_model_path:
        return _download_speaker_model(voice_dir)
    return configured_path


def _configure_family_members(config: Config) -> None:
    """Manage household speaker profiles and their enrollment recordings."""
    from homebot.channels.voice import VoiceConfig
    from homebot.voice.speaker_verification import SpeakerVerifier, member_id, record_wav

    workspace = Path(config.agents.defaults.workspace).expanduser().resolve()
    from homebot.utils.helpers import sync_workspace_templates

    sync_workspace_templates(workspace, silent=True)
    section = getattr(config.channels, "voice", None)
    if not isinstance(section, dict):
        section = {"enabled": False}
        setattr(config.channels, "voice", section)
    voice_dir = Path(section.get("voiceDir", VoiceConfig().voice_dir)).expanduser().resolve()
    voice_dir.mkdir(parents=True, exist_ok=True)

    model_path = _prepare_speaker_model(section, voice_dir)
    if model_path is None:
        return
    try:
        verifier = SpeakerVerifier(model_path, {}, float(section.get("speakerThreshold", 0.60)))
    except Exception as error:
        print(f"无法加载声纹模型：{error}")
        return

    profiles = _sync_speaker_profiles(section, voice_dir)

    def enroll(profile: dict) -> None:
        profile_id = profile["id"]
        name = profile["name"]
        profile_dir = voice_dir / "speakers" / profile_id
        wav_paths = []
        for sample_index, text in enumerate(_VOICE_ENROLLMENT_TEXTS, 1):
            wav_path = profile_dir / f"{sample_index}.wav"
            print(f"\n{name} 的第 {sample_index} 段注册语音，请自然朗读约 10 秒：")
            print(f"  {text}")
            record_wav(wav_path, section.get("inputDevice") or None)
            verifier.enroll_wav(wav_path)
            wav_paths.append(str(wav_path))
        profile["enrollmentWavs"] = wav_paths
        profile.pop("enrollmentWav", None)
        profile_path = workspace / "members" / profile_id / "USER.md"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        if not profile_path.exists():
            from importlib.resources import files as package_files

            template = package_files("homebot") / "templates" / "members" / "USER.md"
            profile_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  已更新声纹录音；个人档案：{profile_path}")

    guest_profile = workspace / "members" / "guest" / "USER.md"

    while True:
        print("\n--- User Profiles ---")
        for index, profile in enumerate(profiles, 1):
            print(f"  [{index}] {profile['name']} (re-record / delete)")
        print(f"  [{len(profiles) + 1}] Add user profile")
        print("  [0] Back")
        choice = input(f"Choice [0-{len(profiles) + 1}]: ").strip()
        if not choice or choice == "0":
            break
        try:
            selected = int(choice)
        except ValueError:
            print("Invalid choice.")
            continue
        if 1 <= selected <= len(profiles):
            profile = profiles[selected - 1]
            action = input(f"  {profile['name']}: [1] Re-record [2] Delete [0] Cancel: ").strip()
            if action == "1":
                enroll(profile)
            elif action == "2":
                shutil.rmtree(voice_dir / "speakers" / profile["id"], ignore_errors=True)
                profiles.pop(selected - 1)
                print(f"  Deleted user recognition profile: {profile['name']}")
            continue
        if selected != len(profiles) + 1:
            print("Invalid choice.")
            continue

        name = input("User name: ").strip()
        if not name:
            print("Name is required.")
            continue
        profile_id = member_id(name, len(profiles) + 1)
        if any(profile["id"] == profile_id for profile in profiles):
            print("This user already exists. Select the existing profile to re-record it.")
            continue
        profile = {"id": profile_id, "name": name, "enrollmentWavs": []}
        enroll(profile)
        profiles.append(profile)

    section["speakerModelPath"] = str(model_path)
    section["speakerProfiles"] = profiles
    print(f"Guest profile: {guest_profile}")


def _configure_skills(workspace: Path) -> None:
    while True:
        print("\n--- Skills ---")
        print("  [1] Mijia")
        print("  [0] Back")
        choice = input("Choice [0-1]: ").strip()
        if choice == "0" or not choice:
            return
        if choice == "1":
            _configure_mijia(workspace)
        else:
            print(f"Invalid choice: {choice}")


def _configure_mijia(workspace: Path) -> None:
    skill_dir = workspace / "skills" / "mijia"
    config_path = skill_dir / "config.json"
    current: dict[str, str] = {}
    try:
        current = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    print("\n--- Mijia ---")
    base_url = input(f"  Mijia 网关地址 {_show_current(current.get('base_url'))}: ").strip()
    access_token = input(f"  Mijia 访问令牌 {_show_current(current.get('access_token'))}: ").strip()
    base_url = base_url or current.get("base_url", "")
    access_token = access_token or current.get("access_token", "")
    if not base_url or not access_token:
        print("  Mijia 网关地址和访问令牌均为必填项，未保存配置。")
        return

    skill_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"base_url": base_url, "access_token": access_token}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    from homebot.skills.mijia.driver import build_skill, request

    try:
        build_skill(request(base_url.rstrip("/"), access_token, "/api/states"), skill_dir / "SKILL.md")
    except RuntimeError as error:
        print(f"  Mijia 配置已保存，但设备列表刷新失败：{error}")
    else:
        print(f"  Mijia Skill 已刷新：{skill_dir / 'SKILL.md'}")


def _configure_agent_settings(config: Config) -> None:
    a = config.agents.defaults
    print("\n--- Agent Settings ---")

    cur = _show_current(a.model, "deepseek-v4-flash")
    val = input(f"  Model {cur}: ").strip()
    if val:
        a.model = val

    cur = _show_current(a.provider, "auto")
    val = input(f"  Provider (auto/deepseek) {cur}: ").strip()
    if val:
        a.provider = val

    cur = _show_current(a.temperature, "0.1")
    val = input(f"  Temperature {cur}: ").strip()
    if val:
        try:
            a.temperature = float(val)
        except ValueError:
            pass

    cur = _show_current(a.max_tokens, "8192")
    val = input(f"  Max Tokens {cur}: ").strip()
    if val:
        try:
            a.max_tokens = int(val)
        except ValueError:
            pass

    cur = _show_current(a.context_window_tokens, "65536")
    val = input(f"  Context Window (tokens) {cur}: ").strip()
    if val:
        try:
            a.context_window_tokens = int(val)
        except ValueError:
            pass

    cur = _show_current(a.timezone, "UTC")
    val = input(f"  Timezone {cur}: ").strip()
    if val:
        a.timezone = val

    cur = _show_current(a.workspace, "~/.homebot/workspace")
    val = input(f"  Workspace {cur}: ").strip()
    if val:
        a.workspace = val


def _configure_tools(config: Config) -> None:
    t = config.tools
    print("\n--- Tools Settings ---")

    cur = "yes" if t.web.enable else "no"
    val = input(f"  Web Fetch (yes/no) [{cur}]: ").strip().lower()
    if val in ("yes", "no"):
        t.web.enable = val == "yes"

    search = t.web_search
    cur = "yes" if search.enable else "no"
    val = input(f"  Web Search (yes/no) [{cur}]: ").strip().lower()
    if val in ("yes", "no"):
        search.enable = val == "yes"
    if search.enable:
        print("    Provider: Tavily")
        val = input(f"    Tavily API Key {_show_current(search.api_key)}: ").strip()
        if val:
            search.api_key = val

    cur = "yes" if t.exec.enable else "no"
    val = input(f"  Shell Exec (yes/no) [{cur}]: ").strip().lower()
    if val in ("yes", "no"):
        t.exec.enable = val == "yes"

    cur = "yes" if t.browser.enable else "no"
    val = input(f"  Browser (yes/no) [{cur}]: ").strip().lower()
    if val in ("yes", "no"):
        t.browser.enable = val == "yes"

    cur = _show_current(t.browser.executable_path)
    val = input(f"    Browser Executable Path {cur}: ").strip()
    if val:
        t.browser.executable_path = val

    cur = _show_current(t.browser.user_data_dir)
    val = input(f"    User Data Directory {cur}: ").strip()
    if val:
        t.browser.user_data_dir = val

    # Let user choose which Homebot Chrome profile to use
    resolved_dir = Path(t.browser.user_data_dir).expanduser()
    profiles = _list_browser_profiles(resolved_dir)
    print(f"    Homebot Chrome profiles found under {resolved_dir}:")
    print(f"      [0] Homebot Chrome \"Homebot\" profile")
    for i, (name, size) in enumerate(profiles, 1):
        print(f"      [{i}] {name} ({size})")
    if profiles:
        cur_profile = t.browser.profile or "Homebot"
        profile_prompt = f"    Select profile number [current: {cur_profile}]: "
    else:
        cur_profile = t.browser.profile or "Homebot"
        profile_prompt = f"    Profile name (subdirectory) [{cur_profile}]: "
    val = input(profile_prompt).strip()
    if val:
        try:
            idx = int(val)
            if idx == 0:
                t.browser.profile = "Homebot"
            elif 1 <= idx <= len(profiles):
                t.browser.profile = profiles[idx - 1][0]
            else:
                print(f"    Invalid profile number, keeping current value")
        except ValueError:
            t.browser.profile = val

    refresh = t.browser.session_refresh
    current_urls = ", ".join(refresh.urls) or "none"
    val = input(
        f"    Session Refresh URLs (comma-separated, 'none' to clear) [{current_urls}]: "
    ).strip()
    if val.lower() == "none":
        refresh.urls = []
    elif val:
        refresh.urls = [url.strip() for url in val.split(",") if url.strip()]

    val = input(f"    Session Refresh Interval Hours [{refresh.interval_hours}]: ").strip()
    if val:
        try:
            interval_hours = int(val)
            if interval_hours > 0:
                refresh.interval_hours = interval_hours
        except ValueError:
            pass


def _show_summary(config: Config) -> None:
    print("\n" + "=" * 50)
    print("Configuration Summary")
    print("=" * 50)

    a = config.agents.defaults
    print(f"  Agent: model={a.model}, provider={a.provider}, tz={a.timezone}")
    print(f"  Workspace: {a.workspace}")

    for name in ("deepseek",):
        p = getattr(config.providers, name)
        if p.api_key:
            key_masked = p.api_key[:8] + "..." + p.api_key[-4:] if len(p.api_key) > 12 else "***"
            print(f"  Provider {name}: key={key_masked}")

    from homebot.channels.registry import discover_all
    for name, cls in discover_all().items():
        section = getattr(config.channels, name, None)
        if section is None:
            section = {}
        enabled = section.get("enabled", False) if isinstance(section, dict) else getattr(section, "enabled", False)
        status = "enabled" if enabled else "disabled"
        display = getattr(cls, "display_name", name.capitalize())
        print(f"  Channel {display}: {status}")

    browser = config.tools.browser
    web_search = config.tools.web_search
    search_status = "no"
    if web_search.enable:
        search_status = f"yes ({web_search.provider}, {'configured' if web_search.api_key else 'API key missing'})"
    print(
        f"  Tools: web fetch={'yes' if config.tools.web.enable else 'no'}, "
        f"web search={search_status}, "
        f"exec={'yes' if config.tools.exec.enable else 'no'}, "
        f"browser={'yes' if browser.enable else 'no'} "
        f"(profile={browser.profile}, refresh URLs={len(browser.session_refresh.urls)})"
    )
    print("=" * 50)


def run_config() -> None:
    """Run the configuration editor."""
    print("=" * 50)
    print("  homebot config")
    print("=" * 50)

    config_path = get_config_path()
    if not config_path.exists():
        print("Homebot has not been initialized.")
        print("Run 'python -m homebot init' first to create the initial configuration.")
        return

    print(f"Config found: {config_path}")
    config = load_config()

    menu = {
        "1": ("LLM Providers", lambda: _configure_provider(config), False),
        "2": ("Agent Settings", lambda: _configure_agent_settings(config), False),
        "3": ("Voice Channel", lambda: _configure_voice(config), False),
        "4": ("Tools Settings", lambda: _configure_tools(config), False),
        "5": (
            "Skills Settings",
            lambda: _configure_skills(Path(config.agents.defaults.workspace).expanduser().resolve()),
            False,
        ),
        "6": ("Chat Channels", lambda: _configure_channels(config), False),
    }

    while True:
        print("\n--- Main Menu ---")
        for key, (label, _, _) in menu.items():
            print(f"  [{key}] {label}")
        print("  [7] Review Summary")
        print("  [0] Exit")

        choice = input("Choice [0-7]: ").strip()
        if choice == "0":
            print("Exited.")
            return
        if choice == "7":
            _show_summary(config)
            continue
        if choice not in menu:
            print(f"Invalid choice: {choice}")
            continue

        _, configure, _ = menu[choice]
        configure()
        if choice != "3":
            _save_config(config)
