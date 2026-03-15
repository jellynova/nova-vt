import os
import pytest

os.environ.setdefault("EGL_PLATFORM", "surfaceless")

try:
    import moderngl
    HAS_MODERNGL = True
except ImportError:
    HAS_MODERNGL = False

from pathlib import Path

SHADER_DIR = Path(__file__).parents[3] / "nova_vt" / "renderer"


@pytest.mark.skipif(not HAS_MODERNGL, reason="moderngl not installed")
def test_shaders_compile():
    ctx = moderngl.create_standalone_context(backend="egl")
    vert = (SHADER_DIR / "mtoon.vert").read_text()
    frag = (SHADER_DIR / "mtoon.frag").read_text()
    prog = ctx.program(vertex_shader=vert, fragment_shader=frag)
    assert prog is not None
    ctx.release()
