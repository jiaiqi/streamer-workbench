#!/usr/bin/env bash
# 打包 Python 后端为 PyInstaller 单文件可执行。
#
# 用法:
#   tools/build_backend.sh                  # 默认 macOS 当前架构
#   tools/build_backend.sh --onedir         # 输出目录而非单文件 (调试方便)
#   tools/build_backend.sh --clean          # 清理 build/ dist/ *.spec 后重打
#
# 产物:
#   dist/streamer-workbench-backend  (单文件 binary, 60-80MB, 启动 ~25s 解压)
#   或 dist/streamer-workbench-backend/ (onedir 目录模式, 启动快 ~3s, 适合调试)
#
# 跑产物 (参考):
#   ./dist/streamer-workbench-backend --port 9890
#   STREAMER_WORKBENCH_DATA_DIR=/path/to/data ./dist/streamer-workbench-backend --port 9890
#
# 启动时间: macOS arm64 上 21MB onedir ~3s, 63MB onefile ~25s (onefile 解压到临时目录)
#
# 跨平台:
#   - macOS: 当前架构 (arm64/x86_64)
#   - Windows: 需 Windows 主机或 CI matrix 跑 PyInstaller
#   - Linux: 同上
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# 参数解析
CLEAN=0
ONEFILE="--onefile"
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    --onedir) ONEFILE="--onedir" ;;
    --onefile) ONEFILE="--onefile" ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

if [ "$CLEAN" = "1" ]; then
  echo "==> 清理 build/ dist/ *.spec"
  rm -rf build dist *.spec
fi

# venv 解析: 优先 STREAMER_VENV_PYTHON; 否则假设 venv 在 worktree 父父目录
#   (worktree 在 <repo>/.worktrees/<name>/ 时, venv 在 <repo>/.venv/)
#   普通 checkout 时, venv 与 repo 平级 (<repo>/../.venv)
VENV_PY="${STREAMER_VENV_PYTHON:-}"
if [ -z "$VENV_PY" ]; then
  for candidate in \
    "$REPO_ROOT/../../.venv/bin/python" \
    "$REPO_ROOT/../.venv/bin/python" \
    "$REPO_ROOT/.venv/bin/python"
  do
    if [ -x "$candidate" ]; then
      VENV_PY="$candidate"
      break
    fi
  done
fi
if [ -z "$VENV_PY" ] || [ ! -x "$VENV_PY" ]; then
  VENV_PY="$(command -v python3)"
  if [ -z "$VENV_PY" ]; then
    echo "错误: 找不到 venv python (尝试 \$REPO_ROOT/../../.venv/bin/python, ../.venv/bin/python, .venv/bin/python 和 PATH)" >&2
    exit 1
  fi
  echo "==> 使用系统 python: $VENV_PY"
fi

if ! "$VENV_PY" -c "import pyinstaller" 2>/dev/null; then
  echo "==> pyinstaller 未安装, 装上"
  "$VENV_PY" -m pip install pyinstaller
fi

echo "==> PyInstaller $ONEFILE 打包 server/__main__.py"
# 关键: 必须用 venv 的 python -m PyInstaller (PATH 上的 pyinstaller 可能是
#   系统 Python 的, 与 venv site-packages 不一致, 会漏 PIL 等隐式依赖)
# 关键 hidden imports (PyInstaller hook 对 fastapi/uvicorn/Pillow 已内置,
#   --collect-all 会破坏 Pillow hook 导致 PIL 解析失败, 因此不用)
PYTHONPATH="$REPO_ROOT" "$VENV_PY" -m PyInstaller \
  $ONEFILE \
  --name streamer-workbench-backend \
  --paths "$REPO_ROOT" \
  --add-data "themes:themes" \
  --add-data "fonts:fonts" \
  --add-data "palettes:palettes" \
  --add-data "skins:skins" \
  --collect-submodules server \
  --collect-submodules core \
  --noconfirm \
  server/__main__.py

if [ -f "dist/streamer-workbench-backend" ]; then
  SIZE=$(du -h dist/streamer-workbench-backend | cut -f1)
  echo "==> 完成: dist/streamer-workbench-backend ($SIZE)"
elif [ -d "dist/streamer-workbench-backend" ]; then
  echo "==> 完成: dist/streamer-workbench-backend/ (onedir 模式)"
fi
