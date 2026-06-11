#!/usr/bin/env bash
set -euo pipefail

# WSL-friendly autostart launcher for NasMusicUI.
#
# Safe defaults:
# - derives the repo from this script location, override with NASMUSICUI_REPO
# - uses a lock + pid file to avoid duplicate starts
# - treats a healthy /health endpoint as "already running"
# - writes logs under ~/.nastech/webui/logs unless NASMUSICUI_LOG_DIR is set

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NASMUSICUI_REPO="${NASMUSICUI_REPO:-${DEFAULT_REPO}}"
NASMUSICUI_LOG_DIR="${NASMUSICUI_LOG_DIR:-${HOME}/.nastech/webui/logs}"
NASMUSICUI_HOST="${NASMUSICUI_HOST:-127.0.0.1}"
NASMUSICUI_PORT="${NASMUSICUI_PORT:-8787}"
NASMUSICUI_HEALTH_HOST="${NASMUSICUI_HEALTH_HOST:-127.0.0.1}"
NASMUSICUI_HEALTH_URL="${NASMUSICUI_HEALTH_URL:-http://${NASMUSICUI_HEALTH_HOST}:${NASMUSICUI_PORT}/health}"
NASMUSICUI_PID_FILE="${NASMUSICUI_PID_FILE:-${NASMUSICUI_LOG_DIR}/nasmusicui.pid}"
NASMUSICUI_LOCK_FILE="${NASMUSICUI_LOCK_FILE:-/tmp/nasmusicui-autostart.lock}"
AUTOSTART_LOG="${NASMUSICUI_LOG_DIR}/webui_autostart.log"
WEBUI_LOG="${NASMUSICUI_LOG_DIR}/nasmusicui.log"

# Make the WSL launcher knobs visible to start.sh/bootstrap.py.
export NASMUSICUI_HOST NASMUSICUI_PORT

mkdir -p "${NASMUSICUI_LOG_DIR}"
chmod 700 "${NASMUSICUI_LOG_DIR}" 2>/dev/null || true

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*" | tee -a "${AUTOSTART_LOG}"
}

webui_healthy() {
  command -v curl >/dev/null 2>&1 \
    && curl -fsS --max-time 3 "${NASMUSICUI_HEALTH_URL}" >/dev/null 2>&1
}

pid_is_alive() {
  [[ -s "${NASMUSICUI_PID_FILE}" ]] || return 1
  local pid
  pid="$(cat "${NASMUSICUI_PID_FILE}" 2>/dev/null || true)"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" >/dev/null 2>&1
}

validate_repo() {
  if [[ ! -d "${NASMUSICUI_REPO}" ]]; then
    log "NasMusicUI repo not found: ${NASMUSICUI_REPO}"
    exit 1
  fi
  if [[ ! -f "${NASMUSICUI_REPO}/start.sh" ]]; then
    log "start.sh not found under NASMUSICUI_REPO=${NASMUSICUI_REPO}"
    exit 1
  fi
}

maybe_require_agent_process() {
  # NasMusicUI usually launches the agent in-process, so this check is opt-in.
  # Set NASMUSICUI_REQUIRE_AGENT_PROCESS=1 only if your setup depends on a
  # separately running NasTech gateway/agent before WebUI starts.
  if [[ "${NASMUSICUI_REQUIRE_AGENT_PROCESS:-0}" != "1" ]]; then
    return 0
  fi
  if ! pgrep -f "nastech" >/dev/null 2>&1; then
    log "NASMUSICUI_REQUIRE_AGENT_PROCESS=1 but no NasTech process is running; skipping start"
    exit 1
  fi
}

acquire_lock() {
  exec 9>"${NASMUSICUI_LOCK_FILE}"
  if command -v flock >/dev/null 2>&1; then
    if ! flock -n 9; then
      log "Autostart already running; lock held at ${NASMUSICUI_LOCK_FILE}"
      exit 0
    fi
  else
    log "flock not found; continuing without lock-based duplicate protection"
  fi
}

start_webui() {
  validate_repo
  maybe_require_agent_process

  if webui_healthy; then
    log "NasMusicUI already running at ${NASMUSICUI_HEALTH_URL}"
    exit 0
  fi

  if pid_is_alive; then
    log "NasMusicUI already running with pid $(cat "${NASMUSICUI_PID_FILE}")"
    exit 0
  fi

  rm -f "${NASMUSICUI_PID_FILE}"
  log "Starting NasMusicUI from ${NASMUSICUI_REPO} on ${NASMUSICUI_HOST}:${NASMUSICUI_PORT}"

  (
    cd "${NASMUSICUI_REPO}"
    nohup bash "${NASMUSICUI_REPO}/start.sh" --foreground >>"${WEBUI_LOG}" 2>&1 &
    printf '%s\n' "$!" >"${NASMUSICUI_PID_FILE}"
  )

  sleep "${NASMUSICUI_STARTUP_GRACE_SECONDS:-2}"
  if webui_healthy; then
    log "NasMusicUI started and passed health check"
    exit 0
  fi

  if pid_is_alive; then
    log "NasMusicUI process started with pid $(cat "${NASMUSICUI_PID_FILE}"); health check not ready yet"
    exit 0
  fi

  log "NasMusicUI failed to stay running; see ${WEBUI_LOG}"
  exit 1
}

acquire_lock
start_webui
