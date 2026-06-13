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

echo "[1/5] システムパッケージをインストールしています..."
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

echo "[2/5] rsync・tee・dd の sudo 権限を設定しています..."
SUDOERS_FILE="/etc/sudoers.d/kvm-migrate-rsync"
RSYNC_BIN="$(which rsync)"
TEE_BIN="$(which tee)"
DD_BIN="$(which dd)"
SUDOERS_LINE="$USER ALL=(ALL) NOPASSWD: $RSYNC_BIN, $TEE_BIN, $DD_BIN"

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
    echo "[3/5] 既存の仮想環境を再利用します: $VENV_DIR"
else
    echo "[3/5] 仮想環境を作成しています: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "      完了"
echo ""

# ------------------------------------------------------------------
# Python パッケージ
# ------------------------------------------------------------------

echo "[4/5] Python パッケージをインストールしています..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt"
echo "      完了"
echo ""

# ------------------------------------------------------------------
# デスクトップエントリの作成
# ------------------------------------------------------------------

echo "[5/5] デスクトップエントリを作成しています..."
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/kvm-v2v.desktop"
mkdir -p "$DESKTOP_DIR"

# アイコンは virt-manager があればそれを、なければ汎用アイコンを使用
if [ -f "/usr/share/icons/hicolor/scalable/apps/virt-manager.svg" ]; then
    ICON="virt-manager"
else
    ICON="utilities-system-monitor"
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=KVM VM 移行ツール
Comment=KVM/QEMU 仮想マシンの移行・バックアップ・インポート
Exec=$VENV_DIR/bin/python $SCRIPT_DIR/main.py
Icon=$ICON
Terminal=false
Categories=System;Utility;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# アプリ一覧をすぐに更新
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

# デスクトップにもアイコンを配置
DESKTOP_ICON="$HOME/デスクトップ/kvm-v2v.desktop"
# ロケールによってフォルダ名が異なる場合に対応
if [ ! -d "$HOME/デスクトップ" ] && [ -d "$HOME/Desktop" ]; then
    DESKTOP_ICON="$HOME/Desktop/kvm-v2v.desktop"
fi

if [ -d "$(dirname "$DESKTOP_ICON")" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_ICON"
    chmod +x "$DESKTOP_ICON"
    # GNOME がアイコンを「信頼済み」として扱うよう設定
    if command -v gio &>/dev/null; then
        gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
    fi
    echo "      作成完了: $DESKTOP_FILE"
    echo "      デスクトップアイコン: $DESKTOP_ICON"
else
    echo "      作成完了: $DESKTOP_FILE"
    echo "      ※ デスクトップフォルダが見つからないため、アプリ一覧のみに登録しました"
fi
echo "      GNOME のアプリ一覧または、デスクトップアイコンから起動できます"
echo ""

# ------------------------------------------------------------------
# 完了メッセージ
# ------------------------------------------------------------------

echo "=== セットアップ完了 ==="
echo ""
echo "起動方法 (いずれか):"
echo "  ・デスクトップのアイコンをダブルクリック"
echo "  ・GNOME アプリ一覧から「KVM VM 移行ツール」を検索して起動"
echo "  ・コマンド: source .venv/bin/activate && python main.py"
echo ""
echo "アンインストール方法:"
echo "  ./uninstall.sh          # 仮想環境のみ削除"
echo "  ./uninstall.sh --full   # システムパッケージも削除"
