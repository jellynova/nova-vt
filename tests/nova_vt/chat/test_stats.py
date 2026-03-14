from __future__ import annotations

import time
import threading

import pytest

from nova_vt.chat.stats import StreamStats, StatsPollerThread


# ---------------------------------------------------------------------------
# StreamStats unit tests
# ---------------------------------------------------------------------------

class TestStreamStats:
    def test_initial_viewer_counts_are_zero(self):
        stats = StreamStats()
        assert stats.twitch_viewers == 0
        assert stats.youtube_viewers == 0
        assert stats.tiktok_viewers == 0
        assert stats.total_viewers == 0

    def test_total_viewers_is_sum(self):
        stats = StreamStats()
        stats.update_viewers("twitch", 100)
        stats.update_viewers("youtube", 200)
        stats.update_viewers("tiktok", 50)
        assert stats.total_viewers == 350

    def test_update_viewers_unknown_platform_ignored(self):
        stats = StreamStats()
        stats.update_viewers("facebook", 999)  # silently ignored
        assert stats.total_viewers == 0

    def test_stream_time_str_format(self):
        stats = StreamStats()
        stats.set_stream_start(time.time() - 3661)  # 1h 1m 1s ago
        t = stats.stream_time_str
        assert t == "01:01:01"

    def test_stream_time_str_zero_before_start(self):
        stats = StreamStats()
        assert stats.stream_time_str == "00:00:00"

    def test_thread_safe_concurrent_updates(self):
        """Multiple threads updating viewers must not corrupt state."""
        stats = StreamStats()
        errors: list[Exception] = []

        def _updater(platform: str, count: int):
            try:
                for _ in range(200):
                    stats.update_viewers(platform, count)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_updater, args=("twitch", 100)),
            threading.Thread(target=_updater, args=("youtube", 200)),
            threading.Thread(target=_updater, args=("tiktok", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert stats.twitch_viewers == 100
        assert stats.youtube_viewers == 200
        assert stats.tiktok_viewers == 50
        assert stats.total_viewers == 350

    def test_stream_time_str_hours_minutes_seconds(self):
        stats = StreamStats()
        stats.set_stream_start(time.time() - (2 * 3600 + 15 * 60 + 30))
        t = stats.stream_time_str
        assert t == "02:15:30"


# ---------------------------------------------------------------------------
# StatsPollerThread tests
# ---------------------------------------------------------------------------

class TestStatsPollerThread:
    def test_poller_calls_fetcher_and_updates_stats(self):
        stats = StreamStats()
        call_count = {"n": 0}

        def _fetch_twitch() -> int:
            call_count["n"] += 1
            return 42

        def _fetch_youtube() -> int:
            return 99

        poller = StatsPollerThread(
            stats=stats,
            fetchers={"twitch": _fetch_twitch, "youtube": _fetch_youtube},
            interval=0.1,  # 100ms for test speed
        )
        poller.start()
        time.sleep(0.35)  # allow ~3 poll cycles
        poller.stop()
        poller.join(timeout=2.0)

        assert stats.twitch_viewers == 42
        assert stats.youtube_viewers == 99
        assert call_count["n"] >= 2  # polled at least twice

    def test_poller_ignores_fetcher_exception(self):
        """A fetcher that raises must not crash the poller thread."""
        stats = StreamStats()

        def _bad_fetcher() -> int:
            raise RuntimeError("network error")

        poller = StatsPollerThread(
            stats=stats,
            fetchers={"twitch": _bad_fetcher},
            interval=0.1,
        )
        poller.start()
        time.sleep(0.25)
        poller.stop()
        poller.join(timeout=2.0)

        assert not poller.is_alive()
        assert stats.twitch_viewers == 0  # unchanged

    def test_poller_stops_cleanly(self):
        stats = StreamStats()
        poller = StatsPollerThread(stats=stats, fetchers={}, interval=0.05)
        poller.start()
        poller.stop()
        poller.join(timeout=1.0)
        assert not poller.is_alive()
