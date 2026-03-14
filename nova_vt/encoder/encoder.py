from __future__ import annotations

import os
import queue
import subprocess
import threading
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

    Shutdown: stop_encoding() → close FIFOs → ffmpeg.wait(10s) → kill → unlink FIFOs.
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
            "-vf", "format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", cfg.video_bitrate,
            "-c:a", "aac", "-b:a", cfg.audio_bitrate,
            "-f", "tee", self._build_tee_string(),
        ]

    def run(self) -> None:
        try:
            self._create_fifos()
            video_fd_holder: list[Optional[object]] = [None]
            audio_fd_holder: list[Optional[object]] = [None]
            open_error: list[Optional[Exception]] = [None]

            def _open_video():
                try:
                    video_fd_holder[0] = open(self._config.video_fifo, "wb")
                except Exception as e:
                    open_error[0] = e

            def _open_audio():
                try:
                    audio_fd_holder[0] = open(self._config.audio_fifo, "wb")
                except Exception as e:
                    open_error[0] = e

            open_threads = [
                threading.Thread(target=_open_video, daemon=True),
                threading.Thread(target=_open_audio, daemon=True),
            ]
            for t in open_threads:
                t.start()

            self._ffmpeg_proc = subprocess.Popen(
                self._build_ffmpeg_args(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for t in open_threads:
                t.join(timeout=10.0)

            if open_error[0] is not None:
                raise open_error[0]

            video_fd = video_fd_holder[0]
            audio_fd = audio_fd_holder[0]
            self._video_fd = video_fd
            self._audio_fd = audio_fd

            if video_fd is None or audio_fd is None:
                raise RuntimeError("Failed to open FIFO file descriptors")

            while not self._stop_event.is_set():
                try:
                    frame = self._video_queue.get(timeout=0.1)
                    if frame is None:
                        break
                    video_fd.write(frame)
                    video_fd.flush()
                except queue.Empty:
                    continue
                except BrokenPipeError:
                    break

                try:
                    chunk = self._audio_queue.get_nowait()
                    if chunk is None:
                        break
                    audio_fd.write(chunk)
                    audio_fd.flush()
                except queue.Empty:
                    pass
                except BrokenPipeError:
                    break

            while True:
                try:
                    chunk = self._audio_queue.get_nowait()
                    if chunk is None or audio_fd is None:
                        break
                    audio_fd.write(chunk)
                    audio_fd.flush()
                except queue.Empty:
                    break

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            for fd in (self._video_fd, self._audio_fd):
                if fd is not None:
                    try:
                        fd.close()
                    except Exception:
                        pass

            if self._ffmpeg_proc is not None:
                try:
                    self._ffmpeg_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._ffmpeg_proc.kill()
                    self._ffmpeg_proc.wait()

            self._unlink_fifos()
