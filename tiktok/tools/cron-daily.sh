#!/usr/bin/env bash
# Daily TikTok post — designed to be triggered by cron.
#
# Suggested crontab entry (21:00 JST = 12:00 UTC):
#   0 12 * * * /home/user/ai-broadcast-hub/tiktok/tools/cron-daily.sh
#
# The script:
#   1. Loads the venv inside tiktok/.venv
#   2. Runs posting.run (which picks the next un-posted video, uploads
#      in the configured mode, updates state.json, and notifies Discord)
#   3. Optionally commits state.json back to git so progress is durable
#
# Exit code is propagated for cron / monit / healthchecks.io style
# alerting.

set -euo pipefail

# Resolve script location -> tiktok project dir
TIKTOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TIKTOK_DIR"

LOG_DIR="${TIKTOK_DIR}/posting/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(date +%Y-%m-%d).log"

# Activate venv (created by tools/setup.sh)
if [[ ! -d .venv ]]; then
  echo "ERROR: .venv not found. Run tools/setup.sh first." >&2
  exit 2
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Run the posting pipeline. Tee to a daily log file too.
set +e
python -m posting.run 2>&1 | tee -a "$LOG_FILE"
rc=${PIPESTATUS[0]}
set -e

# Persist state.json across reboots / crons. Only commit if state changed.
if [[ "${TIKTOK_AUTO_COMMIT_STATE:-1}" == "1" ]]; then
  if git -C "$TIKTOK_DIR/.." diff --quiet tiktok/posting/state.json 2>/dev/null; then
    :  # no change
  else
    (
      cd "$TIKTOK_DIR/.."
      git add tiktok/posting/state.json
      git commit -m "posting: update state.json $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        -m "Automated commit from cron-daily.sh" 2>&1 | tee -a "$LOG_FILE" || true
      # Push only if the operator opted in.
      if [[ "${TIKTOK_AUTO_PUSH_STATE:-0}" == "1" ]]; then
        git push 2>&1 | tee -a "$LOG_FILE" || true
      fi
    )
  fi
fi

exit "$rc"
