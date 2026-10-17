#!/usr/bin/env bash
# Fetch the OWASP Benchmark (Java, v1.2) into data/external/.
# The benchmark is GPL-2.0, so it is downloaded rather than vendored in this repo.
set -euo pipefail
DEST="data/external/BenchmarkJava"
if [ -d "$DEST/.git" ]; then
  echo "already present: $DEST"
  exit 0
fi
mkdir -p data/external
git clone --depth 1 https://github.com/OWASP-Benchmark/BenchmarkJava.git "$DEST"
echo "ground truth: $DEST/expectedresults-1.2.csv"
echo "SAST reports: $DEST/results/"
