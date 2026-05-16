"""バックグラウンド操作の汎用ワーカースレッド。"""

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.backup_manager import ProgressCallback


class OperationWorker(QThread):
    """
    任意の処理をバックグラウンドで実行する汎用ワーカー。
    操作関数は (ProgressCallback) -> None のシグネチャを持つ。
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, operation: Callable[[ProgressCallback], None]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            self._operation(lambda msg: self.progress.emit(msg))
            self.finished.emit(True, "全ての処理が完了しました。")
        except Exception as exc:
            self.finished.emit(False, str(exc))
