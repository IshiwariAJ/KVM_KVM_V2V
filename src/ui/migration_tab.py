"""移行タブ — KVM ホスト間で VM を直接コールド移行する。"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.core.host import HostConfig
from src.core.kvm_client import KVMClient
from src.core.migrator import MigrationConfig, VMmigrator
from src.core.vm_info import VMInfo
from src.ui.host_panel import HostPanel
from src.ui.migration_settings_dialog import MigrationSettings, MigrationSettingsDialog
from src.ui.operation_worker import OperationWorker
from src.ui.progress_dialog import ProgressDialog
from src.ui.vm_list_panel import VMListPanel


class MigrationTab(QWidget):
    """移行元ホスト → VM 選択 → 移行先ホスト の3ペイン移行 UI。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source_config: HostConfig | None = None
        self._target_config: HostConfig | None = None
        self._settings = MigrationSettings()
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

        self._source_panel = HostPanel("移行元ホスト", connect_label="接続して VM 一覧を取得")
        self._source_panel.connect_requested.connect(self._on_source_connect)

        self._vm_list_panel = VMListPanel()

        self._target_panel = HostPanel("移行先ホスト", connect_label="接続テスト")
        self._target_panel.connect_requested.connect(self._on_target_connect)

        splitter.addWidget(self._source_panel)
        splitter.addWidget(self._vm_list_panel)
        splitter.addWidget(self._target_panel)
        splitter.setSizes([300, 600, 300])
        return splitter

    def _build_bottom_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()

        settings_btn = QPushButton("⚙ 移行設定")
        settings_btn.clicked.connect(self._on_settings)
        row.addWidget(settings_btn)
        row.addStretch()

        self._migrate_btn = QPushButton("選択した VM を移行 →")
        self._migrate_btn.setEnabled(False)
        self._migrate_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #2196F3; color: white;"
            "  padding: 10px 24px; font-size: 14px; border-radius: 4px;"
            "}"
            "QPushButton:hover { background-color: #1976D2; }"
            "QPushButton:disabled { background-color: #BDBDBD; }"
        )
        self._migrate_btn.clicked.connect(self._on_migrate)
        row.addWidget(self._migrate_btn)
        return row

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------

    def _on_source_connect(self, config: HostConfig) -> None:
        try:
            with KVMClient(config) as client:
                vms = client.list_vms()
            self._source_config = config
            self._vm_list_panel.set_vms(vms)
            self._source_panel.set_status(f"✓ 接続済み ({len(vms)} VM)", ok=True)
        except Exception as exc:
            self._source_config = None
            self._source_panel.set_status("✗ 接続失敗", ok=False)
            QMessageBox.critical(self, "接続エラー", f"移行元への接続に失敗しました:\n{exc}")
        finally:
            self._refresh_button()

    def _on_target_connect(self, config: HostConfig) -> None:
        try:
            with KVMClient(config) as _:
                pass
            self._target_config = config
            self._target_panel.set_status(f"✓ 接続済み ({config.display_name()})", ok=True)
        except Exception as exc:
            self._target_config = None
            self._target_panel.set_status("✗ 接続失敗", ok=False)
            QMessageBox.critical(self, "接続エラー", f"移行先への接続に失敗しました:\n{exc}")
        finally:
            self._refresh_button()

    def _on_settings(self) -> None:
        dialog = MigrationSettingsDialog(self._settings, self)
        if dialog.exec():
            self._settings = dialog.get_settings()

    def _on_migrate(self) -> None:
        selected = self._vm_list_panel.get_selected_vms()
        if not selected:
            QMessageBox.warning(self, "VM 未選択", "移行する VM を 1 つ以上選択してください。")
            return
        if not self._confirm(selected):
            return
        self._run_migration(selected)

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _refresh_button(self) -> None:
        self._migrate_btn.setEnabled(
            self._source_config is not None and self._target_config is not None
        )

    def _confirm(self, vms: list[VMInfo]) -> bool:
        names = "\n".join(f"  • {vm.name}" for vm in vms)
        reply = QMessageBox.question(
            self,
            "移行の確認",
            f"以下の {len(vms)} 個の VM を移行します:\n\n{names}\n\n"
            f"移行先: {self._target_config.display_name()}\n"
            f"ストレージ: {self._settings.target_storage_dir}\n\n実行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _run_migration(self, vms: list[VMInfo]) -> None:
        config = MigrationConfig(
            source_host=self._source_config,
            target_host=self._target_config,
            target_storage_dir=self._settings.target_storage_dir,
            shutdown_before_migrate=self._settings.shutdown_before_migrate,
            start_after_migrate=self._settings.start_after_migrate,
            shutdown_timeout_sec=self._settings.shutdown_timeout_sec,
        )

        def operation(log):
            migrator = VMmigrator(config)
            migrator.set_progress_callback(log)
            migrator.migrate_all(vms)

        dialog = ProgressDialog(self)
        self._worker = OperationWorker(operation)
        self._worker.progress.connect(dialog.append_log)
        self._worker.finished.connect(lambda ok, msg: dialog.set_finished(ok, msg))
        self._worker.start()
        dialog.exec()
