from pathlib import Path

DEFAULT_DATA_ROOT = Path(r"G:\CanYouHearMeVoice\cosyvoice-v3-flash")
DEFAULT_MODEL = "cosyvoice-v3-flash"
DEFAULT_VOICE = "longtian_v3"
DEFAULT_DASHSCOPE_BASE = (
    "https://ws-o1l0tqejdxuruzau.cn-beijing.maas.aliyuncs.com/api/v1"
)
TTS_PATH = "/services/audio/tts/SpeechSynthesizer"

# Optional local import only — never ship the key in git.
LOCAL_KEY_CSV = Path(r"F:\aliyun\百炼\默认业务空间-apiKey-6716879.csv")
