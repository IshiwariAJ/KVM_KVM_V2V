# KVM VM 移行ツール

KVM/QEMU 仮想マシンをホスト間で移行・バックアップ・インポートする GUI ツールです。

![PyQt6](https://img.shields.io/badge/UI-PyQt6-green)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 機能

- **移行 (Migration)**: KVM ホスト間で VM をコールド移行（ディスク転送 + XML 定義の再登録）
- **バックアップ**: VM のディスクイメージと XML 定義をローカルディレクトリや Samba 共有に保存
- **インポート**: バックアップから VM を復元

### 対応転送シナリオ

| ソース | ターゲット | 方式 |
|--------|------------|------|
| ローカル KVM | リモート KVM (SSH) | rsync |
| リモート KVM (SSH) | ローカル KVM | rsync |
| リモート KVM (SSH) | リモート KVM (SSH) | ローカル /tmp 経由 rsync |
| ローカル KVM | Samba/GVFS 共有 | sudo dd (ストリーム、/tmp 不使用) |
| Samba/GVFS 共有 | ローカル KVM | sudo tee (ストリーム、/tmp 不使用) |

## 動作環境

- Ubuntu 24.04 LTS / 26.04 LTS（動作確認済み）
- libvirt + QEMU/KVM がインストール済みであること
- Python 3.10 以上

## インストール

```bash
git clone https://github.com/<your-username>/kvm-v2v.git
cd kvm-v2v
chmod +x setup.sh
./setup.sh
```

`setup.sh` が以下を自動で行います:

1. システムパッケージのインストール (`libvirt-dev`, `pkg-config`, `rsync`, `libvirt-clients`)
2. `rsync` / `tee` / `dd` の passwordless sudo 設定 (`/etc/sudoers.d/kvm-migrate-rsync`)
3. Python 仮想環境 (`.venv`) の作成
4. Python パッケージのインストール (`PyQt6`, `libvirt-python`)
5. デスクトップエントリの作成 (`~/.local/share/applications/kvm-v2v.desktop`)

> **注意**: `/var/lib/libvirt/images/` は root 所有のため、ディスク転送に `sudo rsync` / `sudo tee` / `sudo dd` を使用します。
> setup.sh がこの権限を自動設定します。

## 起動

セットアップ後は以下のいずれかの方法で起動できます:

- **デスクトップのアイコンをダブルクリック**
- GNOME のアプリ一覧から「KVM VM 移行ツール」を検索して起動
- コマンドライン: `source .venv/bin/activate && python main.py`

## アンインストール

```bash
# 仮想環境のみ削除
./uninstall.sh

# 仮想環境 + システムパッケージも削除
./uninstall.sh --full
```

## Samba 共有への接続について

GNOME ファイルマネージャーから Samba 共有をマウント (GVFS) するか、
`/etc/fstab` に cifs エントリを追加してください。

`/etc/fstab` を使う場合、書き込み可能にするには以下のオプションを推奨します:

```
//192.168.x.x/share /mnt/share cifs uid=1000,gid=1000,file_mode=0664,dir_mode=0775 0 0
```

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照してください。
