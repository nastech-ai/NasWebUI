#!/usr/bin/env bash
set -euo pipefail

# WSL-friendly autostart launcher for NasWebUI.
#
# Safe defaults:
# - derives the repo from this script location, override with NASWEBUI_REPO
# - uses a lock + pid file to avoid duplicate starts
# - treats a healthy /health endpoint as "already running"
# - writes logs under ~/.nastech/webui/logs unless NASWEBUI_LOG_DIR is set

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NASWEBUI_REPO="${NASWEBUI_REPO:-${DEFAULT_REPO}}"
NASWEBUI_LOG_DIR="${NASWEBUI_LOG_DIR:-${HOME}/.nastech/webui/logs}"
NASWEBUI_HOST="${NASWEBUI_HOST:-127.0.0.1}"
NASWEBUI_PORT="${NASWEBUI_PORT:-8787}"
NASWEBUI_HEALTH_HOST="${NASWEBUI_HEALTH_HOST:-127.0.0.1}"
NASWEBUI_HEALTH_URL="${NASWEBUI_HEALTH_URL:-http://${NASWEBUI_HEALTH_HOST}:${NASWEBUI_PORT}/health}"
NASWEBUI_PID_FILE="${NASWEBUI_PID_FILE:-${NASWEBUI_LOG_DIR}/naswebui.pid}"
NASWEBUI_LOCK_FILE="${NASWEBUI_LOCK_FILE:-/tmp/naswebui-autostart.lock}"
AUTOSTART_LOG="${NASWEBUI_LOG_DIR}/webui_autostart.log"
WEBUI_LOG="${NASWEBUI_LOG_DIR}/naswebui.log"

# Make the WSL launcher knobs visible to start.sh/bootstrap.py.
export NASWEBUI_HOST NASWEBUI_PORT

mkdir -p "${NASWEBUI_LOG_DIR}"
chmod 700 "${NASWEBUI_LOG_DIR}" 2>/dev/null || true

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*" | tee -a "${AUTOSTART_LOG}"
}

webui_healthy() {
  command -v curl >/dev/null 2>&1 \
    && curl -fsS --max-time 3 "${NASWEBUI_HEALTH_URL}" >/dev/null 2>&1
}

pid_is_alive() {
  [[ -s "${NASWEBUI_PID_FILE}" ]] || return 1
  local pid
  pid="$(cat "${NASWEBUI_PID_FILE}" 2>/dev/null || true)"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" >/dev/null 2>&1
}

validate_repo() {
  if [[ ! -d "${NASWEBUI_REPO}" ]]; then
    log "NasWebUI repo not found: ${NASWEBUI_REPO}"
    exit 1
  fi
  if [[ ! -f "${NASWEBUI_REPO}/start.sh" ]]; then
    log "start.sh not found under NASWEBUI_REPO=${NASWEBUI_REPO}"
    exit 1
  fi
}

maybe_require_agent_process() {
  # NasWebUI usually launches the agent in-process, so this check is opt-in.
  # Set NASWEBUI_REQUIRE_AGENT_PROCESS=1 only if your setup depends on a
  # separately running NasTech gateway/agent before WebUI starts.
  if [[ "${NASWEBUI_REQUIRE_AGENT_PROCESS:-0}" != "1" ]]; then
    return 0
  fi
  if ! pgrep -f "nastech" >/dev/null 2>&1; then
    log "NASWEBUI_REQUIRE_AGENT_PROCESS=1 but no NasTech process is running; skipping start"
    exit 1
  fi
}

acquire_lock() {
  exec 9>"${NASWEBUI_LOCK_FILE}"
  if command -v flock >/dev/null 2>&1; then
    if ! flock -n 9; then
      log "Autostart already running; lock held at ${NASWEBUI_LOCK_FILE}"
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
    log "NasWebUI already running at ${NASWEBUI_HEALTH_URL}"
    exit 0
  fi

  if pid_is_alive; then
    log "NasWebUI already running with pid $(cat "${NASWEBUI_PID_FILE}")"
    exit 0
  fi

  rm -f "${NASWEBUI_PID_FILE}"
  log "Starting NasWebUI from ${NASWEBUI_REPO} on ${NASWEBUI_HOST}:${NASWEBUI_PORT}"

  (
    cd "${NASWEBUI_REPO}"
    nohup bash "${NASWEBUI_REPO}/start.sh" --foreground >>"${WEBUI_LOG}" 2>&1 &
    printf '%s\n' "$!" >"${NASWEBUI_PID_FILE}"
  )

  sleep "${NASWEBUI_STARTUP_GRACE_SECONDS:-2}"
  if webui_healthy; then
    log "NasWebUI started and passed health check"
    exit 0
  fi

  if pid_is_alive; then
    log "NasWebUI process started with pid $(cat "${NASWEBUI_PID_FILE}"); health check not ready yet"
    exit 0
  fi

  log "NasWebUI failed to stay running; see ${WEBUI_LOG}"
  exit 1
}

acquire_lock
start_webui
