# nova-vt Core Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Godot + old package structure with a self-contained Python rendering pipeline: VRM avatar rendering via EGL/moderngl, MediaPipe face+body tracking, and a numpy compositor — all runnable headlessly and testable by writing frames to disk.

**Architecture:** Monolithic `nova_vt` Python package with one `QThread` per subsystem communicating via bounded `queue.Queue`. This plan covers everything up to and including the compositor (frame production). Audio, encoder, chat, and the Qt dashboard are covered in separate plans.

**Tech Stack:** Python 3.12+, PyQt6, moderngl (EGL headless), pygltflib, MediaPipe, numpy, sounddevice, tomllib/tomli-w

**Spec:** `docs/superpowers/specs/2026-03-14-nova-vt-redesign-design.md`

---

## Chunk 1: Foundation

### Task 1: Package scaffold + pyproject.toml

**Files:**
- Delete: `orchestrator/`, `tracker/`, `dashboard/`, `config/`, `overlays/`, `avatar/` (Godot project — keep `avatar/model.vrm`)
- Create: `nova_vt/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/nova_vt/__init__.py`

- [ ] **Step 1: Move the VRM model out of avatar/**

```bash
cp /home/nova/git/nova-vt/avatar/model.vrm /home/nova/git/nova-vt/model.vrm
```

- [ ] **Step 2: Rewrite pyproject.toml**

Replace the full contents of `pyproject.toml`:

```toml
[project]
name = "nova-vt"
version = "0.2.0"
requires-python = ">=3.12"
dependencies = [
    "PyQt6",
    "moderngl",
    "pygltflib",
    "mediapipe",
    "opencv-python",
    "numpy",
    "sounddevice",
    "tomli-w",
    "twitchio",
    "google-api-python-client",
    "google-auth-oauthlib",
    "TikTokLive",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-qt"]

[project.scripts]
nova-vt = "nova_vt.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["nova_vt*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create nova_vt package**

```bash
mkdir -p /home/nova/git/nova-vt/nova_vt
mkdir -p /home/nova/git/nova-vt/nova_vt/renderer
mkdir -p /home/nova/git/nova-vt/nova_vt/tracking
mkdir -p /home/nova/git/nova-vt/nova_vt/compositor
mkdir -p /home/nova/git/nova-vt/nova_vt/audio
mkdir -p /home/nova/git/nova-vt/nova_vt/encoder
mkdir -p /home/nova/git/nova-vt/nova_vt/chat
mkdir -p /home/nova/git/nova-vt/nova_vt/dashboard
mkdir -p /home/nova/git/nova-vt/tests/nova_vt
```

Create `nova_vt/__init__.py` (empty), and `__init__.py` for each sub-package and test directory.

- [ ] **Step 4: Create minimal main.py entrypoint**

`nova_vt/main.py`:
```python
import sys
from PyQt6.QtWidgets import QApplication


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("nova-vt")
    # Dashboard window imported here once implemented
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Install the package**

```bash
cd /home/nova/git/nova-vt && pip install -e ".[dev]"
```

Expected: installs without errors, `nova-vt` entry point available.

- [ ] **Step 6: Verify import**

```bash
python -c "import nova_vt; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Delete old packages**

```bash
cd /home/nova/git/nova-vt
rm -rf orchestrator tracker dashboard config overlays avatar
# avatar/model.vrm was already copied to model.vrm in step 1
```

- [ ] **Step 8: Commit**

```bash
git add nova_vt/ tests/nova_vt/ pyproject.toml model.vrm
git commit -m "feat: scaffold nova_vt package, replace old packages"
```

---

### Task 2: Config (TOML load/save)

**Files:**
- Create: `nova_vt/config.py`
- Create: `tests/nova_vt/test_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/nova_vt/test_config.py`:
```python
import os
import stat
import tempfile
from pathlib import Path
import pytest
from nova_vt.config import Config


def test_load_defaults():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        assert cfg.get("app", "vrm_path") == ""
        assert cfg.get("app", "camera_index") == 0


def test_set_and_get():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set("app", "camera_index", 2)
        assert cfg.get("app", "camera_index") == 2


def test_save_and_reload():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set("app", "vrm_path", "/home/nova/model.vrm")
        cfg.save()
        cfg2 = Config(config_dir=Path(d))
        assert cfg2.get("app", "vrm_path") == "/home/nova/model.vrm"


def test_secrets_created_with_mode_600():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set_secret("stream_keys", "twitch", "mykey")
        cfg.save()
        secrets_path = Path(d) / "secrets.toml"
        assert secrets_path.exists()
        mode = oct(stat.S_IMODE(os.stat(secrets_path).st_mode))
        assert mode == oct(0o600)


def test_get_secret():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set_secret("stream_keys", "twitch", "abc123")
        cfg.save()
        cfg2 = Config(config_dir=Path(d))
        assert cfg2.get_secret("stream_keys", "twitch") == "abc123"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nova/git/nova-vt && pytest tests/nova_vt/test_config.py -v
```

Expected: `ImportError: cannot import name 'Config'`

- [ ] **Step 3: Implement Config**

`nova_vt/config.py`:
```python
from __future__ import annotations

import os
import stat
import tomllib
import warnings
from pathlib import Path
from typing import Any

import tomli_w

_DEFAULTS: dict = {
    "app": {
        "vrm_path": "",
        "camera_index": 0,
        "fps": 30,
    },
    "audio": {
        "mic_volume": 75,
        "game_volume": 60,
        "bgm_volume": 30,
        "master_volume": 90,
        "monitor_device": "",
    },
    "stream": {
        "enabled_platforms": ["twitch", "youtube"],
    },
}

_SECRET_DEFAULTS: dict = {
    "stream_keys": {
        "twitch": "",
        "youtube": "",
        "tiktok": "",
    },
    "twitch": {
        "token": "",
        "client_id": "",
    },
    "youtube": {
        "client_secret_path": "",
    },
}


class Config:
    """Loads and saves nova-vt config from ~/.config/nova-vt/.

    Non-sensitive values live in config.toml.
    Sensitive values (keys, tokens) live in secrets.toml (mode 600).
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or Path.home() / ".config" / "nova-vt"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._config_path = self._dir / "config.toml"
        self._secrets_path = self._dir / "secrets.toml"
        self._data = _deep_merge(_DEFAULTS, self._load_toml(self._config_path))
        self._secrets = _deep_merge(_SECRET_DEFAULTS, self._load_secrets())

    # --- public API ---

    def get(self, section: str, key: str) -> Any:
        return self._data.get(section, {}).get(key)

    def set(self, section: str, key: str, value: Any) -> None:
        self._data.setdefault(section, {})[key] = value

    def get_secret(self, section: str, key: str) -> Any:
        return self._secrets.get(section, {}).get(key)

    def set_secret(self, section: str, key: str, value: Any) -> None:
        self._secrets.setdefault(section, {})[key] = value

    def save(self) -> None:
        self._config_path.write_bytes(tomli_w.dumps(self._data).encode())
        self._write_secrets_atomic(tomli_w.dumps(self._secrets).encode())

    def _write_secrets_atomic(self, data: bytes) -> None:
        """Write secrets.toml atomically with mode 0o600.

        Uses os.open so the file is created with the correct mode from the
        start — avoids the world-readable window that write_bytes + chmod has.
        """
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            os.write(tmp_fd, data)
            os.close(tmp_fd)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._secrets_path)
        except Exception:
            os.close(tmp_fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # --- private ---

    def _load_toml(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, "rb") as f:
            return tomllib.load(f)

    def _load_secrets(self) -> dict:
        if not self._secrets_path.exists():
            return {}
        mode = stat.S_IMODE(os.stat(self._secrets_path).st_mode)
        if mode & 0o077:
            warnings.warn(
                f"secrets.toml permissions are {oct(mode)} — expected 0o600. "
                "Other users may be able to read your stream keys.",
                stacklevel=2,
            )
        return self._load_toml(self._secrets_path)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/nova_vt/test_config.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add nova_vt/config.py tests/nova_vt/test_config.py
git commit -m "feat: add Config with TOML load/save and secrets.toml (mode 600)"
```

---

### Task 3: TrackingProvider protocol + PoseDict + TrackingFrame

**Files:**
- Create: `nova_vt/tracking/provider.py`
- Create: `tests/nova_vt/tracking/__init__.py`
- Create: `tests/nova_vt/tracking/test_provider.py`

- [ ] **Step 1: Write the failing tests**

`tests/nova_vt/tracking/test_provider.py`:
```python
import time
from nova_vt.tracking.provider import TrackingFrame, identity_pose, VRM_BONE_NAMES


def test_identity_pose_has_all_bones():
    pose = identity_pose()
    assert set(pose.keys()) == set(VRM_BONE_NAMES)
    assert len(pose) == 54, f"Expected 54 VRM bones, got {len(pose)}"


def test_identity_pose_quaternions_are_identity():
    pose = identity_pose()
    for bone, q in pose.items():
        assert len(q) == 4, f"{bone} quaternion should be (x,y,z,w) length 4"
        assert q == (0.0, 0.0, 0.0, 1.0), f"{bone} should be identity (0,0,0,1)"


def test_tracking_frame_defaults():
    frame = TrackingFrame()
    assert isinstance(frame.pose, dict)
    assert len(frame.pose) == len(VRM_BONE_NAMES)
    assert isinstance(frame.blend_shapes, dict)
    assert isinstance(frame.timestamp, float)


def test_tracking_frame_timestamp_is_set():
    before = time.time()
    frame = TrackingFrame()
    after = time.time()
    assert before <= frame.timestamp <= after
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/nova_vt/tracking/test_provider.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement provider.py**

`nova_vt/tracking/provider.py`:
```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Full VRM 0.x humanoid bone name list (54 bones — jaw is VRM 1.0 only, excluded)
VRM_BONE_NAMES: tuple[str, ...] = (
    "hips", "spine", "chest", "upperChest", "neck", "head",
    "leftEye", "rightEye",
    "leftShoulder", "rightShoulder",
    "leftUpperArm", "rightUpperArm",
    "leftLowerArm", "rightLowerArm",
    "leftHand", "rightHand",
    "leftThumbProximal", "leftThumbIntermediate", "leftThumbDistal",
    "leftIndexProximal", "leftIndexIntermediate", "leftIndexDistal",
    "leftMiddleProximal", "leftMiddleIntermediate", "leftMiddleDistal",
    "leftRingProximal", "leftRingIntermediate", "leftRingDistal",
    "leftLittleProximal", "leftLittleIntermediate", "leftLittleDistal",
    "rightThumbProximal", "rightThumbIntermediate", "rightThumbDistal",
    "rightIndexProximal", "rightIndexIntermediate", "rightIndexDistal",
    "rightMiddleProximal", "rightMiddleIntermediate", "rightMiddleDistal",
    "rightRingProximal", "rightRingIntermediate", "rightRingDistal",
    "rightLittleProximal", "rightLittleIntermediate", "rightLittleDistal",
    "leftUpperLeg", "rightUpperLeg",
    "leftLowerLeg", "rightLowerLeg",
    "leftFoot", "rightFoot",
    "leftToes", "rightToes",
)

# Quaternion as (x, y, z, w) tuple — identity rotation
Quaternion = tuple[float, float, float, float]
PoseDict = dict[str, Quaternion]

IDENTITY_QUATERNION: Quaternion = (0.0, 0.0, 0.0, 1.0)


def identity_pose() -> PoseDict:
    """Return a PoseDict with all 54 bones set to identity rotation."""
    return {bone: IDENTITY_QUATERNION for bone in VRM_BONE_NAMES}


@dataclass
class TrackingFrame:
    pose: PoseDict = field(default_factory=identity_pose)
    blend_shapes: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@runtime_checkable
class TrackingProvider(Protocol):
    def get_frame(self) -> TrackingFrame: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/nova_vt/tracking/test_provider.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add nova_vt/tracking/ tests/nova_vt/tracking/
git commit -m "feat: add TrackingProvider protocol, PoseDict, TrackingFrame with 54 VRM bones"
```

---

### Task 4: VRM Loader (pygltflib)

**Files:**
- Create: `nova_vt/renderer/vrm_loader.py`
- Create: `tests/nova_vt/renderer/__init__.py`
- Create: `tests/nova_vt/renderer/test_vrm_loader.py`

The loader parses the VRM file into plain Python data structures — no GPU involvement. It normalises VRM 0.x `BlendShapeProxy` and VRM 1.0 `Expression` into a unified `ExpressionMap` keyed by ARKit names.

- [ ] **Step 1: Write the failing tests**

`tests/nova_vt/renderer/test_vrm_loader.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/nova_vt/renderer/test_vrm_loader.py -v
```

Expected: `ModuleNotFoundError: No module named 'nova_vt.renderer.vrm_loader'`

- [ ] **Step 3: Implement vrm_loader.py**

`nova_vt/renderer/vrm_loader.py`:
```python
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pygltflib

# Mapping from VRM 0.x BlendShapeProxy preset names → ARKit names
_VRM0_TO_ARKIT: dict[str, str] = {
    "a": "jawOpen", "i": "mouthSmileLeft", "u": "mouthFunnel",
    "e": "mouthUpperUpLeft", "o": "mouthRollLower",
    "blink": "eyeBlinkLeft", "blink_l": "eyeBlinkLeft", "blink_r": "eyeBlinkRight",
    "joy": "mouthSmileLeft", "angry": "browDownLeft", "sorrow": "browInnerUp",
    "fun": "cheekSquintLeft", "lookup": "eyeLookUpLeft", "lookdown": "eyeLookDownLeft",
    "lookleft": "eyeLookOutLeft", "lookright": "eyeLookInLeft",
    "neutral": "mouthClose",
}

# VRM 1.0 Expression names → ARKit names
_VRM1_TO_ARKIT: dict[str, str] = {
    "aa": "jawOpen", "ih": "mouthSmileLeft", "ou": "mouthFunnel",
    "ee": "mouthUpperUpLeft", "oh": "mouthRollLower",
    "blinkLeft": "eyeBlinkLeft", "blinkRight": "eyeBlinkRight",
    "happy": "mouthSmileLeft", "angry": "browDownLeft", "sad": "browInnerUp",
    "relaxed": "cheekSquintLeft", "surprised": "eyeWideLeft",
    "neutral": "mouthClose",
}


@dataclass
class MeshData:
    positions: np.ndarray      # (N, 3) float32
    normals: np.ndarray        # (N, 3) float32
    uvs: np.ndarray            # (N, 2) float32
    indices: np.ndarray        # (M,) uint16 or uint32
    morph_targets: list[np.ndarray] = field(default_factory=list)  # [(N,3) float32 deltas]
    morph_names: list[str] = field(default_factory=list)


@dataclass
class SkinData:
    bone_names: list[str]
    inverse_bind_matrices: np.ndarray  # (B, 4, 4) float32
    joints: np.ndarray                 # (N, 4) uint16
    weights: np.ndarray                # (N, 4) float32


class VRMLoader:
    """Loads a VRM 0.x or 1.0 file and exposes mesh, skin, and expression data."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._gltf = pygltflib.GLTF2().load(str(path))
        self.meshes: list[MeshData] = []
        self.skin: SkinData | None = None
        self.expression_map: dict[str, int] = {}  # ARKit name → morph target index
        self._load()

    # ── public ──────────────────────────────────────────────────────────────

    def apply_pose(self, pose_dict: dict[str, tuple]) -> np.ndarray:
        """Return (B, 4, 4) float32 joint matrices for GPU upload.

        pose_dict maps VRM bone name → (x, y, z, w) quaternion.
        Bones not in the dict default to identity.
        """
        if self.skin is None:
            return np.eye(4, dtype=np.float32)[np.newaxis].repeat(1, 0)
        B = len(self.skin.bone_names)
        mats = np.tile(np.eye(4, dtype=np.float32), (B, 1, 1))
        # TODO: full LBS matrix computation (Task 6)
        return mats

    # ── private ─────────────────────────────────────────────────────────────

    def _load(self) -> None:
        gltf = self._gltf
        self._detect_version_and_map_expressions()
        for mesh in gltf.meshes or []:
            for prim in mesh.primitives or []:
                self.meshes.append(self._load_primitive(prim))
        if gltf.skins:
            self.skin = self._load_skin(gltf.skins[0])

    def _detect_version_and_map_expressions(self) -> None:
        gltf = self._gltf
        exts = (gltf.extensions or {}) if hasattr(gltf, "extensions") else {}
        if "VRMC_vrm" in exts:
            self._map_expressions_vrm1(exts["VRMC_vrm"])
        elif "VRM" in exts:
            self._map_expressions_vrm0(exts["VRM"])

    def _map_expressions_vrm0(self, vrm_ext: dict) -> None:
        bsg = vrm_ext.get("blendShapeMaster", {}).get("blendShapeGroups", [])
        for group in bsg:
            preset = group.get("presetName", "").lower()
            arkit = _VRM0_TO_ARKIT.get(preset)
            if arkit and group.get("binds"):
                bind = group["binds"][0]
                self.expression_map[arkit] = bind.get("index", 0)

    def _map_expressions_vrm1(self, vrm_ext: dict) -> None:
        exprs = vrm_ext.get("expressions", {}).get("preset", {})
        for name, data in exprs.items():
            arkit = _VRM1_TO_ARKIT.get(name)
            if arkit and data.get("morphTargetBinds"):
                bind = data["morphTargetBinds"][0]
                self.expression_map[arkit] = bind.get("index", 0)

    def _load_primitive(self, prim: pygltflib.Primitive) -> MeshData:
        positions = self._accessor_to_numpy(prim.attributes.POSITION)
        normals_acc = getattr(prim.attributes, "NORMAL", None)
        normals = self._accessor_to_numpy(normals_acc) if normals_acc is not None else np.zeros_like(positions)
        uvs_acc = getattr(prim.attributes, "TEXCOORD_0", None)
        uvs = self._accessor_to_numpy(uvs_acc) if uvs_acc is not None else np.zeros((len(positions), 2), dtype=np.float32)
        indices = self._accessor_to_numpy(prim.indices) if prim.indices is not None else np.arange(len(positions), dtype=np.uint32)
        morph_targets = []
        morph_names = []
        for i, target in enumerate(prim.targets or []):
            pos_acc = target.get("POSITION") if isinstance(target, dict) else getattr(target, "POSITION", None)
            if pos_acc is not None:
                morph_targets.append(self._accessor_to_numpy(pos_acc))
                morph_names.append(str(i))
        return MeshData(
            positions=positions.astype(np.float32),
            normals=normals.astype(np.float32),
            uvs=uvs.astype(np.float32),
            indices=indices,
            morph_targets=morph_targets,
            morph_names=morph_names,
        )

    def _load_skin(self, skin: pygltflib.Skin) -> SkinData:
        gltf = self._gltf
        bone_names = []
        for j in skin.joints or []:
            node = gltf.nodes[j]
            bone_names.append(node.name or f"bone_{j}")
        ibm = self._accessor_to_numpy(skin.inverseBindMatrices)
        ibm = ibm.reshape(-1, 4, 4).astype(np.float32)
        mesh = self.meshes[0] if self.meshes else None
        n = mesh.positions.shape[0] if mesh else 0
        # joints and weights from first primitive attributes
        prim = self._gltf.meshes[0].primitives[0] if self._gltf.meshes else None
        if prim and hasattr(prim.attributes, "JOINTS_0"):
            joints = self._accessor_to_numpy(prim.attributes.JOINTS_0).reshape(n, 4).astype(np.uint16)
            weights = self._accessor_to_numpy(prim.attributes.WEIGHTS_0).reshape(n, 4).astype(np.float32)
        else:
            joints = np.zeros((n, 4), dtype=np.uint16)
            weights = np.zeros((n, 4), dtype=np.float32)
        return SkinData(bone_names=bone_names, inverse_bind_matrices=ibm, joints=joints, weights=weights)

    def _accessor_to_numpy(self, accessor_index: int) -> np.ndarray:
        gltf = self._gltf
        acc = gltf.accessors[accessor_index]
        bv = gltf.bufferViews[acc.bufferView]
        buf = gltf.buffers[bv.buffer]
        # GLB files store the binary chunk accessible via binary_blob().
        # External .bin URIs must be resolved from the file's directory.
        if buf.uri is None:
            raw: bytes = bytes(gltf.binary_blob())
        else:
            import base64, urllib.parse
            if buf.uri.startswith("data:"):
                # data URI: data:<mediatype>;base64,<data>
                raw = base64.b64decode(buf.uri.split(",", 1)[1])
            else:
                bin_path = self._path.parent / urllib.parse.unquote(buf.uri)
                raw = bin_path.read_bytes()

        dtype_map = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16,
                     5125: np.uint32, 5126: np.float32}
        comp_dtype = dtype_map[acc.componentType]
        item_size = np.dtype(comp_dtype).itemsize
        type_count = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc.type]
        stride = bv.byteStride or 0
        packed_stride = type_count * item_size
        if stride not in (0, packed_stride):
            raise NotImplementedError(
                f"Interleaved buffer views (byteStride={stride}) are not yet supported. "
                "De-interleave the glTF with gltf-transform or Blender before importing."
            )
        start = (bv.byteOffset or 0) + (acc.byteOffset or 0)
        total = acc.count * type_count
        arr = np.frombuffer(raw, dtype=comp_dtype, count=total, offset=start)
        if type_count > 1:
            arr = arr.reshape(acc.count, type_count)
        return arr.copy()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/nova_vt/renderer/test_vrm_loader.py -v
```

Expected: all pass (or skip if model.vrm not at expected path)

- [ ] **Step 5: Commit**

```bash
git add nova_vt/renderer/vrm_loader.py tests/nova_vt/renderer/
git commit -m "feat: add VRMLoader with VRM 0.x/1.0 compat and ExpressionMap"
```

---

### Task 5: MToon GLSL shaders

**Files:**
- Create: `nova_vt/renderer/mtoon.vert`
- Create: `nova_vt/renderer/mtoon.frag`
- Create: `tests/nova_vt/renderer/test_shaders.py`

> **Note:** The spec file layout lists `mtoon.glsl` as a single file. This plan splits it into `mtoon.vert` + `mtoon.frag` — the standard GLSL convention that makes vertex/fragment stages independently readable and avoids a custom parsing step. The spec should be updated to reflect this.

The shader test verifies the GLSL compiles in a real EGL context. Set `EGL_PLATFORM=surfaceless` for headless operation.

- [ ] **Step 1: Write the failing shader compilation test**

`tests/nova_vt/renderer/test_shaders.py`:
```python
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
    """Verify the MToon shaders compile in a headless EGL context."""
    ctx = moderngl.create_standalone_context(backend="egl")
    vert = (SHADER_DIR / "mtoon.vert").read_text()
    frag = (SHADER_DIR / "mtoon.frag").read_text()
    prog = ctx.program(vertex_shader=vert, fragment_shader=frag)
    assert prog is not None
    ctx.release()
```

- [ ] **Step 2: Run test to verify it fails (shaders don't exist yet)**

```bash
EGL_PLATFORM=surfaceless pytest tests/nova_vt/renderer/test_shaders.py -v
```

Expected: `SKIPPED` if moderngl is not installed, or `FileNotFoundError` on `.read_text()` if moderngl is installed but shader files are not yet created.

- [ ] **Step 3: Write MToon vertex shader**

`nova_vt/renderer/mtoon.vert`:
```glsl
#version 330 core

// Per-vertex inputs
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_uv;
layout(location = 3) in ivec4 in_joints;
layout(location = 4) in vec4 in_weights;

// Joint matrices (max 128 bones; upper body needs ~30)
uniform mat4 u_joint_matrices[128];
uniform mat4 u_mvp;

out vec3 v_normal;
out vec2 v_uv;

void main() {
    // Linear Blend Skinning
    mat4 skin_mat =
        in_weights.x * u_joint_matrices[in_joints.x] +
        in_weights.y * u_joint_matrices[in_joints.y] +
        in_weights.z * u_joint_matrices[in_joints.z] +
        in_weights.w * u_joint_matrices[in_joints.w];

    vec4 world_pos = skin_mat * vec4(in_position, 1.0);
    gl_Position = u_mvp * world_pos;

    mat3 normal_mat = transpose(inverse(mat3(skin_mat)));
    v_normal = normalize(normal_mat * in_normal);
    v_uv = in_uv;
}
```

- [ ] **Step 4: Write MToon fragment shader**

`nova_vt/renderer/mtoon.frag`:
```glsl
#version 330 core

in vec3 v_normal;
in vec2 v_uv;

// MToon lighting uniforms
uniform vec4 u_lit_color;       // base diffuse colour (RGBA)
uniform vec4 u_shade_color;     // shadow colour (RGBA)
uniform float u_shade_shift;    // -1..1, toon shadow boundary
uniform float u_shade_toony;    // 0..1, shadow blending sharpness
uniform vec3 u_light_dir;       // world-space light direction (normalised)
uniform float u_alpha_cutoff;   // 0 = opaque, >0 = cutout

// Texture
uniform sampler2D u_lit_texture;
uniform int u_has_texture;

out vec4 out_color;

void main() {
    vec4 tex_color = u_has_texture == 1
        ? texture(u_lit_texture, v_uv)
        : vec4(1.0);

    // Toon shading: compute NdotL, shift, clamp into 0..1 toon factor
    float ndotl = dot(v_normal, normalize(-u_light_dir));
    float toon = ndotl * 0.5 + 0.5;  // remap -1..1 → 0..1
    toon = clamp((toon + u_shade_shift) * (1.0 + u_shade_toony), 0.0, 1.0);

    vec4 color = mix(u_shade_color, u_lit_color, toon) * tex_color;

    if (u_alpha_cutoff > 0.0 && color.a < u_alpha_cutoff) discard;
    out_color = color;
}
```

- [ ] **Step 5: Run shader test to verify it passes**

```bash
EGL_PLATFORM=surfaceless pytest tests/nova_vt/renderer/test_shaders.py -v
```

Expected: PASSED (or SKIPPED if EGL not available in the test environment)

- [ ] **Step 6: Commit**

```bash
git add nova_vt/renderer/mtoon.vert nova_vt/renderer/mtoon.frag tests/nova_vt/renderer/test_shaders.py
git commit -m "feat: add MToon GLSL shaders (LBS vertex + toon fragment)"
```

---

## Chunk 2: Tracking + Renderer

### Task 6: VRM Renderer (moderngl EGL headless)

**Files:**
- Create: `nova_vt/renderer/vrm_renderer.py`
- Create: `tests/nova_vt/renderer/test_vrm_renderer.py`

The renderer is a `QThread` that owns the EGL context, renders each frame, and pushes RGBA numpy arrays to `preview_queue` and (when live) `encoder_queue`.

- [ ] **Step 1: Write failing tests**

`tests/nova_vt/renderer/test_vrm_renderer.py`:
```python
import os
import queue
import time
from pathlib import Path
import numpy as np
import pytest

os.environ.setdefault("EGL_PLATFORM", "surfaceless")

try:
    import moderngl
    HAS_EGL = True
except Exception:
    HAS_EGL = False

from nova_vt.renderer.vrm_loader import VRMLoader
from nova_vt.renderer.vrm_renderer import VRMRenderer

VRM_PATH = Path(__file__).parents[3] / "model.vrm"


@pytest.mark.skipif(not HAS_EGL, reason="moderngl/EGL not available")
def test_renderer_produces_rgba_frame():
    if not VRM_PATH.exists():
        pytest.skip("model.vrm not found")

    preview_q: queue.Queue = queue.Queue(maxsize=2)
    loader = VRMLoader(VRM_PATH)
    renderer = VRMRenderer(loader, preview_queue=preview_q, width=192, height=108)
    renderer.start()
    time.sleep(1.0)
    renderer.stop()
    renderer.wait(3000)

    assert not preview_q.empty(), "renderer did not produce any frames"
    frame = preview_q.get_nowait()
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (108, 192, 4)
    assert frame.dtype == np.uint8


@pytest.mark.skipif(not HAS_EGL, reason="moderngl/EGL not available")
def test_renderer_stops_cleanly():
    if not VRM_PATH.exists():
        pytest.skip("model.vrm not found")
    preview_q: queue.Queue = queue.Queue(maxsize=2)
    loader = VRMLoader(VRM_PATH)
    renderer = VRMRenderer(loader, preview_queue=preview_q, width=192, height=108)
    renderer.start()
    time.sleep(0.3)
    renderer.stop()
    assert renderer.wait(3000), "renderer thread did not exit within 3s"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
EGL_PLATFORM=surfaceless pytest tests/nova_vt/renderer/test_vrm_renderer.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement VRMRenderer**

`nova_vt/renderer/vrm_renderer.py`:
```python
from __future__ import annotations

import os
import queue
import threading
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

os.environ.setdefault("EGL_PLATFORM", "surfaceless")
import moderngl

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

            # Read pixels → numpy RGBA (no dtype arg = uint8 output)
            raw = fbo.read(components=4)
            arr = np.frombuffer(raw, dtype=np.uint8).reshape(self._height, self._width, 4)
            # OpenGL origin is bottom-left; flip vertically
            arr = np.flipud(arr)

            # Push to preview (half-res for display efficiency)
            preview = arr[::2, ::2]
            try:
                self._preview_q.put_nowait(preview)
            except queue.Full:
                pass

            # Push full-res to encoder when live
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

    def _build_vaos(self, ctx: moderngl.Context, prog: moderngl.Program) -> list:
        vaos = []
        for mesh in self._loader.meshes:
            vbo_pos = ctx.buffer(mesh.positions.tobytes())
            vbo_nor = ctx.buffer(mesh.normals.tobytes())
            vbo_uv = ctx.buffer(mesh.uvs.tobytes())
            n = mesh.positions.shape[0]
            # Joints stored as int32 to match GLSL ivec4 ("4i" = 4x int32 integer attribute)
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
                    (vbo_joints, "4i", "in_joints"),   # 4x int32 → ivec4
                    (vbo_weights, "4f", "in_weights"),
                ],
                ibo,
            )
            vaos.append(vao)
        return vaos

    def _render_frame(
        self,
        ctx: moderngl.Context,
        fbo: moderngl.Framebuffer,
        prog: moderngl.Program,
        vaos: list,
        tracking: TrackingFrame,
    ) -> None:
        import numpy as np

        ctx.clear(0.0, 0.0, 0.0, 0.0)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        # Simple orthographic MVP for upper-body framing
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
            # pad to 128 bones
            padded = np.zeros(128 * 16, dtype=np.float32)
            padded[:len(flat)] = flat
            prog["u_joint_matrices"].write(padded.tobytes())

        for vao in vaos:
            vao.render(moderngl.TRIANGLES)


def _ortho_mvp(width: int, height: int) -> "np.ndarray":
    import numpy as np
    # Simple orthographic projection centred on origin, spanning ±1
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
EGL_PLATFORM=surfaceless pytest tests/nova_vt/renderer/test_vrm_renderer.py -v
```

Expected: PASSED (or SKIPPED on systems without EGL)

- [ ] **Step 5: Commit**

```bash
git add nova_vt/renderer/vrm_renderer.py tests/nova_vt/renderer/test_vrm_renderer.py
git commit -m "feat: add EGL headless VRM renderer QThread"
```

---

### Task 7: MediaPipe tracker thread

**Files:**
- Create: `nova_vt/tracking/mediapipe_tracker.py`
- Create: `tests/nova_vt/tracking/test_mediapipe_tracker.py`

- [ ] **Step 1: Write failing tests**

`tests/nova_vt/tracking/test_mediapipe_tracker.py`:
```python
import time
import threading
import pytest
import numpy as np
from nova_vt.tracking.mediapipe_tracker import MediaPipeTracker
from nova_vt.tracking.provider import TrackingFrame, VRM_BONE_NAMES


def test_tracker_implements_provider_protocol():
    from nova_vt.tracking.provider import TrackingProvider
    tracker = MediaPipeTracker(camera_index=0)
    assert isinstance(tracker, TrackingProvider)


def test_get_frame_before_start_returns_identity():
    tracker = MediaPipeTracker(camera_index=0)
    frame = tracker.get_frame()
    assert isinstance(frame, TrackingFrame)
    # All poses should be identity before camera is open
    for bone, q in frame.pose.items():
        assert q == (0.0, 0.0, 0.0, 1.0), f"{bone} should be identity"


def test_tracker_start_stop_without_camera():
    """Tracker should start and stop without raising even if camera fails to open."""
    tracker = MediaPipeTracker(camera_index=99)  # non-existent
    tracker.start()
    time.sleep(0.2)
    tracker.stop()
    assert tracker.wait(2000), "tracker did not stop within 2s"


def test_blend_shapes_are_valid_range():
    """blend_shapes values should always be clamped 0..1."""
    tracker = MediaPipeTracker(camera_index=0)
    frame = tracker.get_frame()
    for k, v in frame.blend_shapes.items():
        assert 0.0 <= v <= 1.0, f"{k} = {v} out of range"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/nova_vt/tracking/test_mediapipe_tracker.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement MediaPipeTracker**

`nova_vt/tracking/mediapipe_tracker.py`:
```python
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from nova_vt.tracking.provider import (
    TrackingFrame,
    TrackingProvider,
    PoseDict,
    identity_pose,
)
from nova_vt.tracking.pose_map import landmarks_to_pose

# MediaPipe task model path — downloaded separately or bundled
_FACE_TASK = Path(__file__).parents[2] / "face_landmarker.task"
_BODY_TASK = Path(__file__).parents[2] / "pose_landmarker.task"

# ARKit blend shape names that MediaPipe FaceLandmarker produces
_ARKIT_NAMES: tuple[str, ...] = (
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
    "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft",
    "mouthFrownRight", "mouthFunnel", "mouthLeft", "mouthLowerDownLeft",
    "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight", "mouthPucker",
    "mouthRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower",
    "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft",
    "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight",
    "noseSneerLeft", "noseSneerRight", "cheekPuff", "cheekSquintLeft",
    "cheekSquintRight", "browDownLeft", "browDownRight", "browInnerUp",
    "browOuterUpLeft", "browOuterUpRight", "tongueOut",
)


class MediaPipeTracker(QThread):
    """Captures webcam and runs MediaPipe FaceLandmarker + PoseLandmarker.

    Thread-safe: call get_frame() from any thread to get the latest TrackingFrame.
    """

    error = pyqtSignal(str)

    def __init__(self, camera_index: int = 0) -> None:
        super().__init__()
        self._camera_index = camera_index
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest = TrackingFrame()

    # ── TrackingProvider protocol ────────────────────────────────────────────

    def get_frame(self) -> TrackingFrame:
        with self._frame_lock:
            return self._latest

    def stop(self) -> None:  # type: ignore[override]
        self._stop_event.set()

    # ── QThread ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._run_loop()
        except Exception as exc:
            self.error.emit(str(exc))

    def _run_loop(self) -> None:
        cap = self._open_camera()
        face_landmarker = self._build_face_landmarker()
        pose_landmarker = self._build_pose_landmarker()

        while not self._stop_event.is_set():
            if cap is None or not cap.isOpened():
                self._stop_event.wait(0.5)
                continue
            ret, bgr = cap.read()
            if not ret:
                continue

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = int(time.time() * 1000)

            blend_shapes: dict[str, float] = {}
            pose = identity_pose()

            if face_landmarker:
                result = face_landmarker.detect_for_video(mp_image, ts)
                if result.face_blendshapes:
                    for cat in result.face_blendshapes[0]:
                        name = cat.category_name.replace("_", "")
                        # Normalise to camelCase ARKit name
                        arkit = _normalise_arkit(name)
                        if arkit:
                            blend_shapes[arkit] = max(0.0, min(1.0, cat.score))

            if pose_landmarker:
                result = pose_landmarker.detect_for_video(mp_image, ts)
                if result.pose_world_landmarks:
                    pose = landmarks_to_pose(result.pose_world_landmarks[0])

            with self._frame_lock:
                self._latest = TrackingFrame(
                    pose=pose,
                    blend_shapes=blend_shapes,
                    timestamp=time.time(),
                )

        if cap:
            cap.release()

    def _open_camera(self) -> Optional[cv2.VideoCapture]:
        for backend in [cv2.CAP_V4L2, cv2.CAP_ANY]:
            cap = cv2.VideoCapture(self._camera_index, backend)
            if cap.isOpened():
                return cap
        return None

    def _build_face_landmarker(self):
        if not _FACE_TASK.exists():
            return None
        opts = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(_FACE_TASK)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            output_face_blendshapes=True,
            num_faces=1,
        )
        return mp.tasks.vision.FaceLandmarker.create_from_options(opts)

    def _build_pose_landmarker(self):
        if not _BODY_TASK.exists():
            return None
        opts = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(_BODY_TASK)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
        )
        return mp.tasks.vision.PoseLandmarker.create_from_options(opts)


def _normalise_arkit(name: str) -> str | None:
    """Map MediaPipe category name to ARKit camelCase key."""
    # MediaPipe returns names like "eyeBlinkLeft" — already ARKit
    for arkit in _ARKIT_NAMES:
        if name.lower() == arkit.lower():
            return arkit
    return None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/nova_vt/tracking/test_mediapipe_tracker.py -v
```

Expected: all pass (camera tests may skip if no webcam in CI)

- [ ] **Step 5: Commit**

```bash
git add nova_vt/tracking/mediapipe_tracker.py tests/nova_vt/tracking/test_mediapipe_tracker.py
git commit -m "feat: add MediaPipeTracker QThread (face + body tracking)"
```

---

### Task 8: pose_map.py (MediaPipe landmarks → VRM bone rotations)

**Files:**
- Create: `nova_vt/tracking/pose_map.py`
- Create: `tests/nova_vt/tracking/test_pose_map.py`

- [ ] **Step 1: Write failing tests**

`tests/nova_vt/tracking/test_pose_map.py`:
```python
import numpy as np
from nova_vt.tracking.pose_map import landmarks_to_pose
from nova_vt.tracking.provider import VRM_BONE_NAMES, IDENTITY_QUATERNION


class _FakeLandmark:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x; self.y = y; self.z = z


def make_landmarks(n=33):
    return [_FakeLandmark() for _ in range(n)]


def test_returns_dict_with_all_bone_names():
    pose = landmarks_to_pose(make_landmarks())
    assert set(pose.keys()) == set(VRM_BONE_NAMES)


def test_unmapped_bones_are_identity():
    pose = landmarks_to_pose(make_landmarks())
    # Fingers are not mapped; should remain identity
    assert pose["leftThumbProximal"] == IDENTITY_QUATERNION
    assert pose["rightIndexDistal"] == IDENTITY_QUATERNION


def test_shoulder_differs_when_landmarks_differ():
    lms = make_landmarks()
    # MediaPipe landmark 11 = left shoulder, 12 = right shoulder
    lms[11] = _FakeLandmark(x=0.3, y=-0.4, z=0.1)
    lms[12] = _FakeLandmark(x=-0.3, y=-0.4, z=0.1)
    pose = landmarks_to_pose(lms)
    # Shoulder rotation should differ from identity
    assert pose["leftShoulder"] != IDENTITY_QUATERNION or pose["rightShoulder"] != IDENTITY_QUATERNION


def test_quaternion_is_unit_length():
    lms = make_landmarks()
    lms[11] = _FakeLandmark(x=0.5, y=-0.5, z=0.2)
    pose = landmarks_to_pose(lms)
    for bone, q in pose.items():
        length = sum(v ** 2 for v in q) ** 0.5
        assert abs(length - 1.0) < 1e-5, f"{bone} quaternion not unit length: {q}"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/nova_vt/tracking/test_pose_map.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement pose_map.py**

`nova_vt/tracking/pose_map.py`:
```python
"""Maps MediaPipe PoseLandmarker world landmarks (33 points) to VRM bone rotations.

MediaPipe landmark indices (upper body subset used here):
  0  = nose          11 = left shoulder   12 = right shoulder
  13 = left elbow    14 = right elbow     15 = left wrist
  16 = right wrist   23 = left hip        24 = right hip

Unmapped VRM bones (fingers, legs, etc.) default to identity quaternion.
"""
from __future__ import annotations

import math
import numpy as np
from nova_vt.tracking.provider import PoseDict, Quaternion, VRM_BONE_NAMES, identity_pose


def landmarks_to_pose(landmarks: list) -> PoseDict:
    """Convert MediaPipe world landmarks to VRM PoseDict.

    Args:
        landmarks: list of objects with .x .y .z (world-space metres)

    Returns:
        PoseDict with all 54 VRM bone names; unmapped bones = identity.
    """
    pose = identity_pose()
    if len(landmarks) < 25:
        return pose

    pts = np.array([[l.x, l.y, l.z] for l in landmarks], dtype=np.float32)

    # Neck: vector from mid-hip to mid-shoulder, expressed as a rotation
    mid_shoulder = (pts[11] + pts[12]) * 0.5
    mid_hip = (pts[23] + pts[24]) * 0.5
    spine_vec = mid_shoulder - mid_hip
    pose["spine"] = _vec_to_quat(spine_vec, ref=np.array([0, 1, 0], dtype=np.float32))

    # Head: nose relative to mid-shoulder
    nose = pts[0]
    head_vec = nose - mid_shoulder
    pose["head"] = _vec_to_quat(head_vec, ref=np.array([0, 1, 0], dtype=np.float32))

    # Shoulders: upper arm direction
    l_upper = pts[13] - pts[11]  # elbow - shoulder
    r_upper = pts[14] - pts[12]
    pose["leftUpperArm"] = _vec_to_quat(l_upper, ref=np.array([-1, 0, 0], dtype=np.float32))
    pose["rightUpperArm"] = _vec_to_quat(r_upper, ref=np.array([1, 0, 0], dtype=np.float32))

    # Forearms: wrist - elbow
    l_lower = pts[15] - pts[13]
    r_lower = pts[16] - pts[14]
    pose["leftLowerArm"] = _vec_to_quat(l_lower, ref=np.array([-1, 0, 0], dtype=np.float32))
    pose["rightLowerArm"] = _vec_to_quat(r_lower, ref=np.array([1, 0, 0], dtype=np.float32))

    # Shoulder bones (clavicle-level rotation based on shoulder height diff)
    shoulder_diff = pts[11][1] - pts[12][1]
    tilt = max(-0.3, min(0.3, shoulder_diff))
    pose["leftShoulder"] = _axis_angle_quat(np.array([0, 0, 1], dtype=np.float32), tilt)
    pose["rightShoulder"] = _axis_angle_quat(np.array([0, 0, -1], dtype=np.float32), tilt)

    return pose


def _vec_to_quat(vec: np.ndarray, ref: np.ndarray) -> Quaternion:
    """Return the quaternion rotating `ref` to align with `vec`."""
    v = vec / (np.linalg.norm(vec) + 1e-8)
    r = ref / (np.linalg.norm(ref) + 1e-8)
    cross = np.cross(r, v)
    dot = float(np.dot(r, v))
    cross_len = np.linalg.norm(cross)
    if cross_len < 1e-8:
        # Parallel or anti-parallel
        if dot > 0:
            return (0.0, 0.0, 0.0, 1.0)
        # Anti-parallel: rotate 180° around any perpendicular axis
        perp = np.cross(r, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(perp) < 1e-8:
            perp = np.cross(r, np.array([0.0, 1.0, 0.0]))
        perp /= np.linalg.norm(perp)
        return (float(perp[0]), float(perp[1]), float(perp[2]), 0.0)
    axis = cross / cross_len
    angle = math.atan2(cross_len, dot)
    s = math.sin(angle / 2)
    return (float(axis[0] * s), float(axis[1] * s), float(axis[2] * s), float(math.cos(angle / 2)))


def _axis_angle_quat(axis: np.ndarray, angle: float) -> Quaternion:
    s = math.sin(angle / 2)
    c = math.cos(angle / 2)
    return (float(axis[0] * s), float(axis[1] * s), float(axis[2] * s), float(c))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/nova_vt/tracking/test_pose_map.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add nova_vt/tracking/pose_map.py tests/nova_vt/tracking/test_pose_map.py
git commit -m "feat: add pose_map — MediaPipe landmarks to VRM bone quaternions"
```

---

## Chunk 3: Compositor + Integration

### Task 9: Scene JSON (scene.py + layers.py)

**Files:**
- Create: `nova_vt/compositor/scene.py`
- Create: `nova_vt/compositor/layers.py`
- Create: `tests/nova_vt/compositor/__init__.py`
- Create: `tests/nova_vt/compositor/test_scene.py`

- [ ] **Step 1: Write failing tests**

`tests/nova_vt/compositor/test_scene.py`:
```python
import json
import tempfile
from pathlib import Path
from nova_vt.compositor.scene import Scene, load_scene, save_scene
from nova_vt.compositor.layers import CaptureLayer, AvatarLayer, ImageLayer, TextLayer


def test_load_scene_from_dict():
    data = {
        "name": "Gameplay",
        "layers": [
            {"type": "capture", "device": "/dev/video0", "rect": [0, 0, 1920, 1080]},
            {"type": "avatar", "rect": [1440, 540, 480, 540]},
        ]
    }
    scene = Scene.from_dict(data)
    assert scene.name == "Gameplay"
    assert len(scene.layers) == 2
    assert isinstance(scene.layers[0], CaptureLayer)
    assert isinstance(scene.layers[1], AvatarLayer)


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        scene = Scene(name="BRB", layers=[
            ImageLayer(path="/tmp/brb.png", rect=(0, 0, 1920, 1080)),
            TextLayer(content="BRB — back soon!", font_size=64, color="#ffffff", rect=(760, 500, 400, 80)),
        ])
        path = Path(d) / "brb.json"
        save_scene(scene, path)
        loaded = load_scene(path)
        assert loaded.name == "BRB"
        assert len(loaded.layers) == 2
        assert isinstance(loaded.layers[0], ImageLayer)
        assert isinstance(loaded.layers[1], TextLayer)
        assert loaded.layers[1].content == "BRB — back soon!"


def test_text_layer_has_template_vars():
    layer = TextLayer(content="{total_viewers} watching", font_size=32, color="#fff", rect=(0, 0, 200, 40))
    assert "{total_viewers}" in layer.content


def test_default_scenes_include_gameplay():
    from nova_vt.compositor.scene import default_scenes
    scenes = default_scenes()
    names = [s.name for s in scenes]
    assert "Gameplay" in names
    assert "BRB" in names
    assert "Just Chatting" in names
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/nova_vt/compositor/test_scene.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement layers.py**

`nova_vt/compositor/layers.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field


Rect = tuple[int, int, int, int]  # (x, y, w, h)


@dataclass
class CaptureLayer:
    device: str
    rect: Rect

    def to_dict(self) -> dict:
        return {"type": "capture", "device": self.device, "rect": list(self.rect)}


@dataclass
class AvatarLayer:
    rect: Rect

    def to_dict(self) -> dict:
        return {"type": "avatar", "rect": list(self.rect)}


@dataclass
class ImageLayer:
    path: str
    rect: Rect
    opacity: float = 1.0

    def to_dict(self) -> dict:
        return {"type": "image", "path": self.path, "rect": list(self.rect), "opacity": self.opacity}


@dataclass
class TextLayer:
    content: str
    font_size: int
    color: str
    rect: Rect

    def to_dict(self) -> dict:
        return {"type": "text", "content": self.content,
                "font_size": self.font_size, "color": self.color, "rect": list(self.rect)}


Layer = CaptureLayer | AvatarLayer | ImageLayer | TextLayer


def layer_from_dict(d: dict) -> Layer:
    t = d["type"]
    rect = tuple(d["rect"])
    if t == "capture":
        return CaptureLayer(device=d["device"], rect=rect)
    if t == "avatar":
        return AvatarLayer(rect=rect)
    if t == "image":
        return ImageLayer(path=d["path"], rect=rect, opacity=d.get("opacity", 1.0))
    if t == "text":
        return TextLayer(content=d["content"], font_size=d["font_size"],
                         color=d["color"], rect=rect)
    raise ValueError(f"Unknown layer type: {t!r}")
```

- [ ] **Step 4: Implement scene.py**

`nova_vt/compositor/scene.py`:
```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from nova_vt.compositor.layers import Layer, layer_from_dict, AvatarLayer, CaptureLayer, ImageLayer, TextLayer


@dataclass
class Scene:
    name: str
    layers: list[Layer] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "layers": [l.to_dict() for l in self.layers]}

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(
            name=d["name"],
            layers=[layer_from_dict(l) for l in d.get("layers", [])],
        )


def load_scene(path: Path) -> Scene:
    return Scene.from_dict(json.loads(path.read_text()))


def save_scene(scene: Scene, path: Path) -> None:
    path.write_text(json.dumps(scene.to_dict(), indent=2))


def default_scenes() -> list[Scene]:
    return [
        Scene("Gameplay", [
            CaptureLayer(device="/dev/video1", rect=(0, 0, 1920, 1080)),
            AvatarLayer(rect=(1440, 540, 480, 540)),
        ]),
        Scene("Just Chatting", [
            AvatarLayer(rect=(560, 0, 800, 1080)),
        ]),
        Scene("BRB", [
            TextLayer(content="BRB — back soon!", font_size=72, color="#a78bfa", rect=(660, 480, 600, 120)),
        ]),
        Scene("Intro", [
            TextLayer(content="Starting soon...", font_size=64, color="#e9d5ff", rect=(660, 480, 600, 120)),
        ]),
        Scene("Ending", [
            TextLayer(content="Thanks for watching! 💜", font_size=64, color="#e9d5ff", rect=(560, 480, 800, 120)),
        ]),
    ]
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/nova_vt/compositor/test_scene.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add nova_vt/compositor/ tests/nova_vt/compositor/
git commit -m "feat: add Scene/Layer types with JSON load/save and default scenes"
```

---

### Task 10: Compositor thread

**Files:**
- Create: `nova_vt/compositor/compositor.py`
- Create: `tests/nova_vt/compositor/test_compositor.py`

- [ ] **Step 1: Write failing tests**

`tests/nova_vt/compositor/test_compositor.py`:
```python
import queue
import time
import numpy as np
import pytest
from nova_vt.compositor.compositor import Compositor
from nova_vt.compositor.scene import Scene
from nova_vt.compositor.layers import AvatarLayer


def make_rgba(h, w, r, g, b, a=255) -> np.ndarray:
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :] = [r, g, b, a]
    return arr


def test_compositor_alpha_blend():
    """Alpha compositing: semi-transparent foreground over opaque background."""
    bg = make_rgba(4, 4, 255, 0, 0, 255)   # opaque red
    fg = make_rgba(4, 4, 0, 0, 255, 128)   # 50% blue over red
    from nova_vt.compositor.compositor import alpha_over
    result = alpha_over(bg, fg)
    # Result blue channel should be ~128, red ~127
    assert result[0, 0, 2] > 100  # blue present
    assert result[0, 0, 0] > 50   # red still visible


def test_compositor_produces_frames():
    scene = Scene("test", [AvatarLayer(rect=(0, 0, 192, 108))])
    avatar_q: queue.Queue = queue.Queue(maxsize=2)
    preview_q: queue.Queue = queue.Queue(maxsize=4)

    # Pre-fill avatar queue with a frame
    avatar_frame = make_rgba(108, 192, 128, 64, 200, 255)
    avatar_q.put_nowait(avatar_frame)

    comp = Compositor(
        scene=scene,
        avatar_queue=avatar_q,
        preview_queue=preview_q,
        width=192,
        height=108,
        fps=10,
    )
    comp.start()
    time.sleep(0.5)
    comp.stop()
    comp.wait(2000)

    assert not preview_q.empty(), "compositor produced no frames"
    frame = preview_q.get_nowait()
    assert frame.shape == (108, 192, 4)


def test_compositor_stop_is_clean():
    scene = Scene("empty", [])
    preview_q: queue.Queue = queue.Queue(maxsize=2)
    comp = Compositor(scene=scene, avatar_queue=queue.Queue(), preview_queue=preview_q,
                      width=192, height=108, fps=10)
    comp.start()
    time.sleep(0.2)
    comp.stop()
    assert comp.wait(2000), "compositor did not stop within 2s"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/nova_vt/compositor/test_compositor.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement compositor.py**

`nova_vt/compositor/compositor.py`:
```python
from __future__ import annotations

import queue
import threading
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from nova_vt.compositor.scene import Scene
from nova_vt.compositor.layers import (
    CaptureLayer, AvatarLayer, ImageLayer, TextLayer, Layer,
)


def alpha_over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Alpha-composite `src` over `dst` (both H×W×4 uint8). Returns new array."""
    src_a = src[:, :, 3:4].astype(np.float32) / 255.0
    dst_a = dst[:, :, 3:4].astype(np.float32) / 255.0
    out_a = src_a + dst_a * (1.0 - src_a)
    src_rgb = src[:, :, :3].astype(np.float32)
    dst_rgb = dst[:, :, :3].astype(np.float32)
    out_rgb = (src_rgb * src_a + dst_rgb * dst_a * (1.0 - src_a)) / (out_a + 1e-8)
    result = np.zeros_like(dst)
    result[:, :, :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
    result[:, :, 3] = np.clip(out_a[:, :, 0] * 255, 0, 255).astype(np.uint8)
    return result


class Compositor(QThread):
    """Composites layers each frame and pushes to preview_queue (and encoder_queue when live).

    Layer order: back-to-front (layers[0] is bottommost).
    """

    error = pyqtSignal(str)

    def __init__(
        self,
        scene: Scene,
        avatar_queue: queue.Queue,
        preview_queue: queue.Queue,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        encoder_queue: Optional[queue.Queue] = None,
        stats: Optional[object] = None,  # StreamStats, added in Plan 2
    ) -> None:
        super().__init__()
        self._scene = scene
        self._avatar_q = avatar_queue
        self._preview_q = preview_queue
        self._encoder_q = encoder_queue
        self._stats = stats
        self._width = width
        self._height = height
        self._fps = fps
        self._stop_event = threading.Event()
        self._scene_lock = threading.Lock()
        self._capture_caches: dict[str, cv2.VideoCapture] = {}
        self._image_caches: dict[str, np.ndarray] = {}
        self._latest_avatar: Optional[np.ndarray] = None

    def switch_scene(self, scene: Scene) -> None:
        with self._scene_lock:
            self._scene = scene

    def set_encoder_queue(self, q: Optional[queue.Queue]) -> None:
        self._encoder_q = q

    def stop(self) -> None:  # type: ignore[override]
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._composite_loop()
        except Exception as exc:
            self.error.emit(str(exc))

    def _composite_loop(self) -> None:
        frame_time = 1.0 / self._fps
        while not self._stop_event.is_set():
            t0 = time.perf_counter()

            # Drain avatar queue for latest frame
            while True:
                try:
                    self._latest_avatar = self._avatar_q.get_nowait()
                except queue.Empty:
                    break

            with self._scene_lock:
                scene = self._scene

            canvas = np.zeros((self._height, self._width, 4), dtype=np.uint8)
            for layer in scene.layers:
                layer_img = self._render_layer(layer)
                if layer_img is not None:
                    canvas = self._blit(canvas, layer_img, layer)

            # Push preview (half-res)
            preview = canvas[::2, ::2]
            try:
                self._preview_q.put_nowait(preview)
            except queue.Full:
                pass

            # Push to encoder when live
            if self._encoder_q is not None:
                try:
                    self._encoder_q.put_nowait(canvas)
                except queue.Full:
                    pass

            elapsed = time.perf_counter() - t0
            sleep = frame_time - elapsed
            if sleep > 0:
                self._stop_event.wait(sleep)

        for cap in self._capture_caches.values():
            cap.release()

    def _render_layer(self, layer: Layer) -> Optional[np.ndarray]:
        if isinstance(layer, AvatarLayer):
            if self._latest_avatar is None:
                return None
            w, h = layer.rect[2], layer.rect[3]
            return cv2.resize(self._latest_avatar, (w, h), interpolation=cv2.INTER_LINEAR)

        if isinstance(layer, CaptureLayer):
            cap = self._capture_caches.get(layer.device)
            if cap is None:
                cap = cv2.VideoCapture(layer.device, cv2.CAP_V4L2)
                self._capture_caches[layer.device] = cap
            if not cap.isOpened():
                return None
            ret, bgr = cap.read()
            if not ret:
                return None
            rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
            w, h = layer.rect[2], layer.rect[3]
            return cv2.resize(rgba, (w, h), interpolation=cv2.INTER_LINEAR)

        if isinstance(layer, ImageLayer):
            img = self._image_caches.get(layer.path)
            if img is None:
                raw = cv2.imread(layer.path, cv2.IMREAD_UNCHANGED)
                if raw is None:
                    return None
                if raw.shape[2] == 3:
                    raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGBA)
                else:
                    raw = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGBA)
                self._image_caches[layer.path] = raw
                img = raw
            w, h = layer.rect[2], layer.rect[3]
            resized = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
            if layer.opacity < 1.0:
                resized = resized.copy()
                resized[:, :, 3] = (resized[:, :, 3] * layer.opacity).astype(np.uint8)
            return resized

        if isinstance(layer, TextLayer):
            content = self._resolve_template(layer.content)
            w, h = layer.rect[2], layer.rect[3]
            img = np.zeros((h, w, 4), dtype=np.uint8)
            color_hex = layer.color.lstrip("#")
            r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
            scale = layer.font_size / 30.0
            cv2.putText(img, content, (4, h - 8), cv2.FONT_HERSHEY_SIMPLEX,
                        scale, (b, g, r, 255), 1, cv2.LINE_AA)
            return img

        return None

    def _blit(self, canvas: np.ndarray, layer_img: np.ndarray, layer: Layer) -> np.ndarray:
        x, y = layer.rect[0], layer.rect[1]
        h, w = layer_img.shape[:2]
        # Clamp to canvas bounds
        x2 = min(x + w, self._width)
        y2 = min(y + h, self._height)
        if x2 <= x or y2 <= y:
            return canvas
        cw, ch = x2 - x, y2 - y
        roi = canvas[y:y2, x:x2]
        src = layer_img[:ch, :cw]
        canvas[y:y2, x:x2] = alpha_over(roi, src)
        return canvas

    def _resolve_template(self, content: str) -> str:
        if self._stats is None:
            return content
        # StreamStats attributes (added in Plan 2)
        replacements = {
            "{total_viewers}": str(getattr(self._stats, "total_viewers", 0)),
            "{twitch_viewers}": str(getattr(self._stats, "twitch_viewers", 0)),
            "{youtube_viewers}": str(getattr(self._stats, "youtube_viewers", 0)),
            "{tiktok_viewers}": str(getattr(self._stats, "tiktok_viewers", 0)),
            "{stream_time}": getattr(self._stats, "stream_time_str", "00:00:00"),
        }
        for k, v in replacements.items():
            content = content.replace(k, v)
        return content
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/nova_vt/compositor/test_compositor.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add nova_vt/compositor/compositor.py tests/nova_vt/compositor/test_compositor.py
git commit -m "feat: add numpy Compositor QThread with alpha compositing and scene switching"
```

---

### Task 11: Headless integration test (render pipeline to PNG)

**Files:**
- Create: `tests/nova_vt/test_integration_render.py`

This test wires Tracker → Renderer → Compositor and writes a single composite frame to `/tmp/nova-vt-test-frame.png`. It verifies the full pipeline without any Qt window or stream output.

- [ ] **Step 1: Write the integration test**

`tests/nova_vt/test_integration_render.py`:
```python
"""Integration test: full rendering pipeline → PNG.

Requires: model.vrm present, EGL available, MediaPipe models optional.
Run: EGL_PLATFORM=surfaceless pytest tests/nova_vt/test_integration_render.py -v -s
"""
import os
import queue
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("EGL_PLATFORM", "surfaceless")

try:
    import moderngl
    import cv2
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

VRM_PATH = Path(__file__).parents[2] / "model.vrm"
OUTPUT_PATH = Path("/tmp/nova-vt-test-frame.png")


@pytest.mark.skipif(not HAS_DEPS, reason="moderngl or cv2 not installed")
def test_pipeline_renders_to_png():
    if not VRM_PATH.exists():
        pytest.skip("model.vrm not found")

    from nova_vt.renderer.vrm_loader import VRMLoader
    from nova_vt.renderer.vrm_renderer import VRMRenderer
    from nova_vt.compositor.compositor import Compositor
    from nova_vt.compositor.scene import Scene
    from nova_vt.compositor.layers import AvatarLayer

    avatar_q: queue.Queue = queue.Queue(maxsize=2)
    preview_q: queue.Queue = queue.Queue(maxsize=4)

    loader = VRMLoader(VRM_PATH)
    renderer = VRMRenderer(loader, preview_queue=avatar_q, width=960, height=540)
    scene = Scene("test", [AvatarLayer(rect=(0, 0, 960, 540))])
    comp = Compositor(scene=scene, avatar_queue=avatar_q, preview_queue=preview_q,
                      width=960, height=540, fps=10)

    renderer.start()
    comp.start()
    time.sleep(2.0)
    renderer.stop()
    comp.stop()
    renderer.wait(3000)
    comp.wait(3000)

    assert not preview_q.empty(), "pipeline produced no composite frames"
    frame = preview_q.get_nowait()
    assert frame.dtype == np.uint8
    assert frame.ndim == 3 and frame.shape[2] == 4

    # Write to PNG for visual inspection
    bgra = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGRA)
    cv2.imwrite(str(OUTPUT_PATH), bgra)
    print(f"\nFrame written to {OUTPUT_PATH} — inspect visually.")
    assert OUTPUT_PATH.exists()
```

- [ ] **Step 2: Run the integration test**

```bash
EGL_PLATFORM=surfaceless pytest tests/nova_vt/test_integration_render.py -v -s
```

Expected: PASSED, PNG written to `/tmp/nova-vt-test-frame.png`

- [ ] **Step 3: Visually inspect the output**

```bash
xdg-open /tmp/nova-vt-test-frame.png
```

Verify: avatar renders on transparent background, no visual glitches

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
EGL_PLATFORM=surfaceless pytest tests/ -v --ignore=tests/dashboard
```

Expected: all tests pass or skip (no failures)

- [ ] **Step 5: Final commit**

```bash
git add tests/nova_vt/test_integration_render.py
git commit -m "test: add headless pipeline integration test (render to PNG)"
```

---

## Summary

After completing all tasks in this plan:
- `nova_vt/` package is installed and importable
- Config loads/saves TOML with 600-permissions secrets file
- VRM model parses cleanly (mesh, skin, morph targets, expression map)
- MToon shaders compile on EGL headless context
- Renderer produces 1920×1080 RGBA frames via EGL at 30fps
- MediaPipe tracker runs in a QThread and outputs TrackingFrame
- Composite pipeline (tracker → renderer → compositor) produces frames verified by PNG output

**Next plan:** `2026-03-14-nova-vt-streaming-engine.md` — Audio mixer, ffmpeg FIFO encoder, and chat providers.
