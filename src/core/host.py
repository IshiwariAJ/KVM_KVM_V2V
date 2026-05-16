from dataclasses import dataclass
from enum import Enum


class ConnectionType(Enum):
    LOCAL = "local"
    SSH = "ssh"


@dataclass
class HostConfig:
    name: str = "localhost"
    connection_type: ConnectionType = ConnectionType.LOCAL
    host: str = ""
    port: int = 22
    username: str = ""
    ssh_key_path: str = ""

    def libvirt_uri(self) -> str:
        if self.connection_type == ConnectionType.LOCAL:
            return "qemu:///system"
        user = f"{self.username}@" if self.username else ""
        port_str = f":{self.port}" if self.port != 22 else ""
        uri = f"qemu+ssh://{user}{self.host}{port_str}/system"
        if self.ssh_key_path:
            uri += f"?keyfile={self.ssh_key_path}"
        return uri

    def display_name(self) -> str:
        if self.connection_type == ConnectionType.LOCAL:
            return "ローカル"
        prefix = f"{self.username}@" if self.username else ""
        return f"{prefix}{self.host}"

    def rsync_prefix(self) -> str:
        """rsync のリモートパスプレフィックス (ローカルは空文字)"""
        if self.connection_type == ConnectionType.LOCAL:
            return ""
        prefix = f"{self.username}@" if self.username else ""
        return f"{prefix}{self.host}:"

    def ssh_opts(self) -> list[str]:
        """rsync -e ssh に渡すオプション文字列用"""
        opts = []
        if self.port != 22:
            opts += ["-p", str(self.port)]
        if self.ssh_key_path:
            opts += ["-i", self.ssh_key_path]
        return opts
