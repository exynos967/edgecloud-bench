#!/bin/bash
# 一键评测: ./eval.sh <solution.cpp> [runner.py 其他参数]
set -e
cd "$(dirname "$0")"
exec python3 runner.py "$@"
