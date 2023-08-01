#!/usr/bin/env bash

set -euo pipefail

# get the folder of this script and cd into it (so relative paths work)
THIS_SCRIPT_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$THIS_SCRIPT_FOLDER"

# get the path of the git repository root
REPOSITORY_ROOT_PATH=$(git rev-parse --show-toplevel)

# source common scripts
source "${REPOSITORY_ROOT_PATH}/common_scripts/step_1.sh"

# define custom render script arguments
# TIP: add new arguments to allow the same pipeline definition to render multiple variants
#      (e.g. create an '--environment' argument which allows values like: "dev", "test", "prod")
RENDER_SCRIPT_ARGS=(
  #"--my-arg" "my-value"
)

# render the pipeline
render_pipeline \
  "./pipeline.py" \
  "./RENDERED_PIPELINE/" \
  "./.temp/" \
  "${RENDER_SCRIPT_ARGS[@]}"