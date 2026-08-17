from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class DashScopeTTS:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def synthesize(self, text: str, voice: str, dest: str, timeout: float) -> None:
        if not self.api_key:
            raise RuntimeError("未配置百炼 API Key，请在设置里填写")
        url = f"{self.base_url}/services/audio/tts/SpeechSynthesizer"
        payload = {
            "model": self.model,
            "input": {
                "text": text,
                "voice": voice,
                "format": "wav",
                "sample_rate": 22050,
                "language_hints": ["zh"],
            },
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "CanYouHearMe/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as err:
                raise RuntimeError(f"百炼 HTTP {e.code}: {raw[:180]}") from err
            raise RuntimeError(
                f"百炼 {parsed.get('code', e.code)}: {parsed.get('message', raw[:180])}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"网络错误: {e.reason}") from e

        parsed = json.loads(raw)
        if parsed.get("code"):
            raise RuntimeError(f"百炼 {parsed.get('code')}: {parsed.get('message')}")
        audio_url = ((parsed.get("output") or {}).get("audio") or {}).get("url")
        if not audio_url:
            raise RuntimeError("百炼未返回音频地址")
        _download(audio_url, dest, timeout)


def _download(url: str, dest: str, timeout: float) -> None:
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "CanYouHearMe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
        out.write(resp.read())
    os.replace(tmp, dest)
