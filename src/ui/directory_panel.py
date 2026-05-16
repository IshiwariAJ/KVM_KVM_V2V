"""ローカルディレクトリを選択するウィジェット。"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DirectoryPanel(QWidget):
    """ディレクトリパスを入力・参照ダイアログで選択するシンプルなウィジェット。"""

    path_changed = pyqtSignal(str)

    def __init__(self, title: str, placeholder: str = "/path/to/directory", parent=None) -> None:
        super().__init__(parent)
        self._setup_ui(title, placeholder)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self, title: str, placeholder: str) -> None:
        outer = QVBoxLayout(self)
        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("ディレクトリパス:"))
        layout.addLayout(self._build_path_row(placeholder))
        layout.addStretch()

        outer.addWidget(group)

    def _build_path_row(self, placeholder: str) -> QHBoxLayout:
        row = QHBoxLayout()

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText(placeholder)
        self._path_edit.textChanged.connect(self.path_changed.emit)

        browse_btn = QPushButton("参照...")
        browse_btn.clicked.connect(self._browse)

        row.addWidget(self._path_edit)
        row.addWidget(browse_btn)
        return row

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "ディレクトリを選択", self._path_edit.text() or "/"
        )
        if path:
            self._path_edit.setText(path)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def get_path(self) -> str:
        return self._path_edit.text().strip()

    def set_path(self, path: str) -> None:
        self._path_edit.setText(path)
