#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m hiver_agent prepare-data
python -m hiver_agent train --method tfidf
python -m hiver_agent run-pipeline --dry-run --limit 3
python -m hiver_agent evaluate --dry-run --judge-sample 10
pytest -q
echo "SMOKE OK"
