#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR/venv/bin/python"

echo "==> Setting up Job Apply Engine"

# ── virtualenv ───────────────────────────────────────────────────────────────
if [[ ! -x "$PYTHON" ]]; then
    echo "[setup] Creating virtualenv..."
    python3 -m venv "$DIR/venv"
else
    echo "[setup] Virtualenv already exists — skipping"
fi

# ── dependencies ─────────────────────────────────────────────────────────────
echo "[setup] Installing dependencies..."
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"

# ── migrations ───────────────────────────────────────────────────────────────
echo "[setup] Running migrations..."
"$PYTHON" "$DIR/manage.py" migrate

# ── superuser ────────────────────────────────────────────────────────────────
USER_COUNT=$("$PYTHON" "$DIR/manage.py" shell -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_superuser=True).count())")
if [[ "$USER_COUNT" -eq 0 ]]; then
    echo "[setup] No superuser found. Creating one now..."
    "$PYTHON" "$DIR/manage.py" createsuperuser
else
    echo "[setup] Superuser already exists — skipping"
fi

# ── launch ───────────────────────────────────────────────────────────────────
echo ""
echo "==> Setup complete. Launching..."
exec "$DIR/start.sh"
