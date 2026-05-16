"""VM 移行のビジネスロジック。UI や libvirt の詳細に依存しない。"""

import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, List

from .host import ConnectionType, HostConfig
from .kvm_client import KVMClient
from .vm_info import VMInfo, VMState


# ---------------------------------------------------------------------------
# 設定データクラス
# ---------------------------------------------------------------------------

@dataclass
class MigrationConfig:
    source_host: HostConfig
    target_host: HostConfig
    target_storage_dir: str = "/var/lib/libvirt/images"
    shutdown_before_migrate: bool = True
    start_after_migrate: bool = False
    shutdown_timeout_sec: int = 120


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------

class MigrationError(Exception):
    pass


# ---------------------------------------------------------------------------
# ロガーコールバック型エイリアス
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[str], None]


# ---------------------------------------------------------------------------
# XML 変換 (純粋関数)
# ---------------------------------------------------------------------------

def update_xml_disk_paths(xml_str: str, path_map: dict[str, str]) -> str:
    """XML 内のディスクパスを path_map に従って置き換えた新しい XML を返す。"""
    root = ET.fromstring(xml_str)
    for disk in root.findall(".//devices/disk[@type='file'][@device='disk']"):
        source = disk.find("source")
        if source is not None:
            old_path = source.get("file", "")
            if old_path in path_map:
                source.set("file", path_map[old_path])
    return ET.tostring(root, encoding="unicode")


def normalize_machine_type(xml_str: str) -> str:
    """machine type のバージョン番号を除去する (例: 'pc-q35-10.2' → 'pc-q35')。
    移行先 QEMU が古い場合の互換性エラーを回避する。"""
    root = ET.fromstring(xml_str)
    for os_type in root.findall(".//os/type"):
        machine = os_type.get("machine", "")
        if machine:
            normalized = re.sub(r"-\d+\.\d+$", "", machine)
            if normalized != machine:
                os_type.set("machine", normalized)
    return ET.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# ディスク転送 (副作用のある関数)
# ---------------------------------------------------------------------------

def _is_user_fuse_path(path: str) -> bool:
    """GVFS 等のユーザー FUSE マウント (/run/user/ 以下) は sudo から参照不可。"""
    return path.startswith("/run/user/")


def _build_rsync_cmd(
    src_path: str,
    dst_path: str,
    src_host: HostConfig,
    dst_host: HostConfig,
) -> list[str]:
    """rsync コマンドのリストを組み立てる。"""
    src_spec = f"{src_host.rsync_prefix()}{src_path}"
    dst_spec = f"{dst_host.rsync_prefix()}{dst_path}"

    ssh_opts: list[str] = []
    for h in (src_host, dst_host):
        if h.connection_type == ConnectionType.SSH:
            ssh_opts += h.ssh_opts()
            break  # rsync は -e に渡す SSH オプションは1つだけ

    # /var/lib/libvirt/images/ 等は root 所有 600 のため、ローカルがソースの場合は sudo が必要
    prefix = ["sudo"] if src_host.connection_type == ConnectionType.LOCAL else []
    cmd = prefix + ["rsync", "-avz", "--progress", src_spec, dst_spec]
    if ssh_opts:
        cmd += ["-e", "ssh " + " ".join(ssh_opts)]
    return cmd


def _stream_gvfs_to_local(src_path: str, dst_path: str, log: ProgressCallback) -> None:
    """/tmp を使わず GVFS → ローカルターゲットへ直接ストリームコピーする。
    ユーザープロセスが GVFS ファイルを開き、stdin 経由で sudo tee に渡す。
    """
    try:
        size_mb = os.path.getsize(src_path) // (1024 * 1024)
        log(f"  直接コピー中 ({size_mb} MB): {src_path} → {dst_path}")
    except OSError:
        log(f"  直接コピー中: {src_path} → {dst_path}")
    try:
        src_file = open(src_path, "rb")  # noqa: WPS515  — with 外で開く必要あり
    except PermissionError as exc:
        raise MigrationError(
            f"GVFS ファイルを読み取れませんでした。\n"
            f"Samba 共有の読み取り権限を確認してください。\n{exc}"
        ) from exc
    with src_file:
        proc = subprocess.Popen(
            ["sudo", "tee", dst_path],
            stdin=src_file,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _, stderr = proc.communicate()
    if proc.returncode != 0:
        raise MigrationError(
            f"コピー失敗 (sudo tee):\n{stderr.decode('utf-8', errors='replace')}"
        )
    log("  コピー完了")


def _transfer_fuse_source(
    src_path: str,
    dst_path: str,
    dst_host: HostConfig,
    log: ProgressCallback,
) -> None:
    """GVFS 等の FUSE マウントからの転送 (インポート用)。
    ローカルターゲットは /tmp を介さず sudo tee で直接ストリームコピーする。
    SSH ターゲットは /tmp を中継する。
    """
    if dst_host.connection_type == ConnectionType.LOCAL:
        _stream_gvfs_to_local(src_path, dst_path, log)
        return

    # SSH ターゲット: /tmp を中継
    filename = os.path.basename(dst_path)
    with tempfile.TemporaryDirectory(prefix="kvm_import_") as tmp_dir:
        tmp_path = os.path.join(tmp_dir, filename)

        try:
            size_mb = os.path.getsize(src_path) // (1024 * 1024)
            size_info = f" ({size_mb} MB)"
        except OSError:
            size_info = ""
        log(f"  ステップ 1/2: GVFS → 一時ディレクトリ{size_info}: {src_path}")
        try:
            shutil.copy2(src_path, tmp_path)
        except PermissionError as exc:
            raise MigrationError(
                f"GVFS ファイルを読み取れませんでした。\n"
                f"Samba 共有の読み取り権限を確認してください。\n{exc}"
            ) from exc
        log("  ステップ 1/2: 完了")

        local = HostConfig()
        step2_cmd = _build_rsync_cmd(tmp_path, dst_path, local, dst_host)
        log(f"  ステップ 2/2: 一時ディレクトリ → コピー先: {' '.join(step2_cmd)}")
        r2 = subprocess.run(step2_cmd, capture_output=True, text=True)
        if r2.returncode != 0:
            raise MigrationError(f"rsync 失敗 (ステップ 2/2):\n{r2.stderr}")


def _transfer_to_fuse_dest(
    src_path: str,
    dst_path: str,
    src_host: HostConfig,
    log: ProgressCallback,
) -> None:
    """GVFS 等の FUSE マウントへの転送 (バックアップ用)。
    sudo rsync は GVFS に書き込めないため /tmp を中継し、shutil で GVFS へ書き込む。
    ローカルソースが root 所有の場合は --chmod=644 で /tmp 内ファイルをユーザー可読にする。
    """
    filename = os.path.basename(dst_path)
    with tempfile.TemporaryDirectory(prefix="kvm_backup_") as tmp_dir:
        tmp_path = os.path.join(tmp_dir, filename)
        local = HostConfig()

        log(f"  ステップ 1/2: コピー元 → 一時ディレクトリ: {src_path}")
        if src_host.connection_type == ConnectionType.LOCAL:
            # root 所有ファイルを sudo rsync で読み、/tmp にはユーザーが読めるモードで書く
            step1_cmd = [
                "sudo", "rsync", "-avz", "--progress",
                "--no-perms", "--chmod=644",
                src_path, tmp_path,
            ]
        else:
            # SSH ソース: sudo 不要
            step1_cmd = _build_rsync_cmd(src_path, tmp_path, src_host, local)
        r1 = subprocess.run(step1_cmd, capture_output=True, text=True)
        if r1.returncode != 0:
            raise MigrationError(f"コピー失敗 (ステップ 1/2):\n{r1.stderr}")
        log("  ステップ 1/2: 完了")

        try:
            size_mb = os.path.getsize(tmp_path) // (1024 * 1024)
            size_info = f" ({size_mb} MB)"
        except OSError:
            size_info = ""
        log(f"  ステップ 2/2: 一時ディレクトリ → GVFS{size_info}: {dst_path}")
        try:
            shutil.copyfile(tmp_path, dst_path)
        except PermissionError as exc:
            raise MigrationError(
                f"GVFS への書き込みに失敗しました。\n"
                f"Samba 共有の書き込み権限を確認してください。\n{exc}"
            ) from exc
        except OSError as exc:
            raise MigrationError(
                f"GVFS へのコピーに失敗しました。\n{exc}"
            ) from exc
        log("  ステップ 2/2: 完了")


def _transfer_disk_direct(
    src_path: str,
    dst_path: str,
    src_host: HostConfig,
    dst_host: HostConfig,
    log: ProgressCallback,
) -> None:
    """rsync を使い、ローカル/リモートを問わずディスクを転送する。"""
    # GVFS 等のユーザー FUSE マウントはソースでも宛先でも sudo から参照不可
    if src_host.connection_type == ConnectionType.LOCAL and _is_user_fuse_path(src_path):
        _transfer_fuse_source(src_path, dst_path, dst_host, log)
        return
    if dst_host.connection_type == ConnectionType.LOCAL and _is_user_fuse_path(dst_path):
        _transfer_to_fuse_dest(src_path, dst_path, src_host, log)
        return

    cmd = _build_rsync_cmd(src_path, dst_path, src_host, dst_host)
    log(f"  実行: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise MigrationError(f"rsync 失敗:\n{result.stderr}")


def _transfer_disk_via_local(
    src_path: str,
    dst_path: str,
    src_host: HostConfig,
    dst_host: HostConfig,
    log: ProgressCallback,
) -> None:
    """両方がリモートの場合: 一時ディレクトリを中継してコピーする。"""
    filename = os.path.basename(src_path)
    with tempfile.TemporaryDirectory(prefix="kvm_migrate_") as tmp_dir:
        tmp_path = os.path.join(tmp_dir, filename)
        local = HostConfig()  # ローカルホスト設定

        log("  ステップ 1/2: リモートソース → ローカル一時ディレクトリ")
        _transfer_disk_direct(src_path, tmp_path, src_host, local, log)

        log("  ステップ 2/2: ローカル一時ディレクトリ → リモートターゲット")
        _transfer_disk_direct(tmp_path, dst_path, local, dst_host, log)


def transfer_disk(
    src_path: str,
    dst_path: str,
    src_host: HostConfig,
    dst_host: HostConfig,
    log: ProgressCallback,
) -> None:
    """転送元・転送先に応じて適切な転送方式を選択する。"""
    both_remote = (
        src_host.connection_type == ConnectionType.SSH
        and dst_host.connection_type == ConnectionType.SSH
    )
    if both_remote:
        _transfer_disk_via_local(src_path, dst_path, src_host, dst_host, log)
    else:
        _transfer_disk_direct(src_path, dst_path, src_host, dst_host, log)


# ---------------------------------------------------------------------------
# シャットダウン待機
# ---------------------------------------------------------------------------

def wait_for_shutdown(client: KVMClient, vm_name: str, timeout_sec: int, log: ProgressCallback) -> None:
    """VM が停止するまでポーリングする。タイムアウト時は例外を送出する。"""
    elapsed = 0
    interval = 3
    while elapsed < timeout_sec:
        state = client.get_vm_state(vm_name)
        if state == VMState.SHUT_OFF:
            return
        log(f"  シャットダウン待機中... ({elapsed}s / {timeout_sec}s)")
        time.sleep(interval)
        elapsed += interval
    raise MigrationError(f"VM '{vm_name}' のシャットダウンがタイムアウトしました ({timeout_sec}s)")


# ---------------------------------------------------------------------------
# VM 単体の移行ステップ
# ---------------------------------------------------------------------------

def _step_shutdown(vm: VMInfo, config: MigrationConfig, log: ProgressCallback) -> None:
    if vm.state != VMState.RUNNING:
        log("  VM は既に停止しています。シャットダウンをスキップします。")
        return
    if not config.shutdown_before_migrate:
        log("  設定によりシャットダウンをスキップします。")
        return
    log("  ACPI シャットダウンを送信中...")
    with KVMClient(config.source_host) as client:
        client.shutdown_vm(vm.name)
        wait_for_shutdown(client, vm.name, config.shutdown_timeout_sec, log)
    log("  シャットダウン完了。")


def _step_export_xml(vm: VMInfo, config: MigrationConfig, log: ProgressCallback) -> str:
    log("  XML 定義を取得中...")
    with KVMClient(config.source_host) as client:
        return client.get_inactive_xml(vm.name)


def _step_transfer_disks(
    vm: VMInfo,
    config: MigrationConfig,
    log: ProgressCallback,
) -> dict[str, str]:
    """全ディスクを転送し、旧パス → 新パスの対応辞書を返す。"""
    path_map: dict[str, str] = {}
    for disk in vm.disks:
        filename = os.path.basename(disk.path)
        dst_path = os.path.join(config.target_storage_dir, filename)
        log(f"  ディスク転送: {disk.path} → {dst_path}")
        transfer_disk(disk.path, dst_path, config.source_host, config.target_host, log)
        path_map[disk.path] = dst_path
        log(f"  転送完了: {dst_path}")
    return path_map


def _step_define_vm(
    vm_name: str,
    xml: str,
    config: MigrationConfig,
    log: ProgressCallback,
) -> None:
    log("  移行先ホストに VM を登録中...")
    with KVMClient(config.target_host) as client:
        client.define_vm(xml)
        if config.start_after_migrate:
            log("  VM を起動中...")
            client.start_vm(vm_name)


# ---------------------------------------------------------------------------
# 移行オーケストレーター
# ---------------------------------------------------------------------------

class VMmigrator:
    """複数 VM のコールド移行を順番に実行する。"""

    def __init__(self, config: MigrationConfig) -> None:
        self._config = config
        self._log: ProgressCallback = lambda msg: None

    def set_progress_callback(self, callback: ProgressCallback) -> None:
        self._log = callback

    def migrate_all(self, vms: List[VMInfo]) -> None:
        for vm in vms:
            self._migrate_one(vm)

    def _migrate_one(self, vm: VMInfo) -> None:
        self._log(f"\n▶ [{vm.name}] 移行開始")

        _step_shutdown(vm, self._config, self._log)
        xml_str = _step_export_xml(vm, self._config, self._log)
        path_map = _step_transfer_disks(vm, self._config, self._log)
        updated_xml = update_xml_disk_paths(xml_str, path_map)
        updated_xml = normalize_machine_type(updated_xml)
        _step_define_vm(vm.name, updated_xml, self._config, self._log)

        self._log(f"✓ [{vm.name}] 移行完了")
