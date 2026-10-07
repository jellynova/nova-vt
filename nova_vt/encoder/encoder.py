from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


@dataclass
class EncoderConfig:
    video_fifo: str = "/tmp/nova-vt-video.fifo"
    audio_fifo: str = "/tmp/nova-vt-audio.fifo"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    sample_rate: int = 48000
    audio_channels: int = 2
    video_bitrate: str = "6000k"
    audio_bitrate: str = "160k"
    rtmp_targets: list[str] = field(default_factory=list)


class EncoderThread(QThread):
    """Writes RGBA frames + PCM audio to named FIFOs consumed by ffmpeg.

    Video and audio are written by separate threads so neither FIFO waits on
    the other: ffmpeg opens and probes its inputs sequentially.

    Shutdown: stop_encoding() → writers drain to sentinel and close FIFOs →
    ffmpeg.wait(10s) → kill → unlink FIFOs.
    """

    error = pyqtSignal(str)

    def __init__(self, config: EncoderConfig, video_queue: queue.Queue,
                 audio_queue: queue.Queue, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._video_queue = video_queue
        self._audio_queue = audio_queue
        self._stop_event = threading.Event()
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._video_fd: Optional[object] = None
        self._audio_fd: Optional[object] = None

    def stop_encoding(self) -> None:
        self._stop_event.set()
        for q in (self._video_queue, self._audio_queue):
            try:
                q.put_nowait(None)
            except queue.Full:
                pass

    def _create_fifos(self) -> None:
        for path in (self._config.video_fifo, self._config.audio_fifo):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            os.mkfifo(path)

    def _unlink_fifos(self) -> None:
        for path in (self._config.video_fifo, self._config.audio_fifo):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def _build_tee_string(self) -> str:
        return "|".join(f"[f=flv]{t}" for t in self._config.rtmp_targets)

    def _build_ffmpeg_args(self) -> list[str]:
        cfg = self._config
        return [
            "ffmpeg", "-re",
            "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{cfg.width}x{cfg.height}", "-r", str(cfg.fps),
            "-i", cfg.video_fifo,
            "-f", "s16le", "-ar", str(cfg.sample_rate), "-ac", str(cfg.audio_channels),
            "-i", cfg.audio_fifo,
            # The tee muxer does not auto-select streams; map them explicitly.
            "-map", "0:v", "-map", "1:a",
            "-vf", "format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", cfg.video_bitrate,
            "-c:a", "aac", "-b:a", cfg.audio_bitrate,
            "-f", "tee", self._build_tee_string(),
        ]

    def _write_fifo(self, path: str, q: queue.Queue, name: str,
                    errors: list[Exception]) -> None:
        """Open one FIFO and stream its queue into it until a None sentinel.

        Each FIFO gets its own writer because ffmpeg opens and probes its
        inputs one at a time: it reads video data before it opens the audio
        FIFO, so the video writer must be streaming while the audio open is
        still pending.
        """
        fd = None
        try:
            fd = open(path, "wb")
            if name == "video":
                self._video_fd = fd
            else:
                self._audio_fd = fd
            while True:
                try:
                    data = q.get(timeout=0.1)
                except queue.Empty:
                    if self._stop_event.is_set():
                        break
                    continue
                if data is None:
                    break
                fd.write(data)
                fd.flush()
        except BrokenPipeError:
            pass
        except Exception as e:
            errors.append(e)
        finally:
            if fd is not None:
                try:
                    fd.close()
                except Exception:
                    pass

    def _release_blocked_opens(self) -> None:
        """Unblock writers stuck in open() once ffmpeg can no longer read."""
        for path in (self._config.video_fifo, self._config.audio_fifo):
            try:
                os.close(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                pass

    def run(self) -> None:
        writers: list[threading.Thread] = []
        writer_errors: list[Exception] = []
        try:
            self._create_fifos()

            self._ffmpeg_proc = subprocess.Popen(
                self._build_ffmpeg_args(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            writers = [
                threading.Thread(
                    target=self._write_fifo,
                    args=(self._config.video_fifo, self._video_queue, "video", writer_errors),
                    daemon=True,
                ),
                threading.Thread(
                    target=self._write_fifo,
                    args=(self._config.audio_fifo, self._audio_queue, "audio", writer_errors),
                    daemon=True,
                ),
            ]
            for t in writers:
                t.start()

            stop_deadline: Optional[float] = None
            while any(t.is_alive() for t in writers):
                if self._ffmpeg_proc.poll() is not None:
                    self._release_blocked_opens()
                elif self._stop_event.is_set():
                    # Writers may be blocked on a pipe ffmpeg stopped reading.
                    if stop_deadline is None:
                        stop_deadline = time.monotonic() + 10.0
                    elif time.monotonic() > stop_deadline:
                        self._ffmpeg_proc.kill()
                for t in writers:
                    t.join(timeout=0.1)

            if writer_errors:
                raise writer_errors[0]

            rc = self._ffmpeg_proc.poll()
            if rc not in (None, 0) and not self._stop_event.is_set():
                raise RuntimeError(f"ffmpeg exited unexpectedly with code {rc}")

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if self._ffmpeg_proc is not None:
                try:
                    self._ffmpeg_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._ffmpeg_proc.kill()
                    self._ffmpeg_proc.wait()

            self._release_blocked_opens()
            for t in writers:
                t.join(timeout=1.0)

            self._unlink_fifos()
