import sys
import pytest
from PyQt6.QtWidgets import QApplication, QLabel
from nova_vt.dashboard.platform_stats import PlatformStatsWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def test_platform_stats_has_three_rows(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    assert widget._rows["twitch"] is not None
    assert widget._rows["youtube"] is not None
    assert widget._rows["tiktok"] is not None


def test_platform_stats_initial_zero(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    for plat in ("twitch", "youtube", "tiktok"):
        label = widget._viewer_labels[plat]
        assert "0" in label.text()


def test_platform_stats_update_viewer_count(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    widget.update_stats("twitch", viewers=1234, likes=56)
    label = widget._viewer_labels["twitch"]
    assert "1234" in label.text()


def test_platform_stats_update_likes(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    widget.update_stats("youtube", viewers=500, likes=99)
    label = widget._likes_labels["youtube"]
    assert "99" in label.text()


def test_platform_stats_twitch_color_coded(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    row = widget._rows["twitch"]
    sheet = row.styleSheet()
    assert "#9146FF" in sheet or "#9146ff" in sheet.lower()


def test_platform_stats_update_from_stream_stats(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    stats = {
        "twitch": {"viewers": 300, "likes": 10},
        "youtube": {"viewers": 150, "likes": 5},
        "tiktok": {"viewers": 75, "likes": 200},
    }
    widget.update_from_stream_stats(stats)
    assert "300" in widget._viewer_labels["twitch"].text()
    assert "150" in widget._viewer_labels["youtube"].text()
    assert "75" in widget._viewer_labels["tiktok"].text()
