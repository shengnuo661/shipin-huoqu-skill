#!/usr/bin/env bash
# ============================================================
#  video-downloader 启动脚本（macOS / Linux）
#  用法：./vd.sh <视频链接> [输出目录] [额外参数...]
#  示例：./vd.sh https://v.douyin.com/xxx ./downloads
# ============================================================
set -euo pipefail

# 隔离 Python 环境目录（WorkBuddy 约定路径）
VENV="$HOME/.workbuddy/binaries/python/envs/default/bin"
# 若 WorkBuddy 未预置该 venv，则回退到本脚本同级的 .venv
if [ ! -x "$VENV/python" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  VENV="$SCRIPT_DIR/.venv/bin"
fi

export PATH="$VENV:$PATH"
SKILL_DIR="$HOME/.workbuddy/skills/video-downloader/scripts"
if [ ! -d "$SKILL_DIR" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SKILL_DIR="$SCRIPT_DIR/scripts"
fi

exec "$VENV/python" "$SKILL_DIR/download_video.py" "$@"
