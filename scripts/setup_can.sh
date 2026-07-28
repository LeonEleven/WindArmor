#!/usr/bin/env bash
set -euo pipefail

can_channel="${1:-can10}"

if [[ ! "${can_channel}" =~ ^can[0-9]+$ ]]; then
    echo "错误：CAN 通道必须是 can 加数字，例如 can10" >&2
    exit 2
fi

ip link set "${can_channel}" down 2>/dev/null || true
ip link set "${can_channel}" up type can bitrate 1000000
ip link set "${can_channel}" txqueuelen 1000
ip -details link show "${can_channel}"
