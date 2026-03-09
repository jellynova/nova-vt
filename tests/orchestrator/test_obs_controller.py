from unittest.mock import patch, MagicMock
import pytest
from orchestrator.obs_controller import OBSController


def test_obs_controller_switch_scene():
    with patch('orchestrator.obs_controller.obs.ReqClient') as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        controller = OBSController(host="localhost", port=4455, password="test")
        controller.switch_scene("Gameplay")

        mock_client.set_current_program_scene.assert_called_once_with("Gameplay")


def test_obs_controller_get_current_scene():
    with patch('orchestrator.obs_controller.obs.ReqClient') as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get_current_program_scene.return_value.current_program_scene_name = "BRB"
        mock_client_cls.return_value = mock_client

        controller = OBSController(host="localhost", port=4455, password="test")
        scene = controller.current_scene()

        assert scene == "BRB"
