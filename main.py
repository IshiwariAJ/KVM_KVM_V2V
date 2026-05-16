import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("KVM VM 移行ツール")
    app.setStyle("Fusion")

    # ダークパレット寄りのニュートラルカラー
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F5F5F5"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#212121"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
