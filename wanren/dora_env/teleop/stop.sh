#!/usr/bin/env bash
# Stop the running teleop dataflow and tear down the cluster.
set -euo pipefail

cd "$(dirname "$0")"

echo ">> Stopping dataflow 'teleop' (if running)..."
dora stop teleop 2>/dev/null || true

echo ">> Tearing down cluster (coordinator + daemons)..."
dora cluster down 2>/dev/null || dora destroy 2>/dev/null || true
