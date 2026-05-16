"""バックアップタブ — KVM ホストの VM をローカルディレクトリに保存する。"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.core.backup_manager import backup_vm
from src.core.host import HostConfig
from src.core.kvm_client import KVMClient
from src.core.vm_info import VMInfo
from src.ui.directory_panel import DirectoryPanel
from src.ui.host_panel import HostPanel
from src.ui.operation_worker import OperationWorker
from src.ui.progress_dialog import ProgressDialog
from src.ui.vm_list_panel import VMListPanel


class BackupTab(QWidget):
    """KVM ホストから VM を選択し、ローカルディレクトリにバックアップする UI。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source_config: HostConfig | None = None
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

        self._source_panel = HostPanel("バックアップ元 KVM ホスト", connect_label="接続して VM 一覧を取得")
        self._source_panel.connect_requested.connect(self._on_source_connect)

        self._vm_list_panel = VMListPanel()

        self._dir_panel = DirectoryPanel(
            "バックアップ先ディレクトリ",
            placeholder="/mnt/backup/kvm",
        )

        splitter.addWidget(self._source_panel)
        splitter.addWidget(self._vm_list_panel)
        splitter.addWidget(self._dir_panel)
        splitter.setSizes([300, 600, 300])
        return splitter

    def _build_bottom_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._shutdown_chk = QCheckBox("バックアップ前に VM をシャットダウンする")
        self._shutdown_chk.setChecked(True)
        row.addWidget(self._shutdown_chk)
        row.addStretch()

        self._backup_btn = QPushButton("選択した VM をバックアップ ↓")
        self._backup_btn.setEnabled(False)
        self._backup_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #4CAF50; color: white;"
            "  padding: 10px 24px; font-size: 14px; border-radius: 4px;"
            "}"
            "QPushButton:hover { background-color: #388E3C; }"
            "QPushButton:disabled { background-color: #BDBDBD; }"
        )
        self._backup_btn.clicked.connect(self._on_backup)
        row.addWidget(self._backup_btn)
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
            QMessageBox.critical(self, "接続エラー", f"ホストへの接続に失敗しました:\n{exc}")
        finally:
            self._refresh_button()

    def _on_backup(self) -> None:
        selected = self._vm_list_panel.get_selected_vms()
        backup_dir = self._dir_panel.get_path()

        if not selected:
            QMessageBox.warning(self, "VM 未選択", "バックアップする VM を 1 つ以上選択してください。")
            return
        if not backup_dir:
            QMessageBox.warning(self, "保存先未指定", "バックアップ先ディレクトリを指定してください。")
            return
        if not self._confirm(selected, backup_dir):
            return

        self._run_backup(selected, backup_dir)

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _refresh_button(self) -> None:
        self._backup_btn.setEnabled(self._source_config is not None)

    def _confirm(self, vms: list[VMInfo], backup_dir: str) -> bool:
        names = "\n".join(f"  • {vm.name}" for vm in vms)
        reply = QMessageBox.question(
            self,
            "バックアップの確認",
            f"以下の {len(vms)} 個の VM をバックアップします:\n\n{names}\n\n"
            f"保存先: {backup_dir}\n\n実行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _run_backup(self, vms: list[VMInfo], backup_dir: str) -> None:
        source_host = self._source_config
        shutdown_before = self._shutdown_chk.isChecked()

        def operation(log):
            for vm in vms:
                backup_vm(
                    vm=vm,
                    source_host=source_host,
                    backup_base_dir=backup_dir,
                    log=log,
                    shutdown_before=shutdown_before,
                )

        dialog = ProgressDialog(self)
        self._worker = OperationWorker(operation)
        self._worker.progress.connect(dialog.append_log)
        self._worker.finished.connect(lambda ok, msg: dialog.set_finished(ok, msg))
        self._worker.start()
        dialog.exec()
