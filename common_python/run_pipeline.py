import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Union

import requests
import urllib3

from common_python.kfp_client_manager import KFPClientManager

#########################################################################################
# Logging
#########################################################################################
logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
logger.addHandler(handler)


#########################################################################################
# Arguments
#########################################################################################
def _parse_args(args: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a rendered pipeline")
    parser.add_argument(
        "--pipeline-folder",
        help="Path to the pipeline folder (must contain a `workflow.yaml` file, and possibly `params` folder)",
        required=True,
    )
    parser.add_argument(
        "--run-name",
        help="The name to use for this run (will be formatted as `MANUAL::{run_name}__{timestamp}`)",
        required=True,
    )
    parser.add_argument(
        "--experiment-name",
        help="The name of the experiment to run the pipeline in (must already exist)",
        required=True,
    )
    parser.add_argument(
        "--namespace",
        help="The namespace/profile to run the pipeline in",
        required=True,
    )
    parser.add_argument(
        "--api-url",
        help="The URL of the Kubeflow Pipelines API",
        required=True,
    )
    parser.add_argument(
        "--skip-tls-verify",
        action="store_true",
        help="Whether to skip TLS verification when connecting to the Kubeflow Pipelines API",
    )
    parser.add_argument(
        "--dex-username",
        default=os.environ.get("DEX_USERNAME"),
        help="The username to use for Dex authentication (can also be set via the DEX_USERNAME environment variable)",
    )
    parser.add_argument(
        "--dex-password",
        default=os.environ.get("DEX_PASSWORD"),
        help="The password to use for Dex authentication (can also be set via the DEX_PASSWORD environment variable)",
    )
    parser.add_argument(
        "--dex-auth-type",
        default="local",
        choices=["ldap", "local"],
        help="The auth type to use if Dex has multiple enabled",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING"],
        help="The log level to use",
    )

    return parser.parse_args(args)


####################################################################################################
# Helpers
####################################################################################################
def read_file(path: Union[str, Path]) -> str:
    """
    Read a file and return its contents as a string.
    """
    with open(path, "r") as f:
        return f.read()


def get_job_name(job_name: str) -> str:
    """
    Returns a new job name based on the given job name and the current timestamp.
    FORMAT: "MANUAL::{job_name}__{timestamp}", where {timestamp} is "0000-00-00T00-00-00Z"
    """
    # use an ISO8601-like timestamp format (':' is replaced with '-' for safety)
    now_string = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"MANUAL::{job_name}__{now_string}"


####################################################################################################
# Main
####################################################################################################
def main(args: List[str]):
    # parse CLI arguments
    args = _parse_args(args)

    # create a requests session for the Kubeflow Pipelines API
    api_session = requests.Session()

    # apply `--log-level`
    logger.setLevel(args.log_level)

    # apply `--skip-tls-verify`
    if args.skip_tls_verify:
        api_session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ensure required arguments are provided and non-empty
    if not args.run_name:
        raise ValueError("the --run-name must not be empty")
    if not args.experiment_name:
        raise ValueError("the --experiment-name must not be empty")
    if not args.api_url:
        raise ValueError("the --api-url must not be empty")
    if not args.dex_username:
        raise ValueError(
            "the --dex-username argument or `DEX_USERNAME` environment variable must not be empty"
        )
    if not args.dex_password:
        raise ValueError(
            "the --dex-password argument or `DEX_PASSWORD` environment variable must not be empty"
        )
    if not args.namespace:
        raise ValueError("the --namespace must not be empty")

    # ensure `--api-url` is reachable
    try:
        api_get = api_session.get(args.api_url, timeout=5)
    except requests.exceptions.ConnectionError as ex:
        raise ValueError(f"failed to resolve --api-url '{args.api_url}'") from ex
    if api_get.status_code != 200:
        raise ValueError(
            f"the --api-url '{args.api_url}' returned status code {api_get.status_code}"
        )

    # ensure that the pipeline folder exists
    pipeline_folder = Path(args.pipeline_folder)
    if not pipeline_folder.is_dir():
        logger.error(f"Pipeline folder does not exist: {pipeline_folder}")
        sys.exit(1)

    # ensure that the pipeline folder contains a 'workflow.yaml' file
    workflow_yaml_path = pipeline_folder / "workflow.yaml"
    if not workflow_yaml_path.is_file():
        logger.error(
            f"Pipeline folder does not contain a workflow.yaml file: {workflow_yaml_path}"
        )
        sys.exit(1)

    # check if the pipeline folder contains a 'params' sub-folder
    params_folder = pipeline_folder / "params"
    has_params_folder = params_folder.is_dir()

    # if a 'params' sub-folder exists, get the parameters and values by reading each file
    params = {}
    if has_params_folder:
        for param_file in params_folder.glob("*"):
            param_name = param_file.name
            param_value = read_file(param_file)
            params[param_name] = param_value

    # initialize KFPClientManager
    kfp_client_manager = KFPClientManager(
        api_url=args.api_url,
        dex_username=args.dex_username,
        dex_password=args.dex_password,
        dex_auth_type=args.dex_auth_type,
        skip_tls_verify=args.skip_tls_verify,
    )

    # get an authenticated KFP client
    kfp_client = kfp_client_manager.get_kfp_client()

    # test the client works with the given namespace
    try:
        kfp_client.list_experiments(namespace=args.namespace)
    except Exception as ex:
        raise RuntimeError(
            f"Failed to list experiments in namespace '{args.namespace}' "
            f"(TIP: ensure '{args.namespace}' exists and '{args.dex_username}' has access to it)"
        ) from ex

    # get the kfp experiment
    logger.info(f"Getting experiment: {args.experiment_name}")
    experiment = kfp_client.get_experiment(
        experiment_name=args.experiment_name, namespace=args.namespace
    )

    # calculate the job name
    job_name = get_job_name(args.run_name)

    # run the pipeline
    logger.info(f"Running pipeline: {job_name}")
    kfp_client.run_pipeline(
        experiment_id=experiment.id,
        job_name=job_name,
        pipeline_package_path=str(workflow_yaml_path),
        params=params,
    )


if __name__ == "__main__":
    main(args=sys.argv[1:])
