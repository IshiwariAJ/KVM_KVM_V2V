"""インポートタブ — バックアップディレクトリから KVM ホストに VM を復元する。"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.core.backup_manager import VMBackup, import_vm, scan_backup_directory
from src.core.host import HostConfig
from src.core.kvm_client import KVMClient
from src.ui.backup_list_panel import BackupListPanel
from src.ui.directory_panel import DirectoryPanel
from src.ui.host_panel import HostPanel
from src.ui.operation_worker import OperationWorker
from src.ui.progress_dialog import ProgressDialog


class ImportTab(QWidget):
    """バックアップディレクトリを参照し、KVM ホストへ VM をインポートする UI。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._target_config: HostConfig | None = None
        self._worker: OperationWorker | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_panels(), stretch=1)
        layout.addLayout(self._build_bottom_bar())

    def _build_panels(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(self._build_source_panel())
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_target_panel())
        splitter.setSizes([300, 600, 300])
        return splitter

    def _build_source_panel(self) -> QWidget:
        """バックアップ元ディレクトリ選択パネル。"""
        container = QWidget()
        layout = QVBoxLayout(container)

        self._dir_panel = DirectoryPanel(
            "バックアップ元ディレクトリ",
            placeholder="/mnt/backup/kvm",
        )
        scan_btn = QPushButton("🔍 スキャン")
        scan_btn.clicked.connect(self._on_scan)

        layout.addWidget(self._dir_panel)
        layout.addWidget(scan_btn)
        layout.addStretch()
        return container

    def _build_list_panel(self) -> QWidget:
        self._backup_list_panel = BackupListPanel()
        return self._backup_list_panel

    def _build_target_panel(self) -> QWidget:
        """インポート先 KVM ホストとストレージ設定パネル。"""
        container = QWidget()
        layout = QVBoxLayout(container)

        self._target_host_panel = HostPanel("インポート先 KVM ホスト", connect_label="接続テスト")
        self._target_host_panel.connect_requested.connect(self._on_target_connect)
        layout.addWidget(self._target_host_panel)

        layout.addWidget(self._build_storage_group())
        layout.addStretch()
        return container

    def _build_storage_group(self) -> QGroupBox:
        group = QGroupBox("ストレージ設定")
        form = QFormLayout(group)

        self._storage_dir_edit = QLineEdit("/var/lib/libvirt/images")
        form.addRow("ディスク保存先:", self._storage_dir_edit)

        self._start_chk = QCheckBox("インポート後に VM を自動起動する")
        form.addRow("", self._start_chk)

        return group

    def _build_bottom_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()

        self._import_btn = QPushButton("選択した VM をインポート ↑")
        self._import_btn.setEnabled(False)
        self._import_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #FF9800; color: white;"
            "  padding: 10px 24px; font-size: 14px; border-radius: 4px;"
            "}"
            "QPushButton:hover { background-color: #F57C00; }"
            "QPushButton:disabled { background-color: #BDBDBD; }"
        )
        self._import_btn.clicked.connect(self._on_import)
        row.addWidget(self._import_btn)
        return row

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------

    def _on_scan(self) -> None:
        backup_dir = self._dir_panel.get_path()
        if not backup_dir:
            QMessageBox.warning(self, "ディレクトリ未指定", "バックアップ元ディレクトリを指定してください。")
            return
        backups = scan_backup_directory(backup_dir)
        self._backup_list_panel.set_backups(backups)
        if not backups:
            QMessageBox.information(
                self, "バックアップなし",
                f"指定ディレクトリに VM バックアップが見つかりませんでした:\n{backup_dir}"
            )

    def _on_target_connect(self, config: HostConfig) -> None:
        try:
            with KVMClient(config) as _:
                pass
            self._target_config = config
            self._target_host_panel.set_status(f"✓ 接続済み ({config.display_name()})", ok=True)
        except Exception as exc:
            self._target_config = None
            self._target_host_panel.set_status("✗ 接続失敗", ok=False)
            QMessageBox.critical(self, "接続エラー", f"インポート先への接続に失敗しました:\n{exc}")
        finally:
            self._refresh_button()

    def _on_import(self) -> None:
        selected = self._backup_list_panel.get_selected_backups()
        storage_dir = self._storage_dir_edit.text().strip()

        if not selected:
            QMessageBox.warning(self, "未選択", "インポートするバックアップを 1 つ以上選択してください。")
            return
        if not storage_dir:
            QMessageBox.warning(self, "ディレクトリ未指定", "ディスク保存先ディレクトリを指定してください。")
            return
        if not self._confirm(selected, storage_dir):
            return

        self._run_import(selected, storage_dir)

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _refresh_button(self) -> None:
        self._import_btn.setEnabled(self._target_config is not None)

    def _confirm(self, backups: list[VMBackup], storage_dir: str) -> bool:
        names = "\n".join(f"  • {b.vm_name}" for b in backups)
        reply = QMessageBox.question(
            self,
            "インポートの確認",
            f"以下の {len(backups)} 個の VM をインポートします:\n\n{names}\n\n"
            f"インポート先: {self._target_config.display_name()}\n"
            f"ストレージ: {storage_dir}\n\n実行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _run_import(self, backups: list[VMBackup], storage_dir: str) -> None:
        target_host = self._target_config
        start_after = self._start_chk.isChecked()

        def operation(log):
            for backup in backups:
                import_vm(
                    backup=backup,
                    target_host=target_host,
                    target_storage_dir=storage_dir,
                    log=log,
                    start_after=start_after,
                )

        dialog = ProgressDialog(self)
        self._worker = OperationWorker(operation)
        self._worker.progress.connect(dialog.append_log)
        self._worker.finished.connect(lambda ok, msg: dialog.set_finished(ok, msg))
        self._worker.start()
        dialog.exec()
