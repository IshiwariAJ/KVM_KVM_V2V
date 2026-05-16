"""移行設定ダイアログ。"""

from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class MigrationSettings:
    target_storage_dir: str = "/var/lib/libvirt/images"
    shutdown_before_migrate: bool = True
    start_after_migrate: bool = False
    shutdown_timeout_sec: int = 120


class MigrationSettingsDialog(QDialog):
    """移行前に確認・変更できる設定値をまとめたダイアログ。"""

    def __init__(self, settings: MigrationSettings | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("移行設定")
        self.setMinimumWidth(440)
        initial = settings or MigrationSettings()
        self._setup_ui(initial)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self, s: MigrationSettings) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("移行先のストレージや動作オプションを設定してください。"))

        form = QFormLayout()
        form.addRow("移行先ストレージディレクトリ:", self._build_dir_row(s.target_storage_dir))
        form.addRow("", self._build_shutdown_checkbox(s.shutdown_before_migrate))
        form.addRow("", self._build_start_checkbox(s.start_after_migrate))
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_dir_row(self, default: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)

        self._dir_edit = QLineEdit(default)
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(32)
        browse_btn.clicked.connect(self._browse_dir)

        row.addWidget(self._dir_edit)
        row.addWidget(browse_btn)
        return container

    def _build_shutdown_checkbox(self, checked: bool) -> QCheckBox:
        self._shutdown_chk = QCheckBox("移行前に VM をシャットダウンする")
        self._shutdown_chk.setChecked(checked)
        return self._shutdown_chk

    def _build_start_checkbox(self, checked: bool) -> QCheckBox:
        self._start_chk = QCheckBox("移行後に VM を自動起動する")
        self._start_chk.setChecked(checked)
        return self._start_chk

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "ディレクトリを選択", self._dir_edit.text())
        if path:
            self._dir_edit.setText(path)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def get_settings(self) -> MigrationSettings:
        return MigrationSettings(
            target_storage_dir=self._dir_edit.text(),
            shutdown_before_migrate=self._shutdown_chk.isChecked(),
            start_after_migrate=self._start_chk.isChecked(),
        )
