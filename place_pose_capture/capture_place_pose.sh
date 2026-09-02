#!/bin/bash

set -u

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$TOOL_DIR/capture_place_pose.py"
