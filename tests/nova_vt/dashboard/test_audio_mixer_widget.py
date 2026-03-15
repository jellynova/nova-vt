import sys
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication, QSlider, QPushButton, QProgressBar
from PyQt6.QtCore import Qt
from nova_vt.dashboard.audio_mixer import AudioMixerWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


CHANNELS = ["mic", "game", "bgm", "master"]
DEFAULTS = {"mic": 75, "game": 60, "bgm": 30, "master": 90}


def make_widget(qtbot):
    mock_mixer = MagicMock()
    # AudioMixerWidget calls get_peaks() → dict[str, float]
    mock_mixer.get_peaks = MagicMock(return_value={ch: 0.0 for ch in ["mic", "game", "bgm", "master"]})
    widget = AudioMixerWidget(mixer=mock_mixer)
    qtbot.addWidget(widget)
    return widget, mock_mixer


def test_audio_mixer_has_four_channels(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    sliders = widget.findChildren(QSlider)
    assert len(sliders) == 4


def test_audio_mixer_default_values(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    for ch, expected in DEFAULTS.items():
        assert widget.get_volume(ch) == expected, f"{ch} should default to {expected}"


def test_audio_mixer_slider_change_updates_volume(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    widget._sliders["mic"].setValue(50)
    assert widget.get_volume("mic") == 50


def test_audio_mixer_slider_calls_mixer_set_volume(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    widget._sliders["game"].setValue(40)
    mock_mixer.set_volume.assert_called_with("game", 40)


def test_audio_mixer_mute_toggle_calls_mixer(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    widget.show()
    mute_btn = widget._mute_buttons["mic"]
    qtbot.mouseClick(mute_btn, Qt.MouseButton.LeftButton)
    mock_mixer.set_mute.assert_called_with("mic", True)
    qtbot.mouseClick(mute_btn, Qt.MouseButton.LeftButton)
    mock_mixer.set_mute.assert_called_with("mic", False)


def test_audio_mixer_has_vu_meters(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    meters = widget.findChildren(QProgressBar)
    assert len(meters) == 4


def test_audio_mixer_vu_meter_range(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    for ch in CHANNELS:
        bar = widget._vu_meters[ch]
        assert bar.minimum() == 0
        assert bar.maximum() == 100


def test_audio_mixer_vu_update_from_mock(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    mock_mixer.get_peaks.return_value = {ch: 0.75 for ch in CHANNELS}
    widget._update_vu_meters()
    for ch in CHANNELS:
        assert widget._vu_meters[ch].value() == 75


def test_audio_mixer_end_stream_button_exists(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    assert widget._end_stream_btn is not None


def test_audio_mixer_end_stream_emits_signal(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    widget.show()
    with qtbot.waitSignal(widget.end_stream_requested, timeout=500):
        qtbot.mouseClick(widget._end_stream_btn, Qt.MouseButton.LeftButton)


def test_audio_mixer_end_stream_disabled_when_not_live(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    widget.set_live(False)
    assert not widget._end_stream_btn.isEnabled()


def test_audio_mixer_end_stream_enabled_when_live(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    widget.set_live(True)
    assert widget._end_stream_btn.isEnabled()
