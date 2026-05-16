"""メインウィンドウ。3つのタブを QTabWidget で束ねる。"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.backup_tab import BackupTab
from src.ui.import_tab import ImportTab
from src.ui.migration_tab import MigrationTab


class MainWindow(QMainWindow):
    """移行 / バックアップ / インポートの3モードをタブで切り替えるメインウィンドウ。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KVM VM 移行ツール")
        self.setMinimumSize(1200, 700)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addWidget(self._build_title())
        layout.addWidget(self._build_tabs(), stretch=1)

        self.statusBar().showMessage("タブを選択して操作を開始してください。")

    def _build_title(self) -> QLabel:
        label = QLabel("KVM 仮想マシン管理ツール")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px;")
        return label

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(MigrationTab(), "🔄  移行  (ホスト → ホスト)")
        tabs.addTab(BackupTab(),    "💾  バックアップ  (ホスト → ディレクトリ)")
        tabs.addTab(ImportTab(),    "📥  インポート  (ディレクトリ → ホスト)")
        return tabs
