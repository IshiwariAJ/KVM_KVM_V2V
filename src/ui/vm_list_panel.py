"""VM 一覧表示・選択ウィジェット。"""

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.vm_info import VMInfo, VMState


_STATE_COLORS: dict[VMState, str] = {
    VMState.RUNNING: "#C8E6C9",
    VMState.PAUSED: "#FFF9C4",
    VMState.SHUT_OFF: "#FFCDD2",
    VMState.UNKNOWN: "#F5F5F5",
}

_COLUMNS = ["選択", "VM 名", "状態", "vCPU", "メモリ (MB)", "ディスク数"]


class VMListPanel(QWidget):
    """VM のリストを表示し、移行対象をチェックボックスで選択させる。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._vms: List[VMInfo] = []
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addLayout(self._build_header())
        layout.addWidget(self._build_table())
        layout.addWidget(self._build_footer_label())

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("仮想マシン一覧"))
        row.addStretch()

        for label, handler in [("全選択", self._select_all), ("全解除", self._deselect_all)]:
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        return row

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        return self._table

    def _build_footer_label(self) -> QLabel:
        self._count_label = QLabel("VM が見つかりません。ホストに接続してください。")
        return self._count_label

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_vms(self, vms: List[VMInfo]) -> None:
        self._vms = vms
        self._table.setRowCount(len(vms))
        for row, vm in enumerate(vms):
            self._fill_row(row, vm)
        self._count_label.setText(f"{len(vms)} 個の VM が見つかりました。")

    def get_selected_vms(self) -> List[VMInfo]:
        return [
            vm for i, vm in enumerate(self._vms)
            if self._is_checked(i)
        ]

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------

    def _select_all(self) -> None:
        self._set_all_checked(True)

    def _deselect_all(self) -> None:
        self._set_all_checked(False)

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _fill_row(self, row: int, vm: VMInfo) -> None:
        self._table.setCellWidget(row, 0, self._make_checkbox_cell())
        self._table.setItem(row, 1, QTableWidgetItem(vm.name))
        self._table.setItem(row, 2, self._make_state_item(vm.state))
        self._table.setItem(row, 3, QTableWidgetItem(str(vm.vcpus)))
        self._table.setItem(row, 4, QTableWidgetItem(str(vm.memory_mb)))
        self._table.setItem(row, 5, QTableWidgetItem(str(vm.total_disks())))

    @staticmethod
    def _make_checkbox_cell() -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QCheckBox())
        return container

    @staticmethod
    def _make_state_item(state: VMState) -> QTableWidgetItem:
        item = QTableWidgetItem(state.value)
        item.setBackground(QColor(_STATE_COLORS.get(state, "#F5F5F5")))
        return item

    def _get_checkbox(self, row: int) -> QCheckBox | None:
        cell = self._table.cellWidget(row, 0)
        if cell is None:
            return None
        return cell.findChild(QCheckBox)

    def _is_checked(self, row: int) -> bool:
        chk = self._get_checkbox(row)
        return chk is not None and chk.isChecked()

    def _set_all_checked(self, checked: bool) -> None:
        for i in range(self._table.rowCount()):
            chk = self._get_checkbox(i)
            if chk is not None:
                chk.setChecked(checked)
