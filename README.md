# GitOps for Kubeflow Pipelines

This repo demonstrates how GitOps can be used with [Kubeflow Pipelines](https://www.deploykf.org/reference/tools/#kubeflow-pipelines) from [deployKF](https://github.com/deployKF/deployKF).

> __NOTE:__ 
> 
> - This repo is about using GitOps to manage __pipelines definitions__ and __pipeline schedules__ NOT the platform itself.
> - This repo only supports Kubeflow Pipelines compiled in V1 mode.

## Repository Contents

This repository contains the following content:

<table>
  <tr>
    <th>Directory</th>
    <th>Description</th>
  </tr>
  <tr>
    <td>
      <a href="./.github/workflows">
        <code>/.github/workflows/</code>
      </a>
    </td>
    <td>example GitHub Actions workflows</td>
  </tr>
    <td>
      <a href="./common_python">
        <code>/common_python/</code>
      </a>
    </td>
    <td>shared Python code</td>
  </tr>
  <tr>
    <td>
      <a href="./common_scripts">
        <code>/common_scripts/</code>
      </a>
    </td>
    <td>shared Bash scripts</td>
  </tr>
  <tr>
    <td>
      <a href="./step-1--render-pipelines">
        <code>/step-1--render-pipelines/</code>
      </a>
    </td>
    <td>example of rendering Kubeflow Pipelines</td>
  </tr>
  <tr>
    <td>
      <a href="./step-2--run-pipelines">
        <code>/step-2--run-pipelines/</code>
      </a>
    </td>
    <td>example of running rendered Kubeflow Pipelines</td>
  </tr>
  <tr>
    <td>
      <a href="./step-3--schedule-pipelines">
        <code>/step-3--schedule-pipelines/</code>
      </a>
    </td>
    <td>example of scheduling rendered Kubeflow Pipelines using GitOps</td>
  </tr>
</table>

## Real-World Usage

Unlike this demo, in the real world you typically store pipeline definitions and schedules in separate repositories.

For example, you may have the following repositories:

<table>
  <tr>
    <th>Repository</th>
    <th>Purpose</th>
    <th>Demo Steps Used</th>
  </tr>
  <tr>
    <td>
      <code>ml-project-1</code>
    </td>
    <td>contains pipeline definitions for "ml project 1"</td>
    <td rowspan="3">
      <a href="./#step-1-render-pipelines">
        "Step 1: Render Pipelines"
      </a>
      <br>
      <a href="./#step-2-run-pipelines">
        "Step 2: Run Pipelines"
      </a>
    </td>
  </tr>
  <tr>
    <td>
      <code>ml-project-2</code>
    </td>
    <td>contains pipeline definitions for "ml project 2"</td>
  </tr>
  <tr>
    <td>
      <code>ml-project-3</code>
    </td>
    <td>contains pipeline definitions for "ml project 3"</td>
  </tr>
  <tr>
    <td>
      <code>kfp-schedules</code>
    </td>
    <td>manages schedules for all pipelines</td>
    <td>
      <a href="./#step-3-schedule-pipelines">
        "Step 3: Run Schedule Pipelines"
      </a>
    </td>
  </tr>
</table>

The main reasons to use a structure like this are:

- At a fundamental level, pipeline definitions and schedules are different things (with different lifecycles).
- Schedules are typically owned by "operations" teams, while the definitions are typically owned by "data science" teams.
- Machine learning projects often have many pipelines, so logically grouping them makes it easier to manage them.

## Step 1: Render Pipelines

The [Kubeflow Pipelines SDK](https://kubeflow-pipelines.readthedocs.io/en/stable/index.html) is a Python [DSL](https://en.wikipedia.org/wiki/Domain-specific_language) which compiles down to [Argo `Workflow`](https://argoproj.github.io/argo-workflows/workflow-concepts/#the-workflow) resources,
the Kubeflow Pipelines backend is able to execute compiled pipelines on a Kubernetes cluster on a schedule.

To manage pipeline definitions/schedules with GitOps, we need a reliable way to render the pipelines from their "dynamic Python representation" into their "static YAML representation".

For this purpose, you will find the following items under [`/step-1--render-pipelines/example_pipeline_1/`](./step-1--render-pipelines/example_pipeline_1):

<table>
  <tr>
    <th>File/Directory</th>
    <th>Description</th>
  </tr>
  <tr>
    <td>
      <a href="./step-1--render-pipelines/example_pipeline_1/pipeline.py">
        <code>./pipeline.py</code>
      </a>
    </td>
    <td>
      <ul>
        <li>A Python script containing the pipeline definition</li>
        <li>This script exposes an argument named <code>--output-folder</code>,
          which specifies where the rendered pipeline should be saved
        </li>
      </ul>
    </td>
  </tr>
  <tr>
    <td>
      <a href="./step-1--render-pipelines/example_pipeline_1/render_pipeline.sh">
        <code>./render_pipeline.sh</code>
      </a>
    </td>
    <td>
      <ul>
        <li>A Bash script which invokes <code>pipeline.py</code> in a reproducible way, with static arguments</li>
        <li>This script uses shared code from <code>/common_python/</code> and <code>/common_scripts/</code> to ensure
          the rendered pipeline is only updated if the pipeline definition actually changes 
          (rendered pipelines contain the build time, it would always be different)
        </li>
      </ul>
    </td>
  </tr>
  <tr>
    <td>
      <a href="./step-1--render-pipelines/example_pipeline_1/RENDERED_PIPELINE/">
        <code>./RENDERED_PIPELINE/</code>
      </a>
    </td>
    <td>
      <ul>
        <li>A directory containing the output of <code>render_pipeline.sh</code></li>
        <li>This directory contains the following items:</li>
        <ul>
          <li>A <code>workflow.yaml</code> file containing the rendered
            <a href="https://argoproj.github.io/argo-workflows/workflow-concepts/#the-workflow">Argo <code>Workflow</code></a> resource
          </li>
          <li>A <code>params/</code> directory containing a file for each
            <a href="https://www.kubeflow.org/docs/components/pipelines/v1/sdk/parameters/">pipeline parameter</a>
          </li>
        </ul>
      </ul>
    </td>
  </tr>
  <tr>
    <td>
      <a href="./step-1--render-pipelines/example_pipeline_1/example_component.yaml">
        <code>./example_component.yaml</code>
      </a>
    </td>
    <td>
      <ul>
        <li>A YAML file containing the definition of a
          <a href="https://www.kubeflow.org/docs/components/pipelines/sdk/component-development/">reusable kubeflow component</a>
        </li>
        <li>This component is used by <code>pipeline.py</code> to define a step in the pipeline</li>
      </ul>
    </td>
  </tr>
</table>

Additionally, we provide the following GitHub Actions [reusable workflow](https://docs.github.com/en/actions/using-workflows/reusing-workflows#creating-a-reusable-workflow) templates under [`/.github/workflows/`](./.github/workflows):

<table>
  <tr>
    <th>Workflow Template</th>
    <th>Description</th>
  </tr>
  <tr>
    <td>
      <a href="./.github/workflows/_check-pipelines-are-rendered.yaml">
        <code>./_check-pipelines-are-rendered.yaml</code>
      </a>
    </td>
    <td>
      <ul>
        <li>Takes a list named <code>pipeline_render_scripts</code> with paths to scripts like <code>render_pipeline.sh</code> and runs them to ensure PRs have not forgotten to update the rendered pipelines after making changes</li>
        <li>Example of calling workflow: <a href="./.github/workflows/check-pipelines-are-rendered.yaml"><code>./check-pipelines-are-rendered.yaml</code></a></li>
      </ul>
    </td>
  </tr>
</table>

> __WARNING:__
> 
> It is NOT recommended to run `pipeline.py` directly, but rather to use the `render_pipeline.sh` script.

> __TIP:__
> 
> If each run of `render_pipeline.sh` results in a different rendered pipeline, your pipeline definition is not deterministic, 
> for example, it might be using `datetime.now()` in the definition itself, rather than within a step.
>
> If a step in your pipeline requires the current date/time, you may use the Argo Workflows [variables feature](https://argoproj.github.io/argo-workflows/variables/#global) to set a step's inputs:
> 
> - `{{workflow.creationTimestamp.RFC3339}}` becomes the run-time of the workflow ("2030-01-01T00:00:00Z")
> - `{{workflow.creationTimestamp.<STRFTIME_CHAR>}}` becomes the run-time formatted by a single [strftime](https://strftime.org/) character
>     - _TIP: custom time formats can be created using multiple variables, `{{workflow.creationTimestamp.Y}}-{{workflow.creationTimestamp.m}}-{{workflow.creationTimestamp.d}}` becomes "2030-01-01"_

> __TIP:__
> 
> Additional arguments may be added to `pipeline.py` so that the same pipeline definition can render multiple variants.
> 
> - If you do this, you will need to create a separate `render_pipeline.sh` script for each variant, for example, `render_pipeline_dev.sh`, `render_pipeline_test.sh`, `render_pipeline_prod.sh`.
> - These scripts should be configured to render the pipeline into a separate directory, for example, `RENDERED_PIPELINE_dev/`, `RENDERED_PIPELINE_test/`, `RENDERED_PIPELINE_prod/`.

# Step 2: Run Pipelines

Before scheduling a pipeline, developers will likely want to run it manually to ensure it works as expected.

As we have already rendered the pipeline in ["step 1"](./#step-1-render-pipelines), we now need a way to run it.

For this purpose, you will find the following items under [`/step-2--run-pipelines/example_pipeline_1/`](./step-2--run-pipelines/example_pipeline_1):

<table>
  <tr>
    <th>File/Directory</th>
    <th>Description</th>
  </tr>
  <tr>
    <td>
      <a href="./step-2--run-pipelines/example_pipeline_1/run_pipeline.sh">
        <code>./run_pipeline.sh</code>
      </a>
    </td>
    <td>
      <ul>
        <li>A bash script which invokes <a href="./common_python/run_pipeline.py"><code>./common_python/run_pipeline.py</code></a> in a reproducible way</li>
        <li>This script triggers a one-time run of the pipeline rendered at <a href="./step-1--render-pipelines/example_pipeline_1/RENDERED_PIPELINE"><code>./step-1--render-pipelines/example_pipeline_1/RENDERED_PIPELINE</code></a></li>
      </ul>
    </td>
  </tr>
</table>

# Step 3: Schedule Pipelines

TBA