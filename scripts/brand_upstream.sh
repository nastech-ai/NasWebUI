#!/usr/bin/env bash
# brand_upstream.sh — reusable NasWebUI branding transform.
#
# Run this on any file or directory tree fetched from the upstream
# nesquena/hermes-webui repo to replace every Hermes reference with
# NasWebUI before the code touches this repo's codebase.
#
# Usage:
#   bash scripts/brand_upstream.sh [TARGET_DIR]
#   TARGET_DIR defaults to the repo root (.).
#
# Safe to run multiple times (idempotent).
#
# Replacement table
# ─────────────────────────────────────────────────────────────────────
#   Hermes WebUI            → NasWebUI
#   hermes-webui            → naswebui
#   HermesWebUI             → NasWebUI
#   HERMES_WEBUI            → NASWEBUI
#   hermes_webui            → naswebui
#   HERMES_HOME             → NASTECH_HOME
#   HERMES_BASE_HOME        → NASTECH_BASE_HOME
#   hermes_home             → nastech_home
#   hermes_cli              → nastech_cli
#   HERMES_WEBUI_TEST_PYTHON→ NASWEBUI_TEST_PYTHON
#   get_active_hermes_home  → get_active_nastech_home
#   hermes-run-adapter…     → naswebui-run-adapter…
#   why-hermes              → why-naswebui
#   hermes_webui_autostart  → naswebui_autostart
#   Hermes Agent            → NasTech Agent
#   hermes agent            → nastech agent
#   NasMusicUI / NASMUSICUI → NasWebUI / NASWEBUI  (catch any leftover)
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

TARGET="${1:-.}"

# Resolve to absolute path
TARGET="$(cd "$TARGET" && pwd)"

echo "[brand] Applying NasWebUI branding to: $TARGET"

# ── File content replacements (sed, in-place) ─────────────────────────────
find "$TARGET" -type f \( \
  -name "*.py"   -o -name "*.sh"   -o -name "*.md"  -o \
  -name "*.js"   -o -name "*.html" -o -name "*.css" -o \
  -name "*.txt"  -o -name "*.yaml" -o -name "*.yml" -o \
  -name "*.json" -o -name "*.toml" -o -name "*.ps1" -o \
  -name "*.mjs"  -o -name "*.bash" -o -name ".env*" \
\) \
  -not -path "*/.git/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/.venv/*" \
| xargs sed -i \
  -e 's/Hermes WebUI/NasWebUI/g' \
  -e 's/hermes-webui/naswebui/g' \
  -e 's/hermes_webui/naswebui/g' \
  -e 's/HermesWebUI/NasWebUI/g' \
  -e 's/HERMES_WEBUI/NASWEBUI/g' \
  -e 's/HERMES_HOME/NASTECH_HOME/g' \
  -e 's/HERMES_BASE_HOME/NASTECH_BASE_HOME/g' \
  -e 's/hermes_home/nastech_home/g' \
  -e 's/hermes_cli/nastech_cli/g' \
  -e 's/hermes\.cli/nastech\.cli/g' \
  -e 's/HERMES_WEBUI_TEST_PYTHON/NASWEBUI_TEST_PYTHON/g' \
  -e 's/get_active_hermes_home/get_active_nastech_home/g' \
  -e 's/hermes-run-adapter/naswebui-run-adapter/g' \
  -e 's/why-hermes/why-naswebui/g' \
  -e 's/hermes_webui_autostart/naswebui_autostart/g' \
  -e 's/Hermes Agent/NasTech Agent/g' \
  -e 's/hermes agent/nastech agent/g' \
  -e 's/Hermes agent/NasTech agent/g' \
  -e 's/NasMusicUI/NasWebUI/g' \
  -e 's/NASMUSICUI/NASWEBUI/g' \
  -e 's/nasmusicui/naswebui/g' \
  2>/dev/null || true

# ── File renames (paths containing hermes/nasmusicui) ────────────────────
# Walk bottom-up so parent renames don't break child paths.
while IFS= read -r old_path; do
  new_path="$(echo "$old_path" | sed \
    -e 's/hermes-run-adapter/naswebui-run-adapter/g' \
    -e 's/why-hermes/why-naswebui/g' \
    -e 's/hermes_webui_autostart/naswebui_autostart/g' \
    -e 's/hermes_home/nastech_home/g' \
    -e 's/hermes_webui/naswebui/g' \
    -e 's/nasmusicui/naswebui/g')"
  if [[ "$old_path" != "$new_path" ]]; then
    mkdir -p "$(dirname "$new_path")"
    mv "$old_path" "$new_path"
    echo "[brand] renamed: $old_path → $new_path"
  fi
done < <(find "$TARGET" -depth \
  -not -path "*/.git/*" \
  \( \
    -name "*hermes_webui_autostart*" -o \
    -name "*why-hermes*" -o \
    -name "*hermes-run-adapter*" -o \
    -name "*hermes_home*" -o \
    -name "*hermes_webui*" -o \
    -name "*nasmusicui*" \
  \))

echo "[brand] Done. All Hermes references replaced with NasWebUI."
