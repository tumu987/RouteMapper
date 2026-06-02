#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== 路线图生成引擎 v0.1.0 测试 ==="
for f in routes/*_config.json; do
    [ "$f" = "routes/_template.json" ] && continue
    echo "--- $(basename $f) ---"
    python3 generate.py "$f" || { echo "FAIL: $f"; exit 1; }
done
echo "=== 全部通过 ==="
