"""ホスト接続設定ウィジェット。"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.host import ConnectionType, HostConfig


class HostPanel(QWidget):
    """接続先ホストの種別・認証情報を入力し、接続要求シグナルを発行する。"""

    connect_requested = pyqtSignal(object)  # HostConfig

    def __init__(self, title: str, connect_label: str = "接続", parent=None) -> None:
        super().__init__(parent)
        self._setup_ui(title, connect_label)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self, title: str, connect_label: str) -> None:
        outer = QVBoxLayout(self)

        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        layout.addLayout(self._build_type_row())
        layout.addWidget(self._build_ssh_fields())
        layout.addWidget(self._build_connect_button(connect_label))
        layout.addWidget(self._build_status_label())
        layout.addStretch()

        outer.addWidget(group)

    def _build_type_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._local_radio = QRadioButton("ローカル")
        self._ssh_radio = QRadioButton("SSH")
        self._local_radio.setChecked(True)
        self._local_radio.toggled.connect(self._on_type_toggled)
        row.addWidget(self._local_radio)
        row.addWidget(self._ssh_radio)
        row.addStretch()
        return row

    def _build_ssh_fields(self) -> QWidget:
        self._ssh_widget = QWidget()
        form = QFormLayout(self._ssh_widget)

        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("192.168.1.100")
        form.addRow("ホスト:", self._host_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(22)
        form.addRow("ポート:", self._port_spin)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("ubuntu")
        form.addRow("ユーザー:", self._user_edit)

        form.addRow("SSHキー:", self._build_key_row())

        self._ssh_widget.setEnabled(False)
        return self._ssh_widget

    def _build_key_row(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("~/.ssh/id_rsa  (省略可)")
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(32)
        browse_btn.clicked.connect(self._browse_key)

        row.addWidget(self._key_edit)
        row.addWidget(browse_btn)
        return container

    def _build_connect_button(self, label: str) -> QPushButton:
        self._connect_btn = QPushButton(label)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        return self._connect_btn

    def _build_status_label(self) -> QLabel:
        self._status_label = QLabel("未接続")
        self._status_label.setStyleSheet("color: gray;")
        return self._status_label

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------

    def _on_type_toggled(self, local_selected: bool) -> None:
        self._ssh_widget.setEnabled(not local_selected)

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "SSH 秘密鍵を選択", "", "All Files (*)")
        if path:
            self._key_edit.setText(path)

    def _on_connect_clicked(self) -> None:
        self.connect_requested.emit(self._build_host_config())

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_status(self, message: str, *, ok: bool) -> None:
        self._status_label.setText(message)
        self._status_label.setStyleSheet(f"color: {'green' if ok else 'red'};")

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _build_host_config(self) -> HostConfig:
        if self._local_radio.isChecked():
            return HostConfig(name="ローカル", connection_type=ConnectionType.LOCAL)
        return HostConfig(
            name=self._host_edit.text(),
            connection_type=ConnectionType.SSH,
            host=self._host_edit.text(),
            port=self._port_spin.value(),
            username=self._user_edit.text(),
            ssh_key_path=self._key_edit.text(),
        )
