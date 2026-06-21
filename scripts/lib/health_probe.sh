#!/usr/bin/env bash
# Shared, TLS-aware /health probe used by every shell launcher (start.sh,
# ctl.sh, the WSL autostart helper) and the Docker HEALTHCHECK.
#
# The WebUI serves HTTPS when both NASWEBUI_TLS_CERT and
# NASWEBUI_TLS_KEY are set (see api/config.py:TLS_ENABLED). The probe must
# mirror that scheme, otherwise an http:// probe against an https listener (or
# vice-versa) reports a healthy server as down.
#
# Probe order when TLS is configured:
#   1. Verified HTTPS.
#   2. Self-signed fallback: if verification fails, retry without verification
#      and print a one-line "self-signed certificate" warning (once).
#   3. Plain HTTP: server.py intentionally falls back to serving HTTP when the
#      cert/key are present but unloadable. Probe HTTP last so that
#      contract is honored instead of polling HTTPS forever.
#
# NASWEBUI_TLS_INSECURE_PROBE=1 is an explicit opt-in that skips verified
# HTTPS and goes straight to the unverified attempt. By contract this is
# silent (the user already accepted the risk), so no warning is printed.
#
# This file is safe to `source` (defines functions only) and is also runnable
# directly as a standalone probe:
#   bash scripts/lib/health_probe.sh <host> <port> [path] [max_time]
# On success it prints the response body to stdout and exits 0.
#
# Kept bash 3.2 compatible under `set -u` (ctl.sh sources this).

_NASWEBUI_SELF_SIGNED_WARNED="${_NASWEBUI_SELF_SIGNED_WARNED:-0}"
_NASWEBUI_PROBE_SCHEME="${_NASWEBUI_PROBE_SCHEME:-}"

_naswebui_truthy() {
  case "${1:-}" in
    1 | true | TRUE | True | yes | YES | on | ON) return 0 ;;
    *) return 1 ;;
  esac
}

naswebui_probe_scheme() {
  if [[ -n "${NASWEBUI_TLS_CERT:-}" && -n "${NASWEBUI_TLS_KEY:-}" ]]; then
    printf 'https'
  else
    printf 'http'
  fi
}

_naswebui_warn_self_signed() {
  [[ "${_NASWEBUI_SELF_SIGNED_WARNED}" == "1" ]] && return 0
  _NASWEBUI_SELF_SIGNED_WARNED=1
  printf '[warn] Health probe: TLS certificate at %s is self-signed or not trusted; proceeding without verification.\n' \
    "$1" >&2
}

_naswebui_http_get() {
  local url="$1" max_time="$2" mode="$3"
  if command -v curl >/dev/null 2>&1; then
    if [[ "${mode}" == "insecure" ]]; then
      curl -fsS -k --max-time "${max_time}" "${url}" 2>/dev/null
    else
      curl -fsS --max-time "${max_time}" "${url}" 2>/dev/null
    fi
    return $?
  elif command -v wget >/dev/null 2>&1; then
    if [[ "${mode}" == "insecure" ]]; then
      wget -qO- --no-check-certificate "--timeout=${max_time}" --tries=1 "${url}" 2>/dev/null
    else
      wget -qO- "--timeout=${max_time}" --tries=1 "${url}" 2>/dev/null
    fi
    return $?
  fi
  return 127
}

naswebui_probe_health() {
  local host="$1" port="$2" path="${3:-/health}" max_time="${4:-2}"
  local scheme body
  scheme="$(naswebui_probe_scheme)"

  local http_url="http://${host}:${port}${path}"

  if [[ "${scheme}" == "http" ]]; then
    if body="$(_naswebui_http_get "${http_url}" "${max_time}" "")"; then
      _NASWEBUI_PROBE_SCHEME="http"
      printf '%s' "${body}"
      return 0
    fi
    return 1
  fi

  local https_url="https://${host}:${port}${path}"

  if _naswebui_truthy "${NASWEBUI_TLS_INSECURE_PROBE:-}"; then
    if body="$(_naswebui_http_get "${https_url}" "${max_time}" "insecure")"; then
      _NASWEBUI_PROBE_SCHEME="https"
      printf '%s' "${body}"
      return 0
    fi
  else
    if body="$(_naswebui_http_get "${https_url}" "${max_time}" "")"; then
      _NASWEBUI_PROBE_SCHEME="https"
      printf '%s' "${body}"
      return 0
    fi
    if body="$(_naswebui_http_get "${https_url}" "${max_time}" "insecure")"; then
      _naswebui_warn_self_signed "${https_url}"
      _NASWEBUI_PROBE_SCHEME="https"
      printf '%s' "${body}"
      return 0
    fi
  fi

  if body="$(_naswebui_http_get "${http_url}" "${max_time}" "")"; then
    _NASWEBUI_PROBE_SCHEME="http"
    printf '%s' "${body}"
    return 0
  fi

  return 1
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  if [[ $# -lt 2 ]]; then
    echo "usage: health_probe.sh <host> <port> [path] [max_time]" >&2
    exit 2
  fi
  naswebui_probe_health "$@"
  exit $?
fi
