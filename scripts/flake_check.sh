#!/usr/bin/env bash
# Flake policy (test plan section 8): a test that fails under any random order is a flake.
# Runs the fast tiers under N different random seeds and stops at the first failure.
#
#   bash scripts/flake_check.sh 10      # ten seeds
set -euo pipefail

runs="${1:-5}"
cd "$(dirname "$0")/.."

for seed in $(seq 1 "$runs"); do
  echo "==> random seed ${seed}"
  pytest tests/unit tests/graph tests/security tests/hygiene tests/selfcheck \
    -p randomly --randomly-seed="${seed}" -q -o addopts="" --timeout=60
done
echo "flake check passed: ${runs} seeds"
