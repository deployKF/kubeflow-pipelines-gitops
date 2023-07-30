# GitOps for Kubeflow Pipelines

This repo demonstrates how GitOps can be used with [Kubeflow Pipelines](https://www.deploykf.org/reference/tools/#kubeflow-pipelines) from [deployKF](https://github.com/deployKF/deployKF).

> __NOTES:__ 
> 
> - This repo is about using GitOps to manage __pipelines definitions__ and __pipeline schedules__ NOT the Kubeflow platform itself.
> - This repo only supports Kubeflow Pipelines compiled in V1 mode.

## Repository Contents

This repository contains the following sections:

- [`/common_python/`](./common_python): shared Python code
- [`/common_scripts/`](./common_scripts): shared Bash scripts
- [`/step-1--render-pipeline/`](./step-1--render-pipelines): examples of rendering Kubeflow Pipelines into YAML files
- [`/step-2--run-pipelines`](./step-2--run-pipelines): examples of running rendered Kubeflow Pipelines
- [`/step-3--schedule-pipelines/`](./step-3--schedule-pipelines): examples of scheduling rendered Kubeflow Pipelines using GitOps

## In the Real World

Unlike this demo, in the real world, you will likely want to store pipeline definitions separate from their schedules.
<br>
For example, you might have the following repositories:

- `ml-project-1`: which contains pipeline definitions for "project 1"
- `ml-project-2`: which contains pipeline definitions for "project 2"
- `ml-project-3`: which contains pipeline definitions for "project 3"
- `kfp-schedules`: which contains schedules for all pipelines

In that case, the `ml-project` repo(s) would be "step 1" and "step 2", and `kfp-schedules` would be "step 3".

## Step 1: Render Pipelines

First, you will need to render your Kubeflow Pipelines into _static YAML files_ that can be used with GitOps.

This is because Kubeflow Pipelines actually a [DSL](https://en.wikipedia.org/wiki/Domain-specific_language) for generating Argo [`Workflow`](https://argoproj.github.io/argo-workflows/workflow-concepts/#the-workflow) resources from Python code.
Therefore, to ensure we know exactly what will be deployed, we need to render the pipelines into static YAML files that can be version controlled.

### Structure of a Rendered Pipeline

A rendered pipeline is a directory containing the following files:

- `workflow.yaml`: the rendered Kubeflow Pipeline (which is an [Argo `Workflow` CRD](https://argoproj.github.io/argo-workflows/workflow-concepts/#the-workflow)
- `params/`: a directory containing files with the values for each [pipeline parameter](https://www.kubeflow.org/docs/components/pipelines/v1/sdk/parameters/)
    - each file is named after the parameter name, and contains the value for that parameter