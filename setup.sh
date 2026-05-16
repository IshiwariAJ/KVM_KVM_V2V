#!/bin/bash
# KVM VM 移行ツール セットアップスクリプト
#
# 使い方:
#   ./setup.sh          — 通常セットアップ (既存の .venv は再利用)
#   ./setup.sh --clean  — .venv を削除してクリーンインストール

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# ------------------------------------------------------------------
# オプション解析
# ------------------------------------------------------------------

CLEAN_INSTALL=false
for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN_INSTALL=true ;;
        --help|-h)
            echo "使い方: $0 [--clean]"
            echo ""
            echo "  オプションなし  既存の .venv を再利用してセットアップ"
            echo "  --clean        .venv を削除してクリーンインストール"
            exit 0
            ;;
        *)
            echo "不明なオプション: $arg"
            echo "使い方: $0 [--clean]"
            exit 1
            ;;
    esac
done

echo "=== KVM VM 移行ツール セットアップ ==="
echo ""

# ------------------------------------------------------------------
# クリーンインストール: 既存 .venv を削除
# ------------------------------------------------------------------

if $CLEAN_INSTALL && [ -d "$VENV_DIR" ]; then
    echo "[前処理] 既存の仮想環境を削除しています..."
    rm -rf "$VENV_DIR"
    echo "         完了"
    echo ""
fi

# ------------------------------------------------------------------
# システム依存パッケージ
# ------------------------------------------------------------------

echo "[1/4] システムパッケージをインストールしています..."
sudo apt-get update -q
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    libvirt-dev \
    pkg-config \
    rsync \
    libvirt-clients
echo "      完了"
echo ""

# ------------------------------------------------------------------
# rsync の passwordless sudo 設定
# /var/lib/libvirt/images/ は root 所有 600 のため、
# バックアップ・移行時に sudo rsync が必要。
# ------------------------------------------------------------------

echo "[2/4] rsync・tee の sudo 権限を設定しています..."
SUDOERS_FILE="/etc/sudoers.d/kvm-migrate-rsync"
RSYNC_BIN="$(which rsync)"
TEE_BIN="$(which tee)"
SUDOERS_LINE="$USER ALL=(ALL) NOPASSWD: $RSYNC_BIN, $TEE_BIN"

# 既存の設定が正しい内容かどうか確認し、古い形式なら上書きする
if sudo grep -qF "$SUDOERS_LINE" "$SUDOERS_FILE" 2>/dev/null; then
    echo "      既に設定済みです (スキップ)"
else
    echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 440 "$SUDOERS_FILE"
    echo "      設定完了: $SUDOERS_FILE"
fi
echo ""

# ------------------------------------------------------------------
# Python 仮想環境
# ------------------------------------------------------------------

if [ -d "$VENV_DIR" ]; then
    echo "[3/4] 既存の仮想環境を再利用します: $VENV_DIR"
else
    echo "[3/4] 仮想環境を作成しています: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "      完了"
echo ""

# ------------------------------------------------------------------
# Python パッケージ
# ------------------------------------------------------------------

echo "[4/4] Python パッケージをインストールしています..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt"
echo "      完了"
echo ""

# ------------------------------------------------------------------
# 完了メッセージ
# ------------------------------------------------------------------

echo "=== セットアップ完了 ==="
echo ""
echo "起動方法:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "アンインストール方法:"
echo "  ./uninstall.sh          # 仮想環境のみ削除"
echo "  ./uninstall.sh --full   # システムパッケージも削除"
