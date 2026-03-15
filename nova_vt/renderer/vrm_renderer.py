from __future__ import annotations

import os
import queue
import threading
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

os.environ.setdefault("EGL_PLATFORM", "surfaceless")

from nova_vt.renderer.vrm_loader import VRMLoader, MeshData
from nova_vt.tracking.provider import TrackingFrame, identity_pose


class VRMRenderer(QThread):
    """Renders VRM avatar frames via EGL headless offscreen rendering.

    Pushes RGBA numpy arrays to preview_queue (always) and
    encoder_queue (when set, i.e., in live mode).
    """

    error = pyqtSignal(str)

    def __init__(
        self,
        loader: VRMLoader,
        preview_queue: queue.Queue,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        encoder_queue: queue.Queue | None = None,
    ) -> None:
        super().__init__()
        self._loader = loader
        self._preview_q = preview_queue
        self._encoder_q = encoder_queue
        self._width = width
        self._height = height
        self._fps = fps
        self._stop_event = threading.Event()
        self._current_frame = TrackingFrame()
        self._frame_lock = threading.Lock()

    def update_tracking(self, frame: TrackingFrame) -> None:
        with self._frame_lock:
            self._current_frame = frame

    def set_encoder_queue(self, q: queue.Queue | None) -> None:
        self._encoder_q = q

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._render_loop()
        except Exception as exc:
            self.error.emit(str(exc))

    def _render_loop(self) -> None:
        import time
        import moderngl

        ctx = moderngl.create_standalone_context(backend="egl")
        fbo = ctx.simple_framebuffer((self._width, self._height), components=4)
        fbo.use()

        shader_dir = Path(__file__).parent
        prog = ctx.program(
            vertex_shader=(shader_dir / "mtoon.vert").read_text(),
            fragment_shader=(shader_dir / "mtoon.frag").read_text(),
        )

        vaos = self._build_vaos(ctx, prog)
        frame_time = 1.0 / self._fps

        while not self._stop_event.is_set():
            t0 = time.perf_counter()
            with self._frame_lock:
                tracking = self._current_frame

            self._render_frame(ctx, fbo, prog, vaos, tracking)

            raw = fbo.read(components=4)
            arr = np.frombuffer(raw, dtype=np.uint8).reshape(self._height, self._width, 4)
            arr = np.flipud(arr)

            preview = arr[::2, ::2]
            try:
                self._preview_q.put_nowait(preview)
            except queue.Full:
                pass

            if self._encoder_q is not None:
                try:
                    self._encoder_q.put_nowait(arr)
                except queue.Full:
                    pass

            elapsed = time.perf_counter() - t0
            sleep = frame_time - elapsed
            if sleep > 0:
                self._stop_event.wait(sleep)

        fbo.release()
        ctx.release()

    def _build_vaos(self, ctx, prog) -> list:
        import moderngl
        vaos = []
        for mesh in self._loader.meshes:
            vbo_pos = ctx.buffer(mesh.positions.tobytes())
            vbo_nor = ctx.buffer(mesh.normals.tobytes())
            vbo_uv = ctx.buffer(mesh.uvs.tobytes())
            n = mesh.positions.shape[0]
            if self._loader.skin:
                vbo_joints = ctx.buffer(self._loader.skin.joints.astype(np.int32).tobytes())
                vbo_weights = ctx.buffer(self._loader.skin.weights.tobytes())
            else:
                vbo_joints = ctx.buffer(np.zeros((n, 4), dtype=np.int32).tobytes())
                vbo_weights = ctx.buffer(np.zeros((n, 4), dtype=np.float32).tobytes())
            ibo = ctx.buffer(mesh.indices.astype(np.uint32).tobytes())
            vao = ctx.vertex_array(
                prog,
                [
                    (vbo_pos, "3f", "in_position"),
                    (vbo_nor, "3f", "in_normal"),
                    (vbo_uv, "2f", "in_uv"),
                    (vbo_joints, "4i", "in_joints"),
                    (vbo_weights, "4f", "in_weights"),
                ],
                ibo,
            )
            vaos.append(vao)
        return vaos

    def _render_frame(self, ctx, fbo, prog, vaos, tracking: TrackingFrame) -> None:
        import moderngl

        ctx.clear(0.0, 0.0, 0.0, 0.0)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        mvp = _ortho_mvp(self._width, self._height)
        if "u_mvp" in prog:
            prog["u_mvp"].write(mvp.astype(np.float32).tobytes())
        if "u_light_dir" in prog:
            prog["u_light_dir"].value = (0.0, -1.0, -1.0)
        if "u_lit_color" in prog:
            prog["u_lit_color"].value = (0.8, 0.6, 0.9, 1.0)
        if "u_shade_color" in prog:
            prog["u_shade_color"].value = (0.4, 0.2, 0.6, 1.0)
        if "u_shade_shift" in prog:
            prog["u_shade_shift"].value = 0.0
        if "u_shade_toony" in prog:
            prog["u_shade_toony"].value = 0.9
        if "u_alpha_cutoff" in prog:
            prog["u_alpha_cutoff"].value = 0.0
        if "u_has_texture" in prog:
            prog["u_has_texture"].value = 0

        joint_mats = self._loader.apply_pose(tracking.pose)
        if "u_joint_matrices" in prog and joint_mats is not None:
            flat = joint_mats.flatten().astype(np.float32)
            padded = np.zeros(128 * 16, dtype=np.float32)
            padded[:len(flat)] = flat
            prog["u_joint_matrices"].write(padded.tobytes())

        for vao in vaos:
            vao.render(moderngl.TRIANGLES)


def _ortho_mvp(width: int, height: int) -> np.ndarray:
    near, far = -10.0, 10.0
    l, r = -1.0, 1.0
    b, t = -1.0, 1.0
    m = np.array([
        [2/(r-l),   0,          0,          -(r+l)/(r-l)],
        [0,         2/(t-b),    0,          -(t+b)/(t-b)],
        [0,         0,         -2/(far-near), -(far+near)/(far-near)],
        [0,         0,          0,           1],
    ], dtype=np.float32)
    return m
