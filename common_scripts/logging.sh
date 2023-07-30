#!/usr/bin/env bash

set -euo pipefail

#######################################
# FUNCTIONS
#######################################

function _log() {
  local _level="$1"
  shift
  local _message="$*"

  local _timestamp
  _timestamp=$(date -Iseconds)

  echo >&2 -e "${_timestamp} [${_level}] ${_message}"
}

function log_debug() {
  _log "DEBUG" "$*"
}

function log_info() {
  _log "INFO" "$*"
}

function log_warn() {
  _log "WARN" "$*"
}

function log_error() {
  _log "ERROR" "$*"
}