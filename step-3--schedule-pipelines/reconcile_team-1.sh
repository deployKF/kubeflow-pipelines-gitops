#!/usr/bin/env bash

set -euo pipefail

# get the folder of this script and cd into it (so relative paths work)
THIS_SCRIPT_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$THIS_SCRIPT_FOLDER"

# get the path of the git repository root
REPOSITORY_ROOT_PATH=$(git rev-parse --show-toplevel)

# source common scripts
source "${REPOSITORY_ROOT_PATH}/common_scripts/python.sh"

# set authentication environment variables
# TIP: can also be set with the `--dex-username` and `--dex-password` script arguments
export DEX_USERNAME="user1@example.com"
export DEX_PASSWORD="user1"

# set github token (for accessing private repositories)
# TIP: can also be set with the `--github-token` script argument
#GITHUB_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# run the pipeline
PYTHONPATH=$(get_pythonpath) python "${REPOSITORY_ROOT_PATH}/common_python/reconcile_kfp.py" \
  --config-path "./team-1" \
  --namespace "team-1" \
  --api-url "https://deploykf.example.com:8443/pipeline" \
  --skip-tls-verify