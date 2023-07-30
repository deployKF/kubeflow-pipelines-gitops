#!/usr/bin/env bash

set -euo pipefail

# get the folder of this script and cd into it (so relative paths work)
THIS_SCRIPT_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$THIS_SCRIPT_FOLDER"

# get the path of the git repository root
REPOSITORY_ROOT_PATH=$(git rev-parse --show-toplevel)

# source common scripts
source "${REPOSITORY_ROOT_PATH}/common_scripts/kfp.sh"

# define any custom render script arguments
RENDER_SCRIPT_ARGS=(
  #"--my-arg" "my-value"
)

# render the pipeline
render_pipeline \
  "./render_pipeline.py" \
  "./RENDERED/" \
  "./.temp/" \
  "${RENDER_SCRIPT_ARGS[@]}"