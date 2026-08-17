from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from canyouhearme.policy import should_keep_audio
from canyouhearme.textutil import text_hash

logger = logging.getLogger(__name__)


class VoiceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "app.sqlite"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS utterances (
                text_hash TEXT NOT NULL,
                voice TEXT NOT NULL,
                text TEXT NOT NULL,
                speak_count INTEGER NOT NULL DEFAULT 0,
                cached INTEGER NOT NULL DEFAULT 0,
                audio_path TEXT,
                updated_at REAL NOT NULL,
                PRIMARY KEY (text_hash, voice)
            )
            """
        )
        self._conn.commit()

    def wav_path(self, text: str, voice: str) -> Path:
        folder = self.root / "voices" / voice
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{text_hash(text)}.wav"

    def cached_path(self, text: str, voice: str) -> Path | None:
        path = self.wav_path(text, voice)
        if path.exists() and path.stat().st_size > 0:
            return path
        return None

    def bump(self, text: str, voice: str) -> int:
        h = text_hash(text)
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT speak_count FROM utterances WHERE text_hash=? AND voice=?",
                (h, voice),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO utterances(text_hash, voice, text, speak_count, cached, updated_at) "
                    "VALUES (?,?,?,?,0,?)",
                    (h, voice, text, 1, now),
                )
                self._conn.commit()
                return 1
            count = int(row["speak_count"]) + 1
            self._conn.execute(
                "UPDATE utterances SET speak_count=?, text=?, updated_at=? "
                "WHERE text_hash=? AND voice=?",
                (count, text, now, h, voice),
            )
            self._conn.commit()
            return count

    def mark_cached(self, text: str, voice: str, audio_path: str) -> None:
        h = text_hash(text)
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO utterances(text_hash, voice, text, speak_count, cached, audio_path, updated_at)
                VALUES (?,?,?,1,1,?,?)
                ON CONFLICT(text_hash, voice) DO UPDATE SET
                    cached=1, audio_path=excluded.audio_path, text=excluded.text, updated_at=excluded.updated_at
                """,
                (h, voice, text, audio_path, now),
            )
            self._conn.commit()

    def pending_scan(
        self,
        voice: str,
        phrases: list[str],
        shortcut_values: list[str],
        immediate_max_chars: int,
        background_hits: int,
    ) -> list[str]:
        wanted = []
        seen: set[str] = set()
        for line in phrases + shortcut_values:
            if line and line not in seen:
                seen.add(line)
                if self.cached_path(line, voice) is None:
                    wanted.append(line)
        with self._lock:
            rows = self._conn.execute(
                "SELECT text, speak_count, cached FROM utterances WHERE voice=?",
                (voice,),
            ).fetchall()
        for row in rows:
            text = row["text"]
            if text in seen:
                continue
            if row["cached"] and self.cached_path(text, voice):
                continue
            if should_keep_audio(
                text,
                phrases=phrases,
                shortcut_values=shortcut_values,
                speak_count=int(row["speak_count"]),
                immediate_max_chars=immediate_max_chars,
                background_hits=background_hits,
            ):
                wanted.append(text)
                seen.add(text)
        return wanted
