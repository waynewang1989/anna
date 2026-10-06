#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# 圆球秘境 · 寻宝 —— 一键启动脚本 (macOS / Linux)
#
# 用法:
#   ./start.sh                  正常启动 (首次自动创建虚拟环境并安装依赖)
#   ./start.sh --selftest       自检模式: 自动走位/攻击/穿梭/截图, 约12秒后退出
#   ./start.sh --weather rain   锁定天气启动: clear | rain | snow | wind
#   ./start.sh -f | --force     强制重新安装依赖
#   ./start.sh -h | --help      查看帮助
#   其余参数原样透传给 game.py
# ----------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
REQ="requirements.txt"
STAMP="$VENV/.requirements.stamp"
FORCE=0
ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--force)     FORCE=1 ;;
    --selftest)     export RW_SELFTEST=1 ;;
    --weather)      [[ $# -ge 2 ]] || { echo "错误: --weather 需要参数 (clear|rain|snow|wind)"; exit 1; }
                    export RW_WEATHER="$2"; shift ;;
    --weather=*)    export RW_WEATHER="${1#--weather=}" ;;
    -h|--help)      awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit 0 ;;
    *)              ARGS+=("$1") ;;
  esac
  shift
done

# 1) 找 python3
if ! command -v python3 >/dev/null 2>&1; then
  echo "错误: 未找到 python3, 请先安装 Python 3.9+"; exit 1
fi

# 2) 创建虚拟环境 (仅首次)
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "==> 创建虚拟环境 $VENV ..."
  python3 -m venv "$VENV"
fi

# 3) 安装依赖 (requirements.txt 变化时自动重装, -f 强制)
if [[ "$FORCE" == 1 || ! -f "$STAMP" || "$REQ" -nt "$STAMP" ]]; then
  echo "==> 安装依赖 (ursina / Pillow / numpy ...) ..."
  "$VENV/bin/python" -m pip install --upgrade pip || echo "提示: pip 自升级失败(可能离线), 继续..."
  "$VENV/bin/python" -m pip install -r "$REQ"
  touch "$STAMP"
else
  echo "==> 依赖已安装, 跳过 (可用 -f 强制重装)"
fi

# 4) 启动游戏
echo "==> 启动游戏 (第三人称 · 蓝天白云) ..."
exec "$VENV/bin/python" game.py ${ARGS[@]+"${ARGS[@]}"}
