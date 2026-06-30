#!/bin/bash
# 供 Supervisor 调用：启动 hardware_sender（python main.py）。
# 使用 /bin/bash：避免 Supervisor 子进程 PATH 过短或缺少 env 时无法 spawn。
#
# 可选环境变量：
#   EMBODIED_SENDER_PYTHON    指定 Python 可执行文件（最高优先级）
#   EMBODIED_PYTHON           未设置 SENDER_PYTHON 时作为后备
#   EMBODIED_SENDER_VENV      虚拟环境根目录，默认尝试 $ROOT/hardware_sender/.venv
#   EMBODIED_USER_SITE_HOME   同 backend 脚本：root 下加载某用户 pip --user 包时设置家目录
set -euo pipefail

export PATH="${PATH:-/usr/local/bin:/usr/bin:/bin}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SENDER_DIR="$ROOT/hardware_sender"
cd "$SENDER_DIR"

if [[ -n "${EMBODIED_USER_SITE_HOME:-}" ]]; then
  export PYTHONUSERBASE="${EMBODIED_USER_SITE_HOME}/.local"
fi

resolve_python() {
  if [[ -n "${EMBODIED_SENDER_PYTHON:-}" ]]; then
    if [[ ! -x "${EMBODIED_SENDER_PYTHON}" ]]; then
      echo "[embodied-hardware-sender] EMBODIED_SENDER_PYTHON 不可执行: ${EMBODIED_SENDER_PYTHON}" >&2
      exit 1
    fi
    echo "${EMBODIED_SENDER_PYTHON}"
    return
  fi
  if [[ -n "${EMBODIED_PYTHON:-}" ]]; then
    if [[ ! -x "${EMBODIED_PYTHON}" ]]; then
      echo "[embodied-hardware-sender] EMBODIED_PYTHON 不可执行: ${EMBODIED_PYTHON}" >&2
      exit 1
    fi
    echo "${EMBODIED_PYTHON}"
    return
  fi
  local vroot="${EMBODIED_SENDER_VENV:-}"
  local candidates=()
  [[ -n "$vroot" ]] && candidates+=("$vroot/bin/python")
  candidates+=("$SENDER_DIR/.venv/bin/python" "$SENDER_DIR/venv/bin/python")
  for cand in "${candidates[@]}"; do
    if [[ -x "$cand" ]]; then
      echo "$cand"
      return
    fi
  done
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  for cand in /usr/bin/python3 /usr/bin/python; do
    if [[ -x "$cand" ]]; then
      echo "$cand"
      return
    fi
  done
}

PY="$(resolve_python || true)"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  echo "[embodied-hardware-sender] 未找到可用的 Python（请在 hardware_sender 创建 .venv 并 pip install -r requirements.txt，或设置 EMBODIED_SENDER_PYTHON）。" >&2
  exit 1
fi

if ! "$PY" -c "import yaml, paho.mqtt" 2>/dev/null; then
  echo "[embodied-hardware-sender] 当前 Python 缺少依赖（需 PyYAML、paho-mqtt 等）: $PY" >&2
  echo "  请执行: cd \"$SENDER_DIR\" && \"$PY\" -m pip install -r requirements.txt" >&2
  exit 1
fi

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

exec "$PY" main.py "$@"
