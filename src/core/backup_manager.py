"""VM バックアップ・インポートのビジネスロジック。UI や libvirt の詳細に依存しない。"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List

from .host import HostConfig
from .kvm_client import KVMClient
from .migrator import MigrationError, normalize_machine_type, transfer_disk, update_xml_disk_paths, wait_for_shutdown
from .vm_info import VMInfo, VMState


ProgressCallback = Callable[[str], None]


# ---------------------------------------------------------------------------
# バックアップメタデータ
# ---------------------------------------------------------------------------

@dataclass
class VMBackup:
    """バックアップディレクトリ内の1 VM 分のメタデータ。"""
    vm_name: str
    backup_dir: str
    xml_path: str
    disk_filenames: List[str] = field(default_factory=list)
    backup_time: datetime | None = None

    def disk_paths(self) -> List[str]:
        return [os.path.join(self.backup_dir, f) for f in self.disk_filenames]


# ---------------------------------------------------------------------------
# バックアップ一覧取得 (純粋に I/O のみ、libvirt 不要)
# ---------------------------------------------------------------------------

def scan_backup_directory(backup_base_dir: str) -> List[VMBackup]:
    """
    指定ディレクトリ配下の VM バックアップを列挙する。
    各サブディレクトリに definition.xml が存在するものをバックアップとみなす。
    """
    if not os.path.isdir(backup_base_dir):
        return []

    backups: List[VMBackup] = []
    for entry in os.scandir(backup_base_dir):
        if not entry.is_dir():
            continue
        xml_path = os.path.join(entry.path, "definition.xml")
        if not os.path.exists(xml_path):
            continue

        disk_filenames = sorted(
            f.name for f in os.scandir(entry.path)
            if f.is_file() and f.name != "definition.xml"
        )
        backups.append(VMBackup(
            vm_name=entry.name,
            backup_dir=entry.path,
            xml_path=xml_path,
            disk_filenames=disk_filenames,
            backup_time=datetime.fromtimestamp(entry.stat().st_mtime),
        ))

    return sorted(backups, key=lambda b: b.vm_name)


# ---------------------------------------------------------------------------
# バックアップ
# ---------------------------------------------------------------------------

def _shutdown_if_needed(
    vm: VMInfo,
    source_host: HostConfig,
    shutdown_before: bool,
    shutdown_timeout: int,
    log: ProgressCallback,
) -> None:
    if not shutdown_before or vm.state != VMState.RUNNING:
        log("  シャットダウンをスキップします。")
        return
    log("  ACPI シャットダウンを送信中...")
    with KVMClient(source_host) as client:
        client.shutdown_vm(vm.name)
        wait_for_shutdown(client, vm.name, shutdown_timeout, log)
    log("  シャットダウン完了。")


def _export_xml_to_file(vm: VMInfo, source_host: HostConfig, vm_dir: str, log: ProgressCallback) -> None:
    log("  XML 定義を取得・保存中...")
    with KVMClient(source_host) as client:
        xml = client.get_inactive_xml(vm.name)
    xml_path = os.path.join(vm_dir, "definition.xml")
    try:
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml)
    except PermissionError as exc:
        raise MigrationError(
            f"バックアップ先への書き込みに失敗しました。\n"
            f"Samba マウントの書き込み権限を確認してください。\n"
            f"  マウント先: {vm_dir}\n"
            f"  ヒント: マウントオプション (uid, gid, file_mode) を /etc/fstab で確認してください。\n{exc}"
        ) from exc
    log(f"  XML 保存: {xml_path}")


def _copy_disks_to_backup(
    vm: VMInfo,
    source_host: HostConfig,
    vm_dir: str,
    log: ProgressCallback,
) -> None:
    local = HostConfig()
    for disk in vm.disks:
        filename = os.path.basename(disk.path)
        dst = os.path.join(vm_dir, filename)
        log(f"  ディスクコピー: {disk.path} → {dst}")
        transfer_disk(disk.path, dst, source_host, local, log)


def _check_writable(directory: str) -> None:
    """ディレクトリへの書き込み可否を確認する。書き込み不可の場合は MigrationError を送出する。"""
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=True):
            pass
    except PermissionError:
        raise MigrationError(
            f"バックアップ先ディレクトリへの書き込み権限がありません: {directory}\n"
            f"Samba マウントオプション (uid, gid, file_mode) を確認してください。\n"
            f"例 (fstab): //server/share /mnt/point cifs uid=1000,gid=1000,file_mode=0664,dir_mode=0775 0 0"
        )
    except OSError as exc:
        raise MigrationError(f"バックアップ先ディレクトリの確認中にエラーが発生しました: {exc}") from exc


def backup_vm(
    vm: VMInfo,
    source_host: HostConfig,
    backup_base_dir: str,
    log: ProgressCallback,
    shutdown_before: bool = True,
    shutdown_timeout: int = 120,
) -> None:
    """VM を {backup_base_dir}/{vm.name}/ にバックアップする。"""
    log(f"\n▶ [{vm.name}] バックアップ開始")

    vm_dir = os.path.join(backup_base_dir, vm.name)
    os.makedirs(vm_dir, exist_ok=True)
    _check_writable(vm_dir)

    _shutdown_if_needed(vm, source_host, shutdown_before, shutdown_timeout, log)

    _export_xml_to_file(vm, source_host, vm_dir, log)
    _copy_disks_to_backup(vm, source_host, vm_dir, log)

    log(f"✓ [{vm.name}] バックアップ完了: {vm_dir}")


# ---------------------------------------------------------------------------
# インポート
# ---------------------------------------------------------------------------

def _build_import_plan(
    xml: str,
    backup: VMBackup,
    target_storage_dir: str,
) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """
    インポート時の転送計画を構築する。
    戻り値:
      transfers      : [(バックアップ内ファイルパス, 転送先パス), ...]
      xml_update_map : {XML内元パス: 転送先パス, ...}
    """
    root = ET.fromstring(xml)
    transfers: list[tuple[str, str]] = []
    xml_update_map: dict[str, str] = {}

    for disk in root.findall(".//devices/disk[@type='file'][@device='disk']"):
        source = disk.find("source")
        if source is None:
            continue
        original_path = source.get("file", "")
        filename = os.path.basename(original_path)
        backup_file = os.path.join(backup.backup_dir, filename)
        target_path = os.path.join(target_storage_dir, filename)

        if os.path.exists(backup_file):
            transfers.append((backup_file, target_path))
            xml_update_map[original_path] = target_path

    return transfers, xml_update_map


def import_vm(
    backup: VMBackup,
    target_host: HostConfig,
    target_storage_dir: str,
    log: ProgressCallback,
    start_after: bool = False,
) -> None:
    """バックアップからターゲットホストに VM をインポートする。"""
    log(f"\n▶ [{backup.vm_name}] インポート開始")
    local = HostConfig()

    with open(backup.xml_path, "r", encoding="utf-8") as f:
        xml = f.read()

    transfers, xml_update_map = _build_import_plan(xml, backup, target_storage_dir)

    for src, dst in transfers:
        log(f"  ディスクコピー: {src} → {dst}")
        transfer_disk(src, dst, local, target_host, log)

    updated_xml = update_xml_disk_paths(xml, xml_update_map)
    updated_xml = normalize_machine_type(updated_xml)
    log("  VM を登録中...")
    with KVMClient(target_host) as client:
        client.define_vm(updated_xml)
        if start_after:
            log("  VM を起動中...")
            client.start_vm(backup.vm_name)

    log(f"✓ [{backup.vm_name}] インポート完了")
