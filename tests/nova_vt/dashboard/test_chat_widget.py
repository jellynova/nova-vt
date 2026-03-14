import sys
import pytest
from dataclasses import dataclass
from PyQt6.QtWidgets import QApplication, QTabWidget, QListWidget, QLineEdit, QPushButton
from PyQt6.QtCore import Qt
from nova_vt.dashboard.chat_widget import ChatWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@dataclass
class FakeChatMessage:
    platform: str
    username: str
    color: str
    text: str
    event_type: str = "message"


def test_chat_widget_has_four_tabs(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    tabs = widget.findChildren(QTabWidget)
    assert len(tabs) == 1
    tab = tabs[0]
    assert tab.count() == 4
    labels = [tab.tabText(i) for i in range(tab.count())]
    assert labels == ["All", "Twitch", "YouTube", "TikTok"]


def test_chat_widget_message_appears_in_all_tab(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="twitch", username="viewer1", color="#9146FF", text="Hello!")
    widget.add_message(msg)
    all_list = widget._lists["All"]
    assert all_list.count() == 1
    assert "viewer1" in all_list.item(0).text()
    assert "Hello!" in all_list.item(0).text()


def test_chat_widget_message_appears_in_platform_tab(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="youtube", username="yt_fan", color="#FF0000", text="Nice stream")
    widget.add_message(msg)
    yt_list = widget._lists["YouTube"]
    assert yt_list.count() == 1
    assert "yt_fan" in yt_list.item(0).text()


def test_chat_widget_twitch_message_not_in_youtube_tab(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="twitch", username="twitch_user", color="#9146FF", text="hi")
    widget.add_message(msg)
    yt_list = widget._lists["YouTube"]
    assert yt_list.count() == 0


def test_chat_widget_sub_event_highlighted(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="twitch", username="subber", color="#9146FF", text="subscribed!", event_type="sub")
    widget.add_message(msg)
    all_list = widget._lists["All"]
    item = all_list.item(0)
    # Sub events should have a different foreground color
    assert item.foreground().color().name() != "#e2e8f0"


def test_chat_widget_has_reply_input(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    assert widget._reply_input is not None
    assert isinstance(widget._reply_input, QLineEdit)


def test_chat_widget_has_send_button(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    assert widget._send_button is not None
    assert isinstance(widget._send_button, QPushButton)


def test_chat_widget_send_emits_signal(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget._reply_input.setText("test message")
    with qtbot.waitSignal(widget.message_send_requested, timeout=500) as blocker:
        qtbot.mouseClick(widget._send_button, Qt.MouseButton.LeftButton)
    assert blocker.args[0] == "test message"


def test_chat_widget_send_clears_input(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget._reply_input.setText("something")
    qtbot.mouseClick(widget._send_button, Qt.MouseButton.LeftButton)
    assert widget._reply_input.text() == ""


def test_chat_widget_send_includes_platform_when_tab_selected(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    widget.show()
    # Switch to Twitch tab (index 1)
    widget._tabs.setCurrentIndex(1)
    widget._reply_input.setText("hello twitch")
    signals = []
    widget.message_send_requested.connect(lambda text, plat: signals.append((text, plat)))
    qtbot.mouseClick(widget._send_button, Qt.MouseButton.LeftButton)
    assert signals[0] == ("hello twitch", "twitch")


def test_chat_widget_multiple_messages_prepend(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    for i in range(3):
        msg = FakeChatMessage(platform="twitch", username=f"user{i}", color="#fff", text=f"msg{i}")
        widget.add_message(msg)
    all_list = widget._lists["All"]
    assert all_list.count() == 3
    # Most recent message should be at the top (row 0)
    assert "user2" in all_list.item(0).text()
