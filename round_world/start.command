#!/bin/bash
# macOS 双击启动入口: 转发给 start.sh
cd "$(dirname "$0")"
exec ./start.sh "$@"
