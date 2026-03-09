from unittest.mock import patch, MagicMock
from tracker.osc_sender import OscSender
from tracker.face_tracker import FaceData


def test_osc_sender_sends_face_data():
    with patch('tracker.osc_sender.SimpleUDPClient') as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        sender = OscSender(host="127.0.0.1", port=9000)
        data = FaceData(head_yaw=10.0, head_pitch=-5.0, mouth_open=0.5)
        sender.send(data)

        calls = [call[0][0] for call in mock_client.send_message.call_args_list]
        assert "/avatar/parameters/HeadYaw" in calls
        assert "/avatar/parameters/HeadPitch" in calls
        assert "/avatar/parameters/MouthOpen" in calls


def test_osc_sender_sends_correct_values():
    with patch('tracker.osc_sender.SimpleUDPClient') as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        sender = OscSender(host="127.0.0.1", port=9000)
        data = FaceData(head_yaw=10.0)
        sender.send(data)

        call_map = {
            call[0][0]: call[0][1]
            for call in mock_client.send_message.call_args_list
        }
        assert call_map["/avatar/parameters/HeadYaw"] == 10.0
