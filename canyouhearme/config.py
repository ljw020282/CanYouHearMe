from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from canyouhearme.defaults import DEFAULT_PHRASES, DEFAULT_SHORTCUTS
from canyouhearme.paths import (
    DEFAULT_DASHSCOPE_BASE,
    DEFAULT_DATA_ROOT,
    DEFAULT_MODEL,
    DEFAULT_VOICE,
    LOCAL_KEY_CSV,
)

logger = logging.getLogger(__name__)


def default_payload() -> dict[str, Any]:
    return {
        "data_root": str(DEFAULT_DATA_ROOT),
        "model": DEFAULT_MODEL,
        "voice": DEFAULT_VOICE,
        "dashscope_base": DEFAULT_DASHSCOPE_BASE,
        "api_key": "",
        "immediate_cache_max_chars": 6,
        "background_cache_hits": 3,
        "scan_interval_sec": 60,
        "scan_concurrency": 2,
        "tts_timeout_sec": 5,
        "pin_overlay": True,
        "hide_after_speak": True,
        "monitor_enabled": True,
        "monitor_device": None,
        "cable_device": None,
        "cable_device_name": None,
        "phrases": list(DEFAULT_PHRASES),
        "shortcuts": dict(DEFAULT_SHORTCUTS),
        "overlay_pos": None,
    }


class AppConfig:
    def __init__(self) -> None:
        self._path = DEFAULT_DATA_ROOT / "config.json"
        self.data = default_payload()
        self.load()

    @property
    def root(self) -> Path:
        return Path(self.data["data_root"])

    def load(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "voices").mkdir(exist_ok=True)
        self._path = self.root / "config.json"
        if self._path.exists():
            try:
                loaded = json.loads(self._path.read_text(encoding="utf-8"))
                merged = default_payload()
                merged.update(loaded)
                if isinstance(merged.get("shortcuts"), dict):
                    pass
                else:
                    merged["shortcuts"] = dict(DEFAULT_SHORTCUTS)
                self.data = merged
            except Exception as e:
                logger.error("读取配置失败: %s", e)
        self._import_csv_key_if_empty()
        self.save()

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path = self.root / "config.json"
        self._path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def _import_csv_key_if_empty(self) -> None:
        if self.data.get("api_key"):
            return
        if not LOCAL_KEY_CSV.exists():
            return
        try:
            rows = {
                r[0].strip(): r[1].strip()
                for r in csv.reader(LOCAL_KEY_CSV.read_text(encoding="utf-8").splitlines())
                if len(r) >= 2
            }
            key = rows.get("apiKey") or rows.get("apikey") or ""
            base = rows.get("dashScope") or ""
            if key:
                self.data["api_key"] = key
                logger.info("已从本地 CSV 导入 API Key（未写入源码仓库）")
            if base:
                self.data["dashscope_base"] = base
        except Exception as e:
            logger.warning("导入 CSV 失败: %s", e)
