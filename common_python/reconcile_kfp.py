import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

import jsonschema
import kfp
import requests
import urllib3
from kfp_server_api import (
    ApiJob,
    ApiListJobsResponse,
    ApiResourceType,
    ApiPipelineSpec,
    ApiParameter,
    ApiCronSchedule,
    ApiTrigger,
    ApiPeriodicSchedule,
)
from ruamel import yaml

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
    parser = argparse.ArgumentParser(
        description="Reconcile KFP configs (experiments, recurring-runs) into a Kubeflow cluster namespace"
    )
    parser.add_argument(
        "--config-path",
        required=True,
        help="The path to a config folder with 'experiments.yaml' and 'recurring_runs.yaml' files",
    )
    parser.add_argument(
        "--namespace",
        help="The namespace/profile to reconcile the configs into",
    )
    parser.add_argument(
        "--api-url",
        help="The URL of the Kubeflow Pipelines API",
    )
    parser.add_argument(
        "--skip-tls-verify",
        action="store_true",
        help="Whether to skip TLS verification when connecting to the Kubeflow Pipelines API",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="A token for authenticating with GitHub (can also be set via the GITHUB_TOKEN environment variable)",
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
        "--kfp-default-runner-sa",
        default="default-editor",
        help="The default pipeline-runner service account of your Kubeflow Pipelines deployment",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING"],
        help="The log level to use",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Whether to perform a dry run (i.e. don't actually reconcile anything, useful for verifying configs)",
    )

    return parser.parse_args(args)


#########################################################################################
# Constants
#########################################################################################
EXPERIMENTS_SCHEMA = json.loads(
    """
    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "object",
      "properties": {
        "experiments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "minLength": 1
              },
              "description": {
                "type": "string",
                "minLength": 1
              }
            },
            "required": [
              "name"
            ],
            "additionalProperties": false
          }
        }
      },
      "required": [
        "experiments"
      ],
      "additionalProperties": false
    }
    """
)
RECURRING_RUNS_SCHEMA = json.loads(
    """
    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "object",
      "properties": {
        "recurring_runs": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "keep_history": {
                "type": "integer",
                "minimum": -1
              },
              "pipeline_source": {
                "type": "object",
                "properties": {
                  "github_owner": {
                    "type": "string",
                    "minLength": 1
                  },
                  "github_repo": {
                    "type": "string",
                    "minLength": 1
                  },
                  "git_reference": {
                    "type": "string",
                    "minLength": 1
                  },
                  "file_path": {
                    "type": "string",
                    "minLength": 1
                  }
                },
                "required": [
                  "github_owner",
                  "github_repo",
                  "git_reference",
                  "file_path"
                ],
                "additionalProperties": false
              },
              "pipeline_parameters": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "name": {
                      "type": "string",
                      "minLength": 1
                    },
                    "value": {
                      "type": "string"
                    },
                    "valueFrom": {
                      "type": "object",
                      "properties": {
                        "github_owner": {
                          "type": "string",
                          "minLength": 1
                        },
                        "github_repo": {
                          "type": "string",
                          "minLength": 1
                        },
                        "git_reference": {
                          "type": "string",
                          "minLength": 1
                        },
                        "file_path": {
                          "type": "string",
                          "minLength": 1
                        }
                      },
                      "required": [
                        "file_path"
                      ],
                      "additionalProperties": false
                    }
                  },
                  "required": [
                    "name"
                  ],
                  "oneOf": [
                    {
                      "required": [
                        "value"
                      ]
                    },
                    {
                      "required": [
                        "valueFrom"
                      ]
                    }
                  ],
                  "additionalProperties": false
                }
              },
              "job": {
                "type": "object",
                "properties": {
                  "enabled": {
                    "type": "boolean"
                  },
                  "name": {
                    "type": "string",
                    "minLength": 1
                  },
                  "description": {
                    "type": [
                      "string",
                      "null"
                    ],
                    "minLength": 1
                  },
                  "experiment": {
                    "type": "string",
                    "minLength": 1
                  },
                  "max_concurrency": {
                    "type": "integer",
                    "minimum": 1
                  },
                  "service_account": {
                    "type": [
                      "string",
                      "null"
                    ],
                    "minLength": 1
                  },
                  "trigger": {
                    "type": "object",
                    "properties": {
                      "catchup": {
                        "type": "boolean"
                      },
                      "start_date": {
                        "type": [
                          "string",
                          "null"
                        ],
                        "format": "date-time"
                      },
                      "end_date": {
                        "type": [
                          "string",
                          "null"
                        ],
                        "format": "date-time"
                      },
                      "cron": {
                        "type": [
                          "string",
                          "null"
                        ],
                        "pattern": "^[^ ] [^ ] [^ ] [^ ] [^ ] [^ ]$"
                      },
                      "interval_seconds": {
                        "type": [
                          "integer",
                          "null"
                        ],
                        "minimum": 1
                      }
                    },
                    "required": [
                      "catchup"
                    ],
                    "oneOf": [
                      {
                        "properties": {
                          "cron": {
                            "type": "string"
                          }
                        },
                        "required": [
                          "cron"
                        ]
                      },
                      {
                        "properties": {
                          "interval_seconds": {
                            "type": "integer"
                          }
                        },
                        "required": [
                          "interval_seconds"
                        ]
                      }
                    ],
                    "additionalProperties": false
                  }
                },
                "required": [
                  "enabled",
                  "name",
                  "experiment",
                  "max_concurrency",
                  "trigger"
                ],
                "additionalProperties": false
              }
            },
            "required": [
              "pipeline_source",
              "job"
            ],
            "additionalProperties": false
          }
        }
      },
      "required": [
        "recurring_runs"
      ],
      "additionalProperties": false
    }
    """
)


####################################################################################################
# Helpers
####################################################################################################
def get_validator_class(schema: dict) -> jsonschema.Validator:
    """
    Get a JSON schema validator for the given schema (looks at the `$schema` property).
    NOTE: the returned validator has format checking enabled (e.g. for "date-time").
    """
    ValidatorClass = jsonschema.validators.validator_for(schema)
    return ValidatorClass(schema, format_checker=ValidatorClass.FORMAT_CHECKER)


def validate_schema(validator: jsonschema.Validator, data: dict) -> bool:
    """
    Validate the given data against the given JSON schema validator, returning True if valid.
    """
    errors = sorted(validator.iter_errors(data), key=lambda err: err.path)
    for error in errors:
        path = list(error.absolute_path)
        path_str = "/" + "/".join(map(str, path))

        base_message = f"Validation failed at `{path_str}` with error: {error.message}"

        # give more helpful error message for parameters source validation
        if re.fullmatch(
            r"/recurring_runs/[0-9]+/pipeline_parameters/[0-9]+", path_str
        ) and (
            "is valid under each of" in error.message
            or "is not valid under any of the given schemas" in error.message
        ):
            base_message += (
                " -- TIP: you must specify `value` OR `valueFrom`, but NOT both"
            )

        # give more helpful error message for trigger type validation
        if re.fullmatch(r"/recurring_runs/[0-9]+/job/trigger", path_str) and (
            "is valid under each of" in error.message
            or "is not valid under any of the given schemas" in error.message
        ):
            base_message += (
                " -- TIP: you must specify `cron` OR `interval_seconds`, but NOT both"
            )

        # give more helpful error messages for trigger cron validation
        if (
            re.fullmatch(r"/recurring_runs/[0-9]+/job/trigger/cron", path_str)
            and "does not match" in error.message
        ):
            base_message += (
                " -- TIP: Kubeflow Pipelines uses cron expressions with ~6 fields~, "
                "see https://pkg.go.dev/github.com/robfig/cron"
            )

        logger.error(base_message)
    if len(errors) > 0:
        return False
    else:
        return True


def read_file(path: str) -> str:
    """
    Read a file and return its contents as a string.
    """
    with open(path, "r") as f:
        return f.read()


def read_yaml_file(path: str) -> Any:
    """
    Read a YAML file and return the parsed data.

    NOTE: we return dates as ISO 8601 strings, not datetime objects (which are not JSON serializable).
    """

    # Define constructor that converts YAML timestamps to ISO 8601 strings
    def date_constructor(loader, node):
        dt = loader.construct_yaml_timestamp(node)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    # Create the YAML instance with the custom constructor
    custom_yaml = yaml.YAML()
    custom_yaml.constructor.add_constructor(
        "tag:yaml.org,2002:timestamp", date_constructor
    )

    # Read and parse the YAML file
    with open(path, "r") as f:
        try:
            data = custom_yaml.load(f)
        except yaml.YAMLError as ex:
            raise ValueError(f"file at '{path}' is not a valid YAML file") from ex
    return data


def download_github_file(
    github_token: Optional[str],
    github_owner: str,
    github_repo: str,
    git_reference: str,
    file_path: str,
) -> Optional[str]:
    """
    Download a file from GitHub at a specific git reference (branch/tag/commit), returning its path.

    NOTE: files are cached under `.cache` in the current working directory, using the commit hash as the root directory.

    :param github_token: the GitHub token (or None if not set)
    :param github_owner: the GitHub repository owner
    :param github_repo: the GitHub repository name
    :param git_reference: the git reference (branch/tag/commit)
    :param file_path: the path of the file within the repository
    :return: the path of the cached file (or None if something went wrong)
    """

    # create cache directory if it doesn't exist
    cache_dir = os.path.join(".cache")
    os.makedirs(cache_dir, exist_ok=True)

    # set authorization header, if token is provided
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    # get commit hash for the git reference
    api_url = f"https://api.github.com/repos/{github_owner}/{github_repo}/commits/{git_reference}"
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        logger.error(
            f"Failed to retrieve commit hash for reference '{git_reference}': "
            f"{response.status_code} - {response.text}"
        )
        return None
    commit_hash = response.json()["sha"]

    # construct file cache directory using commit hash
    file_cache_dir = os.path.join(
        cache_dir, github_owner, github_repo, commit_hash, os.path.dirname(file_path)
    )
    os.makedirs(file_cache_dir, exist_ok=True)

    # check if file is already cached, otherwise download it
    cached_file_path = os.path.join(file_cache_dir, os.path.basename(file_path))
    if not os.path.exists(cached_file_path):
        download_url = f"https://raw.githubusercontent.com/{github_owner}/{github_repo}/{commit_hash}/{file_path}"
        response = requests.get(download_url, headers=headers, stream=True)
        if response.status_code != 200:
            logger.error(
                f"Failed to download file '{file_path}' at commit '{commit_hash}': "
                f"{response.status_code} - {response.text}"
            )
            return None
        with open(cached_file_path, "wb") as out_file:
            for chunk in response.iter_content(chunk_size=8192):
                out_file.write(chunk)

    return cached_file_path


def validate_workflow_yaml(
    workflow_yaml: str, file_path: str
) -> (bool, Dict[str, bool]):
    """
    Validate the given workflow YAML is a valid Argo Workflow resource, and extract the input parameters.
    :return: a tuple of (workflow_is_valid, {param_name: is_optional})
    """
    # Parse the YAML string
    try:
        yaml_data = yaml.safe_load(workflow_yaml)
    except yaml.YAMLError as ex:
        logger.error(f"Failed to parse workflow YAML file '{file_path}': {ex}")
        return False

    # Unpack the YAML data
    api_version = yaml_data.get("apiVersion", None)
    kind = yaml_data.get("kind", None)
    metadata = yaml_data.get("metadata", None)
    spec = yaml_data.get("spec", None)

    # Validate the YAML data
    valid_workflow = True
    if api_version != "argoproj.io/v1alpha1":
        logger.error(
            f"Invalid workflow YAML file '{file_path}': "
            f"`apiVersion` must be 'argoproj.io/v1alpha1', but was '{api_version}'"
        )
        valid_workflow = False
    if kind != "Workflow":
        logger.error(
            f"Invalid workflow YAML file '{file_path}': "
            f"`kind` must be 'Workflow', but was '{kind}'"
        )
        valid_workflow = False
    if metadata is None:
        logger.error(
            f"Invalid workflow YAML file '{file_path}': missing `metadata` section"
        )
        valid_workflow = False
    if spec is None:
        logger.error(
            f"Invalid workflow YAML file '{file_path}': missing `spec` section"
        )
        valid_workflow = False

    # Extract pipeline input parameters (and if they are optional)
    input_parameters = {}
    if valid_workflow:
        annotations = metadata.get("annotations", {})
        pipeline_spec_json = annotations.get(
            "pipelines.kubeflow.org/pipeline_spec", None
        )
        if pipeline_spec_json is None:
            logger.error(
                f"Invalid workflow YAML file '{file_path}': "
                f"missing `pipelines.kubeflow.org/pipeline_spec` annotation"
            )
            valid_workflow = False

        # try to parse JSON string
        pipeline_spec = None
        if pipeline_spec_json:
            try:
                pipeline_spec = json.loads(pipeline_spec_json)
            except json.JSONDecodeError as ex:
                logger.error(
                    f"Invalid workflow YAML file '{file_path}': "
                    f"failed to parse `pipelines.kubeflow.org/pipeline_spec` annotation:"
                    f"JSON parse error: {ex}"
                )
                valid_workflow = False

        # extract input parameters
        if pipeline_spec:
            pipeline_spec_parameters = pipeline_spec.get("inputs", [])
            for parameter in pipeline_spec_parameters:
                parameter_name = parameter.get("name", None)
                parameter_optional = parameter.get("optional", False)
                if parameter_name is None:
                    logger.error(
                        f"Invalid workflow YAML file '{file_path}': "
                        f"failed to parse `pipelines.kubeflow.org/pipeline_spec` annotation: "
                        f"missing `name` for parameter"
                    )
                    valid_workflow = False
                    break
                input_parameters[parameter_name] = parameter_optional

    return valid_workflow, input_parameters


def get_existing_recurring_runs(
    kfp_client: kfp.Client, namespace: str, job_name: str
) -> List[ApiJob]:
    """
    Get all existing recurring runs for the given job name, sorted by creation time (newest first).

    NOTE: runs are named like "GIT::{job_name}__{timestamp}", where {timestamp} is "0000-00-00T00-00-00Z"

    :param kfp_client: a KFP client
    :param namespace: the namespace to search in
    :param job_name: the job_name to search for
    :return: the list of recurring runs
    """
    recurring_runs = []
    page_token = ""
    pattern = re.compile(
        r"^GIT::(?P<job_name>.*)__(?P<timestamp>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z)$"
    )
    while True:
        # NOTE: in kfp 1.8, the client does not allow filtering by namespace, so we must call the internal API
        response: ApiListJobsResponse = kfp_client._job_api.list_jobs(
            page_token=page_token,
            page_size=100,
            sort_by="created_at desc",
            resource_reference_key_type=ApiResourceType.NAMESPACE,
            resource_reference_key_id=namespace,
            filter=None,
        )
        job: ApiJob
        for job in response.jobs or []:
            match = pattern.match(job.name)
            if match and match.group("job_name") == job_name:
                recurring_runs.append(job)

        if response.next_page_token:
            page_token = response.next_page_token
        else:
            break

    # sort recurring runs by their timestamp (newest first)
    recurring_runs.sort(
        key=lambda j: pattern.match(j.name).group("timestamp"), reverse=True
    )

    return recurring_runs


def compare_api_job(
    api_job: ApiJob,
    workflow_yaml: str,
    job_name: str,
    job_description: Optional[str],
    job_experiment_id: str,
    job_max_concurrency: int,
    job_service_account: str,
    job_parameters: Dict[str, str],
    job_trigger_catchup: bool,
    job_trigger_start_date: Optional[str],
    job_trigger_end_date: Optional[str],
    job_trigger_cron: Optional[str],
    job_trigger_interval_seconds: Optional[int],
) -> bool:
    """
    Compares an ApiJob (recurring run) to the given parameters, returns True if they are the same.
    """
    # unpack some of the inner objects from `api_job`
    api_pipeline_spec: ApiPipelineSpec = api_job.pipeline_spec
    api_parameters_list: List[ApiParameter] = api_pipeline_spec.parameters or []
    api_trigger: ApiTrigger = api_job.trigger
    api_cron_schedule: Optional[ApiCronSchedule] = api_trigger.cron_schedule
    api_periodic_schedule: Optional[ApiPeriodicSchedule] = api_trigger.periodic_schedule

    # unpack the Argo Workflow YAML from `api_job`
    api_workflow_json: str = api_pipeline_spec.workflow_manifest
    if not api_workflow_json:
        raise ValueError(
            f"Encountered ApiJob (ID={api_job.id}, NAME={api_job.name}) with no `workflow_manifest`, "
            f"are you using a supported version of Kubeflow Pipelines?"
        )

    # unpack `api_job` into local variables
    api_description: str = api_job.description
    api_experiment_id: str
    for ref in api_job.resource_references:
        if ref.key.type == ApiResourceType.EXPERIMENT:
            api_experiment_id = ref.key.id
            break
    else:
        raise ValueError(
            f"Encountered ApiJob (ID={api_job.id}, NAME={api_job.name}) with no `EXPERIMENT` in `resource_reference`, "
            f"are you using a supported version of Kubeflow Pipelines?"
        )
    api_max_concurrency: int = int(api_job.max_concurrency)
    api_service_account: str = api_job.service_account
    api_parameters: Dict[str, str] = {
        # NOTE: empty-string parameter values become None in the API, so we replace them for comparison
        p.name: (p.value or "")
        for p in api_parameters_list
    }
    api_trigger_catchup: bool = not api_job.no_catchup
    api_trigger_start_date: Optional[datetime] = None
    api_trigger_end_date: Optional[datetime] = None
    api_trigger_cron: Optional[str] = None
    api_trigger_interval_seconds: Optional[int] = None
    if api_periodic_schedule:
        if api_periodic_schedule.interval_second:
            api_trigger_interval_seconds = int(api_periodic_schedule.interval_second)
        api_trigger_start_date = api_periodic_schedule.start_time
        api_trigger_end_date = api_periodic_schedule.end_time
    elif api_cron_schedule:
        api_trigger_cron = api_cron_schedule.cron
        api_trigger_start_date = api_cron_schedule.start_time
        api_trigger_end_date = api_cron_schedule.end_time

    # cast `api_trigger_start_date` and `api_trigger_end_date` to strings
    if api_trigger_start_date:
        api_trigger_start_date = api_trigger_start_date.isoformat()
    if api_trigger_end_date:
        api_trigger_end_date = api_trigger_end_date.isoformat()

    # compare the given parameters to the unpacked `api_job`
    found_change = False
    if api_description != job_description:
        logger.debug(
            f"Job '{job_name}' has changed `description` "
            f"| OLD: {api_description} "
            f"| NEW: {job_description}"
        )
        found_change = True
    if api_experiment_id != job_experiment_id:
        logger.debug(
            f"Job '{job_name}' has changed `experiment_id` "
            f"| OLD: {api_experiment_id} "
            f"| NEW: {job_experiment_id}"
        )
        found_change = True
    if api_max_concurrency != job_max_concurrency:
        logger.debug(
            f"Job '{job_name}' has changed `max_concurrency` "
            f"| OLD: {api_max_concurrency} "
            f"| NEW: {job_max_concurrency}"
        )
        found_change = True
    if api_service_account != job_service_account:
        logger.debug(
            f"Job '{job_name}' has changed `service_account` "
            f"| OLD: {api_service_account} "
            f"| NEW: {job_service_account}"
        )
        found_change = True
    if api_parameters != job_parameters:
        logger.debug(
            f"Job '{job_name}' has changed `parameters` "
            f"| OLD: {api_parameters} "
            f"| NEW: {job_parameters}"
        )
        found_change = True
    if api_trigger_catchup != job_trigger_catchup:
        logger.debug(
            f"Job '{job_name}' has changed `trigger_catchup` "
            f"| OLD: {api_trigger_catchup} "
            f"| NEW: {job_trigger_catchup}"
        )
        found_change = True
    if api_trigger_start_date != job_trigger_start_date:
        logger.debug(
            f"Job '{job_name}' has changed `trigger_start_date` "
            f"| OLD: {api_trigger_start_date} "
            f"| NEW: {job_trigger_start_date}"
        )
        found_change = True
    if api_trigger_end_date != job_trigger_end_date:
        logger.debug(
            f"Job '{job_name}' has changed `trigger_end_date` "
            f"| OLD: {api_trigger_end_date} "
            f"| NEW: {job_trigger_end_date}"
        )
        found_change = True
    if api_trigger_cron != job_trigger_cron:
        logger.debug(
            f"Job '{job_name}' has changed `trigger_cron` "
            f"| OLD: {api_trigger_cron} "
            f"| NEW: {job_trigger_cron}"
        )
        found_change = True
    if api_trigger_interval_seconds != job_trigger_interval_seconds:
        logger.debug(
            f"Job '{job_name}' has changed `trigger_interval_seconds` "
            f"| OLD: {api_trigger_interval_seconds} "
            f"| NEW: {job_trigger_interval_seconds}"
        )
        found_change = True

    # compare the given Argo Workflow YAML to the one in `api_job`
    api_workflow: Dict[str, Any] = json.loads(api_workflow_json)
    job_workflow: Dict[str, Any] = yaml.safe_load(workflow_yaml)
    if not compare_workflows(api_workflow, job_workflow):
        logger.debug(f"Job '{job_name}' has changed workflow definition")
        found_change = True

    return not found_change


def compare_workflows(
    workflow_1: Dict[str, Any],
    workflow_2: Dict[str, Any],
    ignore_keys: Tuple[str] = (
        "pipelines.kubeflow.org/pipeline_compilation_time",
        "pipelines.kubeflow.org/kfp_sdk_version",
    ),
    float_tol: float = 1e-9,
) -> bool:
    """
    Compares two Argo Workflow dictionaries, returns True if they are equal.
    NOTE: data under `ignore_keys` at any level will be ignored during comparison.
    """

    def compare_recursive(item_1, item_2, current_key=None):
        # base case: both items are None
        if item_1 is None and item_2 is None:
            return True

        # base case: one of the items is None
        if item_1 is None or item_2 is None:
            return False

        # ignore comparison if key is in `ignore_keys`
        if current_key in ignore_keys:
            return True

        # check the type of the items
        type_1 = type(item_1)
        type_2 = type(item_2)

        # if types are different, the items are not equal
        if type_1 != type_2:
            return False

        # handle dictionaries
        if isinstance(item_1, dict):
            keys_1 = set(key for key in item_1 if key not in ignore_keys)
            keys_2 = set(key for key in item_2 if key not in ignore_keys)

            if keys_1 != keys_2:
                return False

            for key in keys_1:
                if not compare_recursive(item_1.get(key), item_2.get(key), key):
                    return False

        # handle lists
        elif isinstance(item_1, list):
            if len(item_1) != len(item_2):
                return False

            for index in range(len(item_1)):
                if not compare_recursive(item_1[index], item_2[index]):
                    return False

        # handle floating point numbers
        elif isinstance(item_1, float):
            return abs(item_1 - item_2) < float_tol

        # handle strings, numbers, booleans
        else:
            return item_1 == item_2

        # all checks passed, items are equal
        return True

    return compare_recursive(workflow_1, workflow_2)


def get_new_job_name(job_name: str) -> str:
    """
    Returns a new job name based on the given job name and the current timestamp.
    FORMAT: "GIT::{job_name}__{timestamp}", where {timestamp} is "0000-00-00T00-00-00Z"
    """
    # use an ISO8601-like timestamp format (':' is replaced with '-' for safety)
    now_string = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"GIT::{job_name}__{now_string}"


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

    # notify user if `--dry-run` is enabled
    if args.dry_run:
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.warning("!!! DRY RUN: NO CHANGES WILL BE MADE !!!")
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    # apply `--skip-tls-verify`
    if args.skip_tls_verify:
        api_session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ensure required arguments are provided and non-empty
    if not args.dry_run:
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
    if not args.kfp_default_runner_sa:
        raise ValueError("the --kfp-default-runner-sa must not be empty")

    # ensure `--api-url` is reachable
    if not args.dry_run:
        try:
            api_get = api_session.get(args.api_url, timeout=5)
        except requests.exceptions.ConnectionError as ex:
            raise ValueError(f"failed to resolve --api-url '{args.api_url}'") from ex
        if api_get.status_code != 200:
            raise ValueError(
                f"the --api-url '{args.api_url}' returned status code {api_get.status_code}"
            )

    # ensure `--config-path` exists and is a directory
    if not os.path.isdir(args.config_path):
        raise ValueError(
            f"the --config-path '{args.config_path}' is not a directory or does not exist"
        )

    # ensure `--config-path` contains `experiments.yaml`
    experiments_path = os.path.join(args.config_path, "experiments.yaml")
    if not os.path.isfile(experiments_path):
        raise ValueError(
            f"the --config-path '{args.config_path}' does not contain 'experiments.yaml'"
        )

    # ensure `--config-path` contains `recurring_runs.yaml`
    recurring_runs_path = os.path.join(args.config_path, "recurring_runs.yaml")
    if not os.path.isfile(recurring_runs_path):
        raise ValueError(
            f"the --config-path '{args.config_path}' does not contain 'recurring_runs.yaml'"
        )

    # read `experiments.yaml` and validate
    experiments = read_yaml_file(path=experiments_path)
    experiments_validator = get_validator_class(EXPERIMENTS_SCHEMA)
    experiments_is_valid = validate_schema(
        validator=experiments_validator, data=experiments
    )
    if not experiments_is_valid:
        raise ValueError(
            f"file at '{experiments_path}' is not a valid 'experiments.yaml' file"
        )

    # read `recurring_runs.yaml` and validate
    recurring_runs = read_yaml_file(path=recurring_runs_path)
    recurring_runs_validator = get_validator_class(RECURRING_RUNS_SCHEMA)
    recurring_runs_is_valid = validate_schema(
        validator=recurring_runs_validator,
        data=recurring_runs,
    )
    if not recurring_runs_is_valid:
        raise ValueError(
            f"file at '{recurring_runs_path}' is not a valid 'recurring_runs.yaml' file"
        )

    # create kfp client (if `--dry-run` is enabled, do nothing)
    if args.dry_run:
        kfp_client = None
    else:
        kfp_client_manager = KFPClientManager(
            api_url=args.api_url,
            dex_username=args.dex_username,
            dex_password=args.dex_password,
            dex_auth_type=args.dex_auth_type,
            skip_tls_verify=args.skip_tls_verify,
        )
        kfp_client = kfp_client_manager.get_kfp_client()

        # test the client works with the given namespace
        try:
            kfp_client.list_experiments(namespace=args.namespace)
        except Exception as ex:
            raise RuntimeError(
                f"Failed to list experiments in namespace '{args.namespace}' "
                f"(TIP: ensure '{args.namespace}' exists and '{args.dex_username}' has access to it)"
            ) from ex

    # store experiment name to id mapping (used to reconcile recurring runs)
    experiment_names_to_id = {}

    # reconcile experiments
    for experiment_spec in experiments["experiments"]:
        experiment_name = experiment_spec["name"]
        experiment_description = experiment_spec.get("description", "")
        experiment_namespace = args.namespace

        if logger.getEffectiveLevel() <= logging.DEBUG:
            logger.info(
                f"Reconciling experiment '{experiment_name}' in namespace '{experiment_namespace}' "
                f"with spec: {json.dumps(experiment_spec)}"
            )
        else:
            logger.info(
                f"Reconciling experiment '{experiment_name}' in namespace '{experiment_namespace}'"
            )

        # do nothing if `--dry-run` is enabled
        if args.dry_run:
            logger.warning(
                f"(DRY RUN) skipping reconciliation of experiment '{experiment_name}'"
            )
            experiment_names_to_id[experiment_name] = None
            continue

        # get or create experiment
        try:
            experiment_api = kfp_client.get_experiment(
                experiment_name=experiment_name, namespace=experiment_namespace
            )
        except ValueError as err:
            if not str(err).startswith("No experiment is found with name"):
                raise err
            logger.info(f"Experiment '{experiment_name}' does not exist, creating it")
            experiment_api = kfp_client.create_experiment(
                name=experiment_name,
                namespace=experiment_namespace,
                description=experiment_description,
            )
        # NOTE: empty-string experiment descriptions become None in the API, so we replace them for comparison
        if (experiment_api.description or "") != experiment_description:
            logger.warning(
                f"Experiment '{experiment_name}' already exists but has an unexpected description "
                f"(EXPECTED: '{experiment_description}', ACTUAL: '{experiment_api.description}') "
                "Descriptions can not be updated, leaving experiment unchanged..."
            )

        # ensure the experiment is not archived
        # NOTE: in kfp 1.8, the client does not allow unarchiving experiments, so we must call the internal API
        kfp_client._experiment_api.unarchive_experiment(id=experiment_api.id)

        # store experiment name to id mapping
        experiment_names_to_id[experiment_name] = experiment_api.id

    # validate all recurring before starting reconciliation
    found_job_names = set()
    for recurring_run_spec in recurring_runs["recurring_runs"]:
        # unpack `pipeline_source`
        pipeline_source = recurring_run_spec["pipeline_source"]
        pipeline_source_github_owner = pipeline_source["github_owner"]
        pipeline_source_github_repo = pipeline_source["github_repo"]
        pipeline_source_git_reference = pipeline_source["git_reference"]
        pipeline_source_file_path = pipeline_source["file_path"]

        # unpack `pipeline_parameters`
        pipeline_parameters = recurring_run_spec.get("pipeline_parameters", [])

        # unpack `job`
        job = recurring_run_spec["job"]
        job_name = job["name"]
        job_experiment = job["experiment"]

        if logger.getEffectiveLevel() <= logging.DEBUG:
            logger.info(
                f"Validating recurring run '{job_name}' with spec: {json.dumps(recurring_run_spec)}"
            )
        else:
            logger.info(f"Validating recurring run '{job_name}'")

        # require that names are unique
        if job_name in found_job_names:
            raise ValueError(
                f"Recurring run '{job_name}' is defined more than once "
                f"(TIP: each `job.name` must be unique)"
            )
        found_job_names.add(job_name)

        # require that referenced experiments are defined in `experiments.yaml`
        if job_experiment not in experiment_names_to_id:
            raise ValueError(
                f"Recurring run '{job_name}' references experiment '{job_experiment}', "
                f"which is not defined in {experiments_path}"
            )

        # download pipeline package (or use cached version)
        pipeline_package_path = download_github_file(
            github_token=args.github_token,
            github_owner=pipeline_source_github_owner,
            github_repo=pipeline_source_github_repo,
            git_reference=pipeline_source_git_reference,
            file_path=pipeline_source_file_path,
        )
        if pipeline_package_path is None:
            raise ValueError(
                f"failed to get pipeline source for recurring run '{job_name}' from GitHub "
                f"repo `{pipeline_source_github_owner}/{pipeline_source_github_repo}` "
                f"at git reference '{pipeline_source_git_reference}' under path '{pipeline_source_file_path}'"
            )

        pipeline_source["_pipeline_package_path"] = pipeline_package_path

        # validate pipeline package and extract pipeline parameters
        if pipeline_package_path.endswith(".yaml"):
            workflow_yaml = read_file(path=pipeline_package_path)
            workflow_yaml_is_valid, workflow_yaml_parameters = validate_workflow_yaml(
                workflow_yaml=workflow_yaml, file_path=pipeline_package_path
            )
            if not workflow_yaml_is_valid:
                raise ValueError(
                    f"pipeline source for recurring run '{job_name}' not a valid Argo Workflow resource"
                )
        else:
            raise ValueError(
                f"pipeline source for recurring run '{job_name}' is not a YAML file"
            )
        pipeline_source["_workflow_yaml"] = workflow_yaml

        # unpack pipeline parameters
        pipeline_parameters_map = {}
        for pipeline_parameter in pipeline_parameters:
            param_name = pipeline_parameter["name"]
            param_value = pipeline_parameter.get("value", None)
            param_value_from = pipeline_parameter.get("valueFrom", None)

            # ensure `name` is unique
            if param_name in pipeline_parameters_map:
                raise ValueError(
                    f"Recurring run '{job_name}' has multiple pipeline parameters with the name '{param_name}' "
                    f"(TIP: each `pipeline_parameters[].name` must be unique)"
                )

            # if `value` is specified, use it
            if param_value is not None:
                pipeline_parameters_map[param_name] = param_value

            # if `valueFrom` is specified, use it
            elif param_value_from is not None:
                param_value_github_owner = param_value_from.get(
                    "github_owner", pipeline_source_github_owner
                )
                param_value_github_repo = param_value_from.get(
                    "github_repo", pipeline_source_github_repo
                )
                param_value_git_reference = param_value_from.get(
                    "git_reference", pipeline_source_git_reference
                )
                param_value_file_path = param_value_from["file_path"]

                # download pipeline parameter file (or use cached version)
                local_param_value_file_path = download_github_file(
                    github_token=args.github_token,
                    github_owner=param_value_github_owner,
                    github_repo=param_value_github_repo,
                    git_reference=param_value_git_reference,
                    file_path=param_value_file_path,
                )
                if local_param_value_file_path is None:
                    raise ValueError(
                        f"failed to get file for parameter '{param_name}' of recurring run "
                        f"'{job_name}' from GitHub repo `{param_value_github_owner}/{param_value_github_repo}` "
                        f"at git reference '{param_value_git_reference}' under path '{param_value_file_path}'"
                    )

                # read parameter value from file
                param_value = read_file(path=local_param_value_file_path)
                pipeline_parameters_map[param_name] = param_value

            # otherwise, raise an error
            else:
                raise ValueError(
                    f"Recurring run '{job_name}' has pipeline parameter '{param_name}' "
                    f"with neither a `value` nor a `valueFrom` specified"
                )
        pipeline_source["_pipeline_parameters_map"] = pipeline_parameters_map

        # validate pipeline parameters
        pipeline_parameters_map_set = set(pipeline_parameters_map)
        workflow_yaml_parameters_set = set(workflow_yaml_parameters)
        if pipeline_parameters_map_set != workflow_yaml_parameters_set:
            # ensure all required parameters have been specified
            missing_parameters = (
                workflow_yaml_parameters_set - pipeline_parameters_map_set
            )
            missing_parameters_filtered = {
                param_name
                for param_name in missing_parameters
                # remove any optional parameters
                if not workflow_yaml_parameters[param_name]
            }
            if missing_parameters_filtered:
                raise ValueError(
                    f"Recurring run '{job_name}' was missing required pipeline parameters: "
                    f"{list(missing_parameters_filtered)}"
                )

            # ensure no extra parameters have been specified
            extra_parameters = (
                pipeline_parameters_map_set - workflow_yaml_parameters_set
            )
            if extra_parameters:
                raise ValueError(
                    f"Recurring run '{job_name}' specified unexpected pipeline parameters: "
                    f"{list(extra_parameters)}"
                )

    # reconcile recurring runs
    for recurring_run_spec in recurring_runs["recurring_runs"]:
        keep_history = recurring_run_spec.get("keep_history", 5)

        # unpack `pipeline_source` (these keys are populated during validation)
        pipeline_source = recurring_run_spec["pipeline_source"]
        pipeline_package_path = pipeline_source["_pipeline_package_path"]
        workflow_yaml = pipeline_source["_workflow_yaml"]

        # unpack `pipeline_parameters` (these keys are populated during validation)
        pipeline_parameters_map = pipeline_source["_pipeline_parameters_map"]

        # unpack `job`
        job = recurring_run_spec["job"]
        job_enabled = job["enabled"]
        job_name = job["name"]
        job_description = job.get("description", None)
        job_experiment = job["experiment"]
        job_max_concurrency = job["max_concurrency"]
        job_service_account = (
            job.get("service_account", None) or args.kfp_default_runner_sa
        )

        # unpack `job.trigger`
        job_trigger = job["trigger"]
        job_trigger_catchup = job_trigger["catchup"]
        job_trigger_start_date = job_trigger.get("start_date", None)
        job_trigger_end_date = job_trigger.get("end_date", None)
        job_trigger_cron = job_trigger.get("cron", None)
        job_trigger_interval_seconds = job_trigger.get("interval_seconds", None)

        logger.info(
            f"Reconciling recurring run '{job_name}' in namespace '{args.namespace}'"
        )

        # do nothing if `--dry-run` is enabled
        if args.dry_run:
            logger.warning(
                f"(DRY RUN) skipping reconciliation of recurring run '{job_name}'"
            )
            continue

        # get existing scheduled runs for this job, sorted newest to oldest
        existing_scheduled_runs = get_existing_recurring_runs(
            kfp_client=kfp_client, namespace=args.namespace, job_name=job_name
        )

        # get the latest scheduled run
        latest_scheduled_run = None
        if existing_scheduled_runs:
            latest_scheduled_run = existing_scheduled_runs[0]

        # check if the latest scheduled run is up-to-date
        latest_is_up_to_date = False
        if latest_scheduled_run:
            latest_is_up_to_date = compare_api_job(
                api_job=latest_scheduled_run,
                workflow_yaml=workflow_yaml,
                job_name=job_name,
                job_description=job_description,
                job_experiment_id=experiment_names_to_id[job_experiment],
                job_max_concurrency=job_max_concurrency,
                job_service_account=job_service_account,
                job_parameters=pipeline_parameters_map,
                job_trigger_catchup=job_trigger_catchup,
                job_trigger_start_date=job_trigger_start_date,
                job_trigger_end_date=job_trigger_end_date,
                job_trigger_cron=job_trigger_cron,
                job_trigger_interval_seconds=job_trigger_interval_seconds,
            )

        # disable any other scheduled runs for this job
        for scheduled_run in existing_scheduled_runs[1:]:
            if scheduled_run.enabled:
                logger.warning(
                    f"Recurring run '{scheduled_run.name}' is no longer the latest, "
                    f"but it's currently enabled."
                )
                logger.info(
                    f"Disabling recurring run '{scheduled_run.name}' in namespace '{args.namespace}'"
                )
                kfp_client.disable_job(job_id=scheduled_run.id)

        # if the latest scheduled run is up-to-date, ensure its `enabled` state is correct
        if latest_is_up_to_date:
            # job is declared as enabled, but latest is disabled
            if job_enabled and (not latest_scheduled_run.enabled):
                logger.warning(
                    f"Expected recurring run '{latest_scheduled_run.name}' to be enabled, "
                    f"but it's currently disabled."
                )
                logger.info(
                    f"Enabling recurring run '{latest_scheduled_run.name}' in namespace '{args.namespace}'"
                )
                # NOTE: in kfp 1.8, the client does not expose `.enable_job()`, so we must call the internal API
                kfp_client._job_api.enable_job(id=latest_scheduled_run.id)

            # job is declared as disabled, but latest is enabled
            elif (not job_enabled) and latest_scheduled_run.enabled:
                logger.warning(
                    f"Expected recurring run '{latest_scheduled_run.name}' to be disabled, "
                    f"but it's currently enabled."
                )
                logger.info(
                    f"Disabling recurring run '{latest_scheduled_run.name}' in namespace '{args.namespace}'"
                )
                kfp_client.disable_job(job_id=latest_scheduled_run.id)

            # job is declared as enabled, and latest is enabled
            else:
                logger.debug(
                    f"Recurring run '{job_name}' is already up-to-date with version '{latest_scheduled_run.name}'"
                )

        # if the latest scheduled run is not up-to-date, create a new scheduled run
        new_scheduled_run = None
        if not latest_is_up_to_date:
            new_job_name = get_new_job_name(job_name=job_name)
            logger.info(
                f"Creating disabled recurring run '{new_job_name}' in namespace '{args.namespace}'"
            )
            new_scheduled_run = kfp_client.create_recurring_run(
                # NOTE: the job is disabled initially, and is enabled later if everything is successful
                enabled=False,
                experiment_id=experiment_names_to_id[job_experiment],
                job_name=new_job_name,
                description=job_description,
                start_time=job_trigger_start_date,
                end_time=job_trigger_end_date,
                interval_second=job_trigger_interval_seconds,
                cron_expression=job_trigger_cron,
                max_concurrency=job_max_concurrency,
                no_catchup=not job_trigger_catchup,
                params=pipeline_parameters_map,
                pipeline_package_path=pipeline_package_path,
                service_account=job_service_account,
            )

            # add the new scheduled run to the list of existing scheduled runs
            # NOTE: this is needed so only exactly `keep_history` scheduled runs are kept
            existing_scheduled_runs.insert(0, new_scheduled_run)

            # disable the previous "latest scheduled run"
            if latest_scheduled_run:
                logger.info(
                    f"Disabling previous recurring run '{latest_scheduled_run.name}' in namespace '{args.namespace}'"
                )
                kfp_client.disable_job(job_id=latest_scheduled_run.id)

            # enable the "new scheduled run", if necessary
            if job_enabled:
                logger.info(
                    f"Enabling new recurring run '{new_scheduled_run.name}' in namespace '{args.namespace}'"
                )
                # NOTE: in kfp 1.8, the client does not expose `.enable_job()`, so we must call the internal API
                kfp_client._job_api.enable_job(id=new_scheduled_run.id)

        # delete any scheduled runs older than `keep_history`
        if keep_history != -1:
            if len(existing_scheduled_runs) > keep_history:
                logger.info(
                    f"Will remove {len(existing_scheduled_runs) - keep_history} old recurring runs in "
                    f"namespace '{args.namespace}' (keep_history={keep_history})"
                )
            for scheduled_run in existing_scheduled_runs[keep_history:]:
                logger.info(
                    f"Deleting recurring run '{scheduled_run.name}' in namespace '{args.namespace}'"
                )
                kfp_client.delete_job(job_id=scheduled_run.id)


if __name__ == "__main__":
    main(args=sys.argv[1:])
