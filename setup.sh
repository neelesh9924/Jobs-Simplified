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

# ── tectonic (LaTeX engine for resume PDFs) ──────────────────────────────────
# System dependency, not pip-installable. We fetch the official prebuilt binary
# from GitHub releases (brew's formula compiles llvm+rust from source — far slower).
if command -v tectonic &>/dev/null; then
    echo "[setup] tectonic already installed — skipping"
else
    echo "[setup] Installing tectonic (LaTeX engine)..."
    UNAME_S="$(uname -s)"; UNAME_M="$(uname -m)"
    case "$UNAME_S/$UNAME_M" in
        Darwin/arm64)  TRIPLE="aarch64-apple-darwin" ;;
        Darwin/x86_64) TRIPLE="x86_64-apple-darwin" ;;
        Linux/x86_64)  TRIPLE="x86_64-unknown-linux-gnu" ;;
        Linux/aarch64) TRIPLE="aarch64-unknown-linux-gnu" ;;
        *) echo "[setup] Unsupported platform $UNAME_S/$UNAME_M — install tectonic manually: https://tectonic-typesetting.github.io/install.html"; TRIPLE="" ;;
    esac
    if [[ -n "$TRIPLE" ]]; then
        URL=$(curl -fsSL https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest \
              | grep -o "https://[^\"]*tectonic-[^\"]*${TRIPLE}\.tar\.gz" | head -1)
        if [[ -n "$URL" ]]; then
            TMP="$(mktemp -d)"
            curl -fsSL -o "$TMP/tectonic.tar.gz" "$URL" && tar xzf "$TMP/tectonic.tar.gz" -C "$TMP"
            if [[ -w /usr/local/bin ]]; then DEST=/usr/local/bin; else DEST="$HOME/.local/bin"; mkdir -p "$DEST"; fi
            mv "$TMP/tectonic" "$DEST/tectonic" && chmod +x "$DEST/tectonic"
            rm -rf "$TMP"
            echo "[setup] tectonic installed to $DEST (ensure it's on PATH)"
        else
            echo "[setup] Could not resolve tectonic release URL — install manually."
        fi
    fi
fi

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
