#!/usr/bin/env bash

set -euo pipefail

# source common scripts
source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"

#######################################
# FUNCTIONS
#######################################

# builds a PYTHONPATH that includes the repository root
function _get_pythonpath() {
  local _repository_root_path
  _repository_root_path=$(git rev-parse --show-toplevel)

  local _pythonpath
  if [[ -z "${PYTHONPATH:-}" ]]; then
    _pythonpath="${_repository_root_path}"
  else
    _pythonpath="${PYTHONPATH}:${_repository_root_path}"
  fi

  echo "${_pythonpath}"
}

# runs a python script with the given arguments
function run_python_script() {
  local _script_path="$1"
  shift
  local _script_args=("$@")

  ## initialize return values
  script_output=""
  script_exit_code=0

  local _pythonpath
  _pythonpath=$(_get_pythonpath)

  log_info "running python script '$(basename "$_script_path")'"
  set +e
  script_output=$(PYTHONPATH="${_pythonpath}" python "$_script_path" "${_script_args[@]}" 2>&1)
  script_exit_code=$?
  set -e
}