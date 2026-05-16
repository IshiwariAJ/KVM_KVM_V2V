"""移行進捗ダイアログ。"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class ProgressDialog(QDialog):
    """移行中のログと進捗を表示し、完了後にユーザーが閉じるダイアログ。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("移行進捗")
        self.setMinimumSize(640, 420)
        self._closeable = False
        self._setup_ui()

    # ------------------------------------------------------------------
    # イベントオーバーライド (操作中は閉じさせない)
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._closeable:
            event.accept()
        else:
            event.ignore()

    def reject(self) -> None:
        # Escape キーで誤って閉じないようにする
        if self._closeable:
            super().reject()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(self._build_status_label())
        layout.addWidget(self._build_progress_bar())
        layout.addWidget(self._build_log_area())
        layout.addLayout(self._build_button_row())

    def _build_status_label(self) -> QLabel:
        self._status_label = QLabel("移行中...")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        return self._status_label

    def _build_progress_bar(self) -> QProgressBar:
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # 不定モード
        return self._progress_bar

    def _build_log_area(self) -> QTextEdit:
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QFont("Monospace", 9))
        self._log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        return self._log_text

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._close_btn = QPushButton("閉じる")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(self._close_btn)
        return row

    # ------------------------------------------------------------------
    # 公開 API (スレッドから呼ばれる想定のシグナル経由メソッド)
    # ------------------------------------------------------------------

    def append_log(self, message: str) -> None:
        self._log_text.append(message)
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log_text.setTextCursor(cursor)

    def set_finished(self, success: bool, message: str) -> None:
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100)

        if success:
            self._status_label.setText(f"✓ {message}")
            self._status_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: green;"
            )
            self._progress_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #4CAF50; }"
            )
        else:
            self._status_label.setText(f"✗ エラー: {message}")
            self._status_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: red;"
            )
            self._progress_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #F44336; }"
            )

        self._closeable = True
        self._close_btn.setEnabled(True)
