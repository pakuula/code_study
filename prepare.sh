#!/usr/bin/env bash
# prepare.sh — подготовка окружения для C code analyzer
# Ubuntu/Debian. Явно использует ./.venv/bin/python и ./.venv/bin/pip.
# Системный Python не используется ни в каких командах установки/запуска.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

log() { echo "[prepare] $*"; }
log_ok()   { echo "[prepare] OK:      $*"; }
log_warn() { echo "[prepare] WARNING: $*"; }

# ---------------------------------------------------------------------------
# 1. Системные пакеты
# ---------------------------------------------------------------------------
log "=== [1/3] Системные пакеты (apt) ==="
sudo apt-get update -y
sudo apt-get install -y \
    universal-ctags \
    cscope \
    gcc \
    sqlite3 \
    libsqlite3-dev \
    pkg-config \
    ripgrep \
    git \
    make \
    python3-venv \
    python3-dev \
    python3-full

# Опционально: clang/llvm для будущей глубокой валидации (не обязательно для MVP)
# sudo apt-get install -y clang llvm

# ---------------------------------------------------------------------------
# 2. Виртуальное окружение
# ---------------------------------------------------------------------------
log "=== [2/3] Виртуальное окружение: $VENV_DIR ==="
if [ ! -f "$PYTHON" ]; then
    log "Создаём .venv..."
    python3 -m venv "$VENV_DIR"
    log_ok "Создано: $PYTHON"
else
    log_ok ".venv уже существует: $PYTHON"
fi

"$PYTHON" --version

# ---------------------------------------------------------------------------
# 3. Python-пакеты в .venv (только через ./.venv/bin/pip)
# ---------------------------------------------------------------------------
log "=== [3/3] Python-пакеты (.venv) ==="
"$PIP" install --upgrade pip setuptools wheel

"$PIP" install \
    "click>=8.1" \
    "pydantic>=2.0" \
    "structlog>=24.0" \
    "tree-sitter>=0.21" \
    tree-sitter-c \
    pycparser \
    regex \
    "tqdm>=4.66" \
    pytest

# ---------------------------------------------------------------------------
# Проверка инструментов
# ---------------------------------------------------------------------------
log ""
log "=== Проверка установленных инструментов ==="

check_tool() {
    local tool="$1"
    if command -v "$tool" &>/dev/null; then
        log_ok "$tool — $($tool --version 2>&1 | head -1)"
    else
        log_warn "$tool не найден. Установите его вручную."
    fi
}

check_tool ctags
check_tool cscope
check_tool gcc
check_tool sqlite3
check_tool rg

"$PYTHON" -c "import sys; print(f'[prepare] OK:      Python {sys.version}')"
"$PYTHON" -c "import tree_sitter; print(f'[prepare] OK:      tree-sitter {tree_sitter.__version__}')" \
    2>/dev/null || log_warn "tree-sitter не импортируется — проверьте установку"
"$PYTHON" -c "import click; print(f'[prepare] OK:      click {click.__version__}')"
"$PYTHON" -c "import structlog; print(f'[prepare] OK:      structlog OK')"
"$PYTHON" -c "import pydantic; print(f'[prepare] OK:      pydantic {pydantic.__version__}')"

log ""
log "=== prepare.sh завершён успешно ==="
log "Запуск анализатора: $PYTHON -m src.orchestrator <source_dir> [--db <path>]"
