#!/bin/bash
# Stop the independent video service and every other Dofbot runtime process.

set -u

RUNTIME_COMMON="$HOME/runtime_common.sh"
if [ ! -f "$RUNTIME_COMMON" ]; then
    echo "[VIDEO][ERROR] Missing $RUNTIME_COMMON" >&2
    exit 1
fi
source "$RUNTIME_COMMON"

runtime_transition_begin "停止独立视频"
trap runtime_transition_end EXIT

echo "[VIDEO] Stopping video service and clearing all Dofbot runtime processes"
if runtime_stop_and_cleanup "独立视频停止前"; then
    echo "[VIDEO] Video service and all project nodes are stopped"
    exit 0
fi

echo "[VIDEO][ERROR] Runtime cleanup is incomplete" >&2
exit 1
