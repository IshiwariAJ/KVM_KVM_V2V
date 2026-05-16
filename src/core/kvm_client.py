"""KVMホストとの通信を担う層。libvirt API の呼び出しのみを行う。"""

import xml.etree.ElementTree as ET
from typing import List

import libvirt

from .host import HostConfig
from .vm_info import DiskInfo, VMInfo, VMState


# libvirt の状態コードを VMState に変換するマッピング
_LIBVIRT_STATE_MAP: dict[int, VMState] = {
    libvirt.VIR_DOMAIN_RUNNING: VMState.RUNNING,
    libvirt.VIR_DOMAIN_PAUSED: VMState.PAUSED,
    libvirt.VIR_DOMAIN_SHUTOFF: VMState.SHUT_OFF,
}


def _parse_disks(xml_str: str) -> List[DiskInfo]:
    """VM の XML 定義からファイルベースのディスク情報を抽出する。"""
    root = ET.fromstring(xml_str)
    disks: List[DiskInfo] = []
    for disk in root.findall(".//devices/disk[@type='file'][@device='disk']"):
        source = disk.find("source")
        target = disk.find("target")
        driver = disk.find("driver")
        if source is None or target is None:
            continue
        disks.append(DiskInfo(
            path=source.get("file", ""),
            device=target.get("dev", ""),
            fmt=driver.get("type", "qcow2") if driver is not None else "qcow2",
        ))
    return disks


def _domain_to_vm_info(domain: libvirt.virDomain) -> VMInfo:
    """libvirt のドメインオブジェクトを VMInfo に変換する。"""
    info = domain.info()
    state = _LIBVIRT_STATE_MAP.get(info[0], VMState.UNKNOWN)
    xml_str = domain.XMLDesc(libvirt.VIR_DOMAIN_XML_INACTIVE)
    return VMInfo(
        name=domain.name(),
        uuid=domain.UUIDString(),
        state=state,
        vcpus=info[3],
        memory_mb=info[1] // 1024,
        disks=_parse_disks(xml_str),
        xml=xml_str,
    )


class KVMClient:
    """libvirt への接続とVM操作を管理するクラス。"""

    def __init__(self, host_config: HostConfig) -> None:
        self._host_config = host_config
        self._conn: libvirt.virConnect | None = None

    # --- 接続管理 ---

    def connect(self) -> None:
        uri = self._host_config.libvirt_uri()
        self._conn = libvirt.open(uri)
        if self._conn is None:
            raise RuntimeError(f"libvirt への接続に失敗しました: {uri}")

    def disconnect(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "KVMClient":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # --- VM 情報取得 ---

    def list_vms(self) -> List[VMInfo]:
        """実行中・停止中を含む全 VM の一覧を返す。"""
        self._require_connected()
        vms: List[VMInfo] = []
        for domain_id in self._conn.listDomainsID():
            domain = self._conn.lookupByID(domain_id)
            vms.append(_domain_to_vm_info(domain))
        for name in self._conn.listDefinedDomains():
            domain = self._conn.lookupByName(name)
            vms.append(_domain_to_vm_info(domain))
        return sorted(vms, key=lambda v: v.name)

    def get_inactive_xml(self, vm_name: str) -> str:
        """停止状態の XML 定義を取得する (移行用)。"""
        self._require_connected()
        domain = self._conn.lookupByName(vm_name)
        return domain.XMLDesc(libvirt.VIR_DOMAIN_XML_INACTIVE)

    def get_vm_state(self, vm_name: str) -> VMState:
        self._require_connected()
        domain = self._conn.lookupByName(vm_name)
        info = domain.info()
        return _LIBVIRT_STATE_MAP.get(info[0], VMState.UNKNOWN)

    # --- VM 操作 ---

    def shutdown_vm(self, vm_name: str) -> None:
        """ACPI シャットダウン信号を送る。"""
        self._require_connected()
        domain = self._conn.lookupByName(vm_name)
        if domain.isActive():
            domain.shutdown()

    def define_vm(self, xml: str) -> None:
        """XML 定義から VM を登録する。"""
        self._require_connected()
        self._conn.defineXML(xml)

    def start_vm(self, vm_name: str) -> None:
        self._require_connected()
        domain = self._conn.lookupByName(vm_name)
        domain.create()

    # --- 内部ユーティリティ ---

    def _require_connected(self) -> None:
        if self._conn is None:
            raise RuntimeError("KVMClient が接続されていません。connect() を先に呼んでください。")
