from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

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
    morph_targets: list[np.ndarray] = field(default_factory=list)
    morph_names: list[str] = field(default_factory=list)
    texture_rgba: np.ndarray | None = None  # (H, W, 4) uint8 or None


@dataclass
class SkinData:
    bone_names: list[str]
    inverse_bind_matrices: np.ndarray  # (B, 4, 4) float32
    joints: np.ndarray                 # (N, 4) uint16
    weights: np.ndarray                # (N, 4) float32


class VRMLoader:
    """Loads a VRM 0.x or 1.0 file and exposes mesh, skin, and expression data."""

    def __init__(self, path: Path) -> None:
        import pygltflib  # lazy — only needed when a VRM file is actually loaded
        self._path = path
        # pygltflib.load() dispatches by extension — .vrm isn't .glb so it tries
        # load_json() and crashes on binary data.  Force load_binary() instead.
        self._gltf = pygltflib.GLTF2.load_binary(str(path))
        self.meshes: list[MeshData] = []
        self.skin: SkinData | None = None
        self.expression_map: dict[str, int] = {}  # ARKit name → morph target index
        self._load()

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (min_xyz, max_xyz) over all mesh positions."""
        all_pos = np.concatenate([m.positions for m in self.meshes], axis=0)
        return all_pos.min(axis=0), all_pos.max(axis=0)

    def apply_pose(self, pose_dict: dict[str, tuple]) -> np.ndarray:
        """Return (B, 4, 4) float32 joint matrices for GPU upload."""
        if self.skin is None:
            return np.eye(4, dtype=np.float32)[np.newaxis].repeat(1, 0)
        B = len(self.skin.bone_names)
        mats = np.tile(np.eye(4, dtype=np.float32), (B, 1, 1))
        return mats

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

    def _load_primitive(self, prim) -> MeshData:
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
        texture_rgba = self._load_material_texture(prim)
        return MeshData(
            positions=positions.astype(np.float32),
            normals=normals.astype(np.float32),
            uvs=uvs.astype(np.float32),
            indices=indices,
            morph_targets=morph_targets,
            morph_names=morph_names,
            texture_rgba=texture_rgba,
        )

    def _load_material_texture(self, prim) -> "np.ndarray | None":
        """Return RGBA uint8 texture for the primitive's material, or None."""
        import io
        gltf = self._gltf
        mat_idx = getattr(prim, "material", None)
        if mat_idx is None or not gltf.materials:
            return None
        mat = gltf.materials[mat_idx]

        # Try standard PBR base colour texture first
        tex_idx: int | None = None
        pbr = getattr(mat, "pbrMetallicRoughness", None)
        if pbr is not None:
            bct = getattr(pbr, "baseColorTexture", None)
            if bct is not None:
                tex_idx = getattr(bct, "index", None)

        # Fall back to MToon / VRM extension mainTexture
        if tex_idx is None:
            exts = (mat.extensions or {}) if hasattr(mat, "extensions") else {}
            for ext_name in ("VRMC_materials_mtoon", "KHR_materials_unlit", "VRM"):
                ext = exts.get(ext_name, {})
                if isinstance(ext, dict):
                    mt = ext.get("shadeMultiplyTexture") or ext.get("mainTexture")
                    if isinstance(mt, dict) and "index" in mt:
                        tex_idx = mt["index"]
                        break

        if tex_idx is None or not gltf.textures:
            return None
        tex = gltf.textures[tex_idx]
        img_idx = getattr(tex, "source", None)
        if img_idx is None or not gltf.images:
            return None
        img = gltf.images[img_idx]

        # Load raw bytes from bufferView or URI
        try:
            bv_idx = getattr(img, "bufferView", None)
            if bv_idx is not None:
                bv = gltf.bufferViews[bv_idx]
                buf = gltf.buffers[bv.buffer]
                raw_blob: bytes = bytes(gltf.binary_blob())
                start = bv.byteOffset or 0
                img_bytes = raw_blob[start: start + bv.byteLength]
            else:
                uri = getattr(img, "uri", None)
                if not uri:
                    return None
                import base64, urllib.parse
                if uri.startswith("data:"):
                    img_bytes = base64.b64decode(uri.split(",", 1)[1])
                else:
                    img_bytes = (self._path.parent / urllib.parse.unquote(uri)).read_bytes()

            import cv2
            arr = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if arr is None:
                return None
            if arr.ndim == 2:
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGBA)
            elif arr.shape[2] == 3:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGBA)
            elif arr.shape[2] == 4:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGBA)
            return arr.astype(np.uint8)
        except Exception:
            return None

    def _load_skin(self, skin) -> SkinData:
        gltf = self._gltf
        bone_names = []
        for j in skin.joints or []:
            node = gltf.nodes[j]
            bone_names.append(node.name or f"bone_{j}")
        ibm = self._accessor_to_numpy(skin.inverseBindMatrices)
        ibm = ibm.reshape(-1, 4, 4).astype(np.float32)
        mesh = self.meshes[0] if self.meshes else None
        n = mesh.positions.shape[0] if mesh else 0
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
        if buf.uri is None:
            raw: bytes = bytes(gltf.binary_blob())
        else:
            import base64, urllib.parse
            if buf.uri.startswith("data:"):
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
                f"Interleaved buffer views (byteStride={stride}) are not yet supported."
            )
        start = (bv.byteOffset or 0) + (acc.byteOffset or 0)
        total = acc.count * type_count
        arr = np.frombuffer(raw, dtype=comp_dtype, count=total, offset=start)
        if type_count > 1:
            arr = arr.reshape(acc.count, type_count)
        return arr.copy()
