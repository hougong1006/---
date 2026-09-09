#!/bin/bash
# Stop the conveyor and all Dofbot sorting, video and joint-test processes.

set -u

RUNTIME_COMMON="$HOME/runtime_common.sh"
if [ ! -f "$RUNTIME_COMMON" ]; then
    echo "[运行保护][错误] 未找到 $RUNTIME_COMMON" >&2
    exit 1
fi
source "$RUNTIME_COMMON"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Dofbot Pro 3D视觉垃圾分拣 - 停止所有   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

runtime_transition_begin "停止完整分拣系统"
trap runtime_transition_end EXIT

if runtime_stop_and_cleanup "一键停止"; then
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║          所有节点已停止！                 ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    exit 0
fi

echo "[停止][错误] 仍有项目进程未能完全退出" >&2
exit 1
