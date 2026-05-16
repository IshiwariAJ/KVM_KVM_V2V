#!/bin/bash
# KVM VM 移行ツール アンインストールスクリプト
#
# 使い方:
#   ./uninstall.sh          — 仮想環境のみ削除 (システムパッケージは残す)
#   ./uninstall.sh --full   — 仮想環境 + システムパッケージも削除

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# ------------------------------------------------------------------
# オプション解析
# ------------------------------------------------------------------

FULL_UNINSTALL=false
for arg in "$@"; do
    case "$arg" in
        --full) FULL_UNINSTALL=true ;;
        --help|-h)
            echo "使い方: $0 [--full]"
            echo ""
            echo "  オプションなし  仮想環境 (.venv) のみ削除"
            echo "  --full         仮想環境 + インストールしたシステムパッケージも削除"
            exit 0
            ;;
        *)
            echo "不明なオプション: $arg"
            echo "使い方: $0 [--full]"
            exit 1
            ;;
    esac
done

echo "=== KVM VM 移行ツール アンインストール ==="
echo ""

# ------------------------------------------------------------------
# 確認プロンプト
# ------------------------------------------------------------------

if $FULL_UNINSTALL; then
    echo "【フルアンインストール】"
    echo "  - 仮想環境 (.venv) を削除します"
    echo "  - sudo 権限設定 (/etc/sudoers.d/kvm-migrate-rsync) を削除します"
    echo "  - 以下のシステムパッケージを削除します:"
    echo "      libvirt-dev, pkg-config, libvirt-clients"
    echo "  ※ python3-pip / python3-venv / rsync は他ツールでも使われるため削除しません"
else
    echo "【仮想環境のみ削除】"
    echo "  - 仮想環境 (.venv) を削除します"
    echo "  - システムパッケージは変更しません"
fi

echo ""
read -rp "続行しますか？ [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "キャンセルしました。"
    exit 0
fi

# ------------------------------------------------------------------
# 仮想環境の削除
# ------------------------------------------------------------------

if [ -d "$VENV_DIR" ]; then
    # 仮想環境がアクティブな場合は警告
    if [ -n "$VIRTUAL_ENV" ] && [ "$VIRTUAL_ENV" = "$VENV_DIR" ]; then
        echo ""
        echo "警告: 仮想環境が現在アクティブです。"
        echo "      削除後にシェルを再起動するか 'deactivate' を実行してください。"
    fi
    echo ""
    echo "[1/2] 仮想環境を削除しています: $VENV_DIR"
    rm -rf "$VENV_DIR"
    echo "      完了"
else
    echo ""
    echo "[1/2] 仮想環境が見つかりません (スキップ): $VENV_DIR"
fi

# ------------------------------------------------------------------
# システムパッケージの削除 (--full のみ)
# ------------------------------------------------------------------

SUDOERS_FILE="/etc/sudoers.d/kvm-migrate-rsync"

if $FULL_UNINSTALL; then
    echo ""
    echo "[2/3] sudo 権限設定を削除しています..."
    if [ -f "$SUDOERS_FILE" ]; then
        sudo rm -f "$SUDOERS_FILE"
        echo "      完了: $SUDOERS_FILE"
    else
        echo "      設定ファイルが見つかりません (スキップ)"
    fi

    echo ""
    echo "[3/3] システムパッケージを削除しています..."
    PKGS_TO_REMOVE=()

    for pkg in libvirt-dev pkg-config libvirt-clients; do
        if dpkg -s "$pkg" &>/dev/null; then
            PKGS_TO_REMOVE+=("$pkg")
        fi
    done

    if [ ${#PKGS_TO_REMOVE[@]} -eq 0 ]; then
        echo "      削除対象のパッケージが見つかりません (スキップ)"
    else
        sudo apt-get remove -y "${PKGS_TO_REMOVE[@]}"
        sudo apt-get autoremove -y
        echo "      完了: ${PKGS_TO_REMOVE[*]}"
    fi
else
    echo "[2/2] システムパッケージ・sudo 設定はそのままにします"
fi

# ------------------------------------------------------------------
# 完了メッセージ
# ------------------------------------------------------------------

echo ""
echo "=== アンインストール完了 ==="
echo ""
if $FULL_UNINSTALL; then
    echo "ツールとシステムパッケージを削除しました。"
    echo "再インストールするには: ./setup.sh"
else
    echo "仮想環境を削除しました。"
    echo "再セットアップするには: ./setup.sh"
    echo "システムパッケージも削除する場合: ./uninstall.sh --full"
fi
