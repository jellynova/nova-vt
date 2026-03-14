from __future__ import annotations

import threading
import time
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# StreamStats
# ---------------------------------------------------------------------------

class StreamStats:
    """Thread-safe container for live stream statistics.

    All public attribute reads and writes are protected by a threading.Lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._twitch_viewers: int = 0
        self._youtube_viewers: int = 0
        self._tiktok_viewers: int = 0
        self._stream_start: Optional[float] = None  # epoch timestamp

    # ------------------------------------------------------------------
    # Read-only properties (acquire lock for safety)
    # ------------------------------------------------------------------

    @property
    def twitch_viewers(self) -> int:
        with self._lock:
            return self._twitch_viewers

    @property
    def youtube_viewers(self) -> int:
        with self._lock:
            return self._youtube_viewers

    @property
    def tiktok_viewers(self) -> int:
        with self._lock:
            return self._tiktok_viewers

    @property
    def total_viewers(self) -> int:
        with self._lock:
            return self._twitch_viewers + self._youtube_viewers + self._tiktok_viewers

    @property
    def stream_time_str(self) -> str:
        """Return elapsed stream time as HH:MM:SS, or 00:00:00 if not started."""
        with self._lock:
            if self._stream_start is None:
                return "00:00:00"
            elapsed = int(time.time() - self._stream_start)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def update_viewers(self, platform: str, count: int) -> None:
        """Update viewer count for *platform*. Unknown platforms are ignored."""
        with self._lock:
            if platform == "twitch":
                self._twitch_viewers = count
            elif platform == "youtube":
                self._youtube_viewers = count
            elif platform == "tiktok":
                self._tiktok_viewers = count

    def set_stream_start(self, timestamp: float) -> None:
        with self._lock:
            self._stream_start = timestamp

    def reset(self) -> None:
        with self._lock:
            self._twitch_viewers = 0
            self._youtube_viewers = 0
            self._tiktok_viewers = 0
            self._stream_start = None


# ---------------------------------------------------------------------------
# StatsPollerThread
# ---------------------------------------------------------------------------

class StatsPollerThread(threading.Thread):
    """Polls each platform's viewer-count fetcher every *interval* seconds.

    *fetchers* is a dict mapping platform name → callable() → int.
    Any fetcher that raises is logged and skipped (poller continues).
    """

    def __init__(
        self,
        stats: StreamStats,
        fetchers: dict[str, Callable[[], int]],
        interval: float = 30.0,
    ) -> None:
        super().__init__(daemon=True, name="StatsPollerThread")
        self._stats = stats
        self._fetchers = fetchers
        self._interval = interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.wait(timeout=self._interval):
            self._poll()

    def _poll(self) -> None:
        for platform, fetcher in self._fetchers.items():
            try:
                count = fetcher()
                self._stats.update_viewers(platform, count)
            except Exception:
                pass  # swallow to keep poller alive
