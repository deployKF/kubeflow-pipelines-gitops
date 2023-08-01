#!/usr/bin/env bash

# get the path of the git repository root
REPOSITORY_ROOT_PATH=$(git rev-parse --show-toplevel)

# source common scripts
source "${REPOSITORY_ROOT_PATH}/common_scripts/logging.sh"
source "${REPOSITORY_ROOT_PATH}/common_scripts/python.sh"

#######################################
# FUNCTIONS
#######################################

# compares two pipeline folders
# returns "true" if they are different and "false" if they are the same
function _pipeline_folders_are_different() {
  local _pipeline_folder_1="$1"
  local _pipeline_folder_2="$2"

  local _compare_pipelines_script
  _compare_pipelines_script="$(git rev-parse --show-toplevel)/common_python/compare_rendered_pipelines.py"

  log_info "comparing pipeline folders '${_pipeline_folder_1}' and '${_pipeline_folder_2}'"
  run_python_script "${_compare_pipelines_script}" \
    --pipeline-folder-1 "${_pipeline_folder_1}" \
    --pipeline-folder-2 "${_pipeline_folder_2}"

  if [[ $script_exit_code -eq 0 ]]; then
    echo "false"
  elif [[ $script_exit_code -eq 200 ]]; then
    echo "true"
  else
    log_error "failed to compare pipeline folders"
    log_error "------------------------- SCRIPT OUTPUT -------------------------"
    log_error "${script_output}"
    log_error "-----------------------------------------------------------------"
    exit 1
  fi
}

# renders a pipeline using the given render script and script arguments
function render_pipeline() {
  local _render_script="$1"
  local _output_folder="$2"
  local _temp_folder="$3"
  shift 3
  local _script_args=("$@")

  log_info "cleaning temp folder '${_temp_folder}'"
  rm -rf "${_temp_folder}"

  log_info "rendering pipeline to '${_temp_folder}'"
  run_python_script "${_render_script}" --output-folder "${_temp_folder}" "${_script_args[@]}"

  # ensure the render script exited successfully
  if [[ $script_exit_code -ne 0 ]]; then
    log_error "failed to render pipeline"
    log_error "------------------------- SCRIPT OUTPUT -------------------------"
    log_error "${script_output}"
    log_error "-----------------------------------------------------------------"
    exit 1
  fi

  # compare rendered pipeline with existing pipeline
  local _pipeline_has_changed
  if [[ -d "${_output_folder}" ]]; then
    _pipeline_has_changed=$(_pipeline_folders_are_different "${_output_folder}" "${_temp_folder}")
  else
    _pipeline_has_changed="true"
  fi

  # if the pipeline has changed, copy the rendered pipeline to the output folder
  if [[ "$_pipeline_has_changed" == "true" ]]; then
    log_info "pipeline has changed since last render"

    # clean the output folder
    if [[ -d "${_output_folder}" ]]; then
      log_info "cleaning output folder '${_output_folder}'"
      rm -rf "${_output_folder}"
    fi

    # copy the rendered pipeline to the output folder
    log_info "copying rendered pipeline to '${_output_folder}'"
    mkdir -p "${_output_folder}"
    cp -r "${_temp_folder}" "${_output_folder}"
  else
    log_info "pipeline has not changed, keeping existing pipeline at '${_output_folder}'"
  fi
}