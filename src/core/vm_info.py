from dataclasses import dataclass, field
from enum import Enum
from typing import List


class VMState(Enum):
    RUNNING = "実行中"
    PAUSED = "一時停止"
    SHUT_OFF = "停止"
    UNKNOWN = "不明"


@dataclass
class DiskInfo:
    path: str
    device: str   # vda, vdb, …
    fmt: str      # qcow2, raw, …


@dataclass
class VMInfo:
    name: str
    uuid: str
    state: VMState
    vcpus: int
    memory_mb: int
    disks: List[DiskInfo] = field(default_factory=list)
    xml: str = ""

    def total_disks(self) -> int:
        return len(self.disks)
