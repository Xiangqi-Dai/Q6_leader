#!/bin/bash
# build.sh - 编译 can_infra C++ 二进制文件
# 仅在部署时使用，Python API (damiao_api.py) 不负责编译

set -e
cd "$(dirname "$0")"

echo "[BUILD] Compiling can_infra..."
make clean 2>/dev/null || true
make

echo "[BUILD] Done. Binary: ./main"
