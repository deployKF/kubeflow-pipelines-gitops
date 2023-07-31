import argparse
import logging
import os
import sys
from typing import List, NamedTuple

from kfp import dsl, compiler, components

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
        description="Render Kubeflow Pipeline into a folder containing a 'workflow.yaml' file and 'params/' folder."
    )
    parser.add_argument(
        "--output-folder",
        help="The path to render the pipeline into (must NOT already exist)",
        required=True,
    )
    return parser.parse_args(args)


####################################################################################################
# Functions
####################################################################################################
def step_0__func() -> NamedTuple("Outputs", utc_epoch=int, day_of_week=str):
    import datetime
    from collections import namedtuple

    # get the current time
    now_utc = datetime.datetime.utcnow()
    utc_epoch = int(now_utc.timestamp())
    day_of_week = now_utc.strftime("%A")

    # return namedtuple() with KFP component outputs
    # https://www.kubeflow.org/docs/components/pipelines/v1/sdk/python-function-components/#building-python-function-based-components
    step_outputs = namedtuple("Outputs", ["utc_epoch", "day_of_week"])
    return step_outputs(utc_epoch=utc_epoch, day_of_week=day_of_week)


def step_1__func(message: components.InputPath(str)):
    print(message)


####################################################################################################
# Main
####################################################################################################
def main(args: List[str]):
    # parse CLI arguments
    args = _parse_args(args)

    # ensure the output folder does not already exist, or is empty
    if os.path.exists(args.output_folder):
        if os.listdir(args.output_folder):
            logger.error(
                f"The output folder already exists, but is not empty: {args.output_folder}"
            )
            sys.exit(1)

    ################################
    # pipeline components
    ################################
    step_0__op = components.create_component_from_func(
        func=step_0__func, base_image="python:3.10"
    )

    step_1__op = components.create_component_from_func(
        func=step_1__func, base_image="python:3.10"
    )

    step_2__op = components.load_component_from_file(filename="example_component.yaml")

    ################################
    # pipeline definition
    ################################
    @dsl.pipeline(name="pipeline_1", description="pipeline_1 description")
    def pipeline(custom_message: str):
        ################################
        # pipeline step 0
        ################################
        step_0 = step_0__op()
        step_0.set_display_name("STEP 0: Get Current Date")

        # disable caching for this step
        step_0.set_caching_options(False)
        step_0.execution_options.caching_strategy.max_cache_staleness = "P0D"

        # unpack outputs from the step
        current_utc_epoch__ref = step_0.outputs["utc_epoch"]
        day_of_week__ref = step_0.outputs["day_of_week"]

        # build message string
        message_string = "\n".join(
            [
                f"current_utc_epoch: {current_utc_epoch__ref}",
                f"day_of_week: {day_of_week__ref}",
                f"custom_message: {custom_message}",
            ]
        )

        ################################
        # pipeline step 1
        ################################
        step_1 = step_1__op(message=message_string)
        step_1.set_display_name("STEP 1: Print Message (Python Function Component)")

        ################################
        # pipeline step 2
        ################################
        step_2 = step_2__op(message=message_string)
        step_2.set_display_name("STEP 2: Print Message (YAML Component)")

    ################################
    # pipeline parameters
    ################################
    pipeline_params = {
        "custom_message": "Hello world!\n" * 10,
    }

    ################################
    # render pipeline
    ################################
    output_folder_path = args.output_folder
    workflow_yaml_path = os.path.join(output_folder_path, "workflow.yaml")
    params_folder_path = os.path.join(output_folder_path, "params")

    # create the output folder
    os.makedirs(output_folder_path, exist_ok=True)

    # write the 'workflow.yaml' file
    compiler.Compiler().compile(pipeline_func=pipeline, package_path=workflow_yaml_path)

    # create the 'params/' folder
    os.makedirs(params_folder_path, exist_ok=True)

    # write parameters to files in the 'params/' folder
    for param_name, param_value in pipeline_params.items():
        param_file_path = os.path.join(params_folder_path, param_name)
        with open(param_file_path, "w") as f:
            f.write(param_value)


if __name__ == "__main__":
    main(args=sys.argv[1:])
