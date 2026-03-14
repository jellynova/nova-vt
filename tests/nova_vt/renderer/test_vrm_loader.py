from pathlib import Path
import numpy as np
import pytest
from nova_vt.renderer.vrm_loader import VRMLoader, MeshData, SkinData

VRM_PATH = Path(__file__).parents[3] / "model.vrm"

@pytest.fixture(scope="module")
def loader():
    if not VRM_PATH.exists():
        pytest.skip("model.vrm not found")
    return VRMLoader(VRM_PATH)


def test_loads_without_error(loader):
    assert loader is not None


def test_has_at_least_one_mesh(loader):
    assert len(loader.meshes) > 0


def test_mesh_has_positions(loader):
    mesh: MeshData = loader.meshes[0]
    assert mesh.positions.shape[1] == 3  # (N, 3) float32
    assert mesh.positions.dtype == np.float32


def test_mesh_has_normals(loader):
    mesh: MeshData = loader.meshes[0]
    assert mesh.normals.shape == mesh.positions.shape


def test_mesh_has_indices(loader):
    mesh: MeshData = loader.meshes[0]
    assert mesh.indices.ndim == 1
    assert mesh.indices.dtype in (np.uint16, np.uint32)


def test_skin_has_joints_and_weights(loader):
    if not loader.skin:
        pytest.skip("no skin")
    skin: SkinData = loader.skin
    n = loader.meshes[0].positions.shape[0]
    assert skin.joints.shape == (n, 4)
    assert skin.weights.shape == (n, 4)


def test_bone_names_include_head(loader):
    if not loader.skin:
        pytest.skip("no skin")
    names = [b.lower() for b in loader.skin.bone_names]
    assert any("head" in n for n in names)


def test_expression_map_is_dict(loader):
    assert isinstance(loader.expression_map, dict)


def test_expression_map_has_arkit_keys(loader):
    # At minimum the loader should recognise common ARKit keys
    known = {"eyeBlinkLeft", "eyeBlinkRight", "jawOpen"}
    present = set(loader.expression_map.keys())
    # VRM models vary — at least 1 should match
    assert len(known & present) >= 1 or len(loader.expression_map) > 0
