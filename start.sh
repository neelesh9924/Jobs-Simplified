#!/usr/bin/env bash
set -e

SESSION="job-apply"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR/venv/bin/python"
CRON_MARKER="job_apply_automate.*ingest_jobs"
CRON_LINE="0 */6 * * *  cd $DIR && $PYTHON manage.py ingest_jobs --source remoteok >> /tmp/ingest_jobs.log 2>&1"

# ── prereq check ────────────────────────────────────────────────────────────
if ! command -v tmux &>/dev/null; then
    echo "tmux not found. Install it first:"
    echo "  brew install tmux"
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "Virtualenv not found at $DIR/venv. Create it first:"
    echo "  python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

# ── cron: add if not already present ────────────────────────────────────────
if crontab -l 2>/dev/null | grep -qE "$CRON_MARKER"; then
    echo "[cron] ingest_jobs already scheduled — skipping"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "[cron] ingest_jobs scheduled (every 6 h)"
fi

# ── tmux: attach if session exists, otherwise create ────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[tmux] attaching to existing session '$SESSION'"
    tmux attach-session -t "$SESSION"
    exit 0
fi

echo "[tmux] starting new session '$SESSION'"

# Window 1 — Django dev server
tmux new-session  -d -s "$SESSION" -n "server" \
    "cd '$DIR' && $PYTHON manage.py runserver; echo '--- server exited ---'; bash"

# Window 2 — ingest log (tail -f; starts empty until first cron run or manual trigger)
touch /tmp/ingest_jobs.log
tmux new-window -t "$SESSION" -n "ingest-log" \
    "tail -f /tmp/ingest_jobs.log"

# Focus the server window
tmux select-window -t "$SESSION:server"
tmux attach-session -t "$SESSION"
