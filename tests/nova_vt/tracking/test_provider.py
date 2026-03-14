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
