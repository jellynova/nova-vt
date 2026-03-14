import sys
from PyQt6.QtWidgets import QApplication


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("nova-vt")
    # Dashboard window imported here once implemented
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
