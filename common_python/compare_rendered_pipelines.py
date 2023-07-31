import argparse
import logging
import os
import sys
from typing import List, Dict, Any, Tuple

from ruamel import yaml

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
        description="Compare two pipeline folders (exit status: 0=equal, 1=error, 200=different)"
    )
    parser.add_argument(
        "--pipeline-folder-1",
        help="Path to the first pipeline folder (must contain a `workflow.yaml` file, and possibly `params` folder)",
        required=True,
    )
    parser.add_argument(
        "--pipeline-folder-2",
        help="Path to the second pipeline folder (must contain a `workflow.yaml` file, and possibly `params` folder)",
        required=True,
    )

    return parser.parse_args(args)


####################################################################################################
# Helpers
####################################################################################################
def read_file(path: str) -> str:
    """
    Read a file and return its contents as a string.
    """
    with open(path, "r") as f:
        return f.read()


def compare_file_contents(file_path_1: str, file_path_2: str) -> bool:
    """
    Compare the contents of two files.
    """
    file_contents_1 = read_file(file_path_1)
    file_contents_2 = read_file(file_path_2)
    return file_contents_1 == file_contents_2


def validate_workflow_yaml(workflow_yaml: str, file_path: str) -> bool:
    """
    Validate the given workflow YAML is a valid Argo Workflow resource.
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

    return valid_workflow


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


####################################################################################################
# Main
####################################################################################################
def main(args: List[str]):
    # parse CLI arguments
    args = _parse_args(args)

    # ensure provided folders exist
    if not os.path.isdir(args.pipeline_folder_1):
        logger.error(
            f"(EXIT CODE: 1) Pipeline folder '{args.pipeline_folder_1}' does not exist"
        )
        sys.exit(1)
    if not os.path.isdir(args.pipeline_folder_2):
        logger.error(
            f"(EXIT CODE: 1) Pipeline folder '{args.pipeline_folder_2}' does not exist"
        )
        sys.exit(1)

    # ensure provided folders contain workflow YAML files
    workflow_yaml_path_1 = os.path.join(args.pipeline_folder_1, "workflow.yaml")
    workflow_yaml_path_2 = os.path.join(args.pipeline_folder_2, "workflow.yaml")
    if not os.path.isfile(workflow_yaml_path_1):
        logger.error(
            f"(EXIT CODE: 1) Pipeline folder '{args.pipeline_folder_1}' does not contain workflow.yaml"
        )
        sys.exit(1)
    if not os.path.isfile(workflow_yaml_path_2):
        logger.error(
            f"(EXIT CODE: 1) Pipeline folder '{args.pipeline_folder_2}' does not contain workflow.yaml"
        )
        sys.exit(1)

    # validate workflow YAML files
    workflow_yaml_1 = read_file(workflow_yaml_path_1)
    workflow_yaml_2 = read_file(workflow_yaml_path_2)
    if not validate_workflow_yaml(workflow_yaml_1, workflow_yaml_path_1):
        logger.error(
            f"(EXIT CODE: 1) Workflow YAML file '{workflow_yaml_path_1}' is not a valid Argo Workflow"
        )
        sys.exit(1)
    if not validate_workflow_yaml(workflow_yaml_2, workflow_yaml_path_2):
        logger.error(
            f"(EXIT CODE: 1) Workflow YAML file '{workflow_yaml_path_2}' is not a valid Argo Workflow"
        )
        sys.exit(1)

    # check if each folder contains a "params/" folder
    params_path_1 = os.path.join(args.pipeline_folder_1, "params")
    params_path_2 = os.path.join(args.pipeline_folder_2, "params")
    pipeline_1_has_params = os.path.isdir(params_path_1)
    pipeline_2_has_params = os.path.isdir(params_path_2)

    # if both folders contain a "params/" folder, compare the params
    if pipeline_1_has_params and pipeline_2_has_params:
        # get list of params files in each folder
        params_files_1 = set(
            f
            for f in os.listdir(params_path_1)
            if os.path.isfile(os.path.join(params_path_1, f))
        )
        params_files_2 = set(
            f
            for f in os.listdir(params_path_2)
            if os.path.isfile(os.path.join(params_path_2, f))
        )

        # check if the two folders contain the same params files
        if params_files_1 != params_files_2:
            logger.info(
                "(EXIT CODE: 200) Pipeline folders contain different 'params/' files"
            )
            sys.exit(200)

        # compare the params files
        for params_file in params_files_1:
            params_file_path_1 = os.path.join(params_path_1, params_file)
            params_file_path_2 = os.path.join(params_path_2, params_file)
            if not compare_file_contents(params_file_path_1, params_file_path_2):
                logger.info(
                    f"(EXIT CODE: 200) Pipeline folders contain different 'params/{params_file}' files"
                )
                sys.exit(200)

    # if only one folder contains a "params/" folder, the folders are not equal
    elif pipeline_1_has_params or pipeline_2_has_params:
        logger.info(
            "(EXIT CODE: 200) Pipeline folders contain different 'params/' files"
        )
        sys.exit(200)

    # compare workflow YAML files
    workflow_1 = yaml.safe_load(workflow_yaml_1)
    workflow_2 = yaml.safe_load(workflow_yaml_2)
    if not compare_workflows(workflow_1, workflow_2):
        logger.info("(EXIT CODE: 200) Workflow YAML files are not equal")
        sys.exit(200)

    # if we get here, the folders are equal
    logger.info("(EXIT CODE: 0) Pipeline folders are equal")
    sys.exit(0)


if __name__ == "__main__":
    main(args=sys.argv[1:])
