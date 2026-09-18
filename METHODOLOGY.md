# Evaluation methodology

This gallery publishes all scored episode videos from the completed LIBERO v5 r4 evaluation and RoboTwin first pass, both configured to request `gpt-6-astra` and `high` reasoning on September 17, 2026. This identifies the requested model configuration, not an independent attestation of the served model. Success and failure refer to each benchmark's native score, not the model's written assessment.

## Evaluation sets and selection

**LIBERO v5 r4:** 40 tasks across Spatial, Goal, Object, and LIBERO-10, with official initial states 0–9 for each task: 400 scored episodes. Results are 322 successes and 78 failures. The suite success counts, each out of 100, are 95, 79, 89, and 59 respectively. Every episode allows up to 500 control steps, 750 tool calls, and 3,600 seconds per episode, including initialization. Up to 10 initialization warmup steps are outside the control-step budget.

The source run is `astra_libero_v5_calibrated_parallel10_r4`. Its four infrastructure failures were retried with fresh contexts under the same frozen protocol, producing 404 total attempts and 400 valid final results. Earlier r1–r3 runs are excluded in their entirety. Selection uses the final valid episode result; it does not choose the highest-scoring attempt. Policy failures were not retried to improve the score.

**RoboTwin first pass:** the 50 official tasks, one valid episode per task, using `demo_clean`, the Aloha AgileX embodiment, and seen instructions: 36 successes and 14 failures, including one policy timeout. It uses each task's native action horizon, up to 750 tool calls, and 1,800 seconds of policy time. Environment preparation has a separate timeout.

The source run is `robotwin_astra_firstpass_20260917`. Initial seeds start at 100000. The private host applies RoboTwin's expert validity screening, then resets to the same valid initial scene before the policy begins. Expert actions and state are not policy inputs. Increasing concurrency from six to eight interrupted six active attempts; these six were rerun with fresh contexts. The source retains 56 attempts, yielding 50 final valid results. The separate setup pilot is excluded. No policy failure or timeout was rerun to improve the score.

The gallery includes every selected success and failure. It contains 450 episode videos; no combined success rate is reported.

Displayed elapsed times are runner episode wall times, including preparation and cleanup. They are not model-only inference time or video playback duration.

## Policy inputs and native scoring

Every attempt starts a new policy process and conversation with an empty workspace and isolated temporary state. Episodes do not share conversation history or memory. The policy receives a natural-language instruction, RGB cameras, robot proprioception, camera and robot calibration, and control counters. It can observe, command robot actions, request visual verification, and finish the episode. Within an episode it can use its own interaction history.

LIBERO supplies a scene camera and a wrist camera. RoboTwin supplies a head camera and both wrist cameras. The policy receives no object ground-truth poses, depth, segmentation, contact or grasp labels, reward, success flags, expert trajectories, source files, or external tools.

LIBERO saves the native `env.step()` success result before refreshing synchronized sensors. RoboTwin uses the native success signal latched during action execution. The private evaluator owns scoring and stopping. A `visually_complete` statement does not override the native outcome. Timeouts count as failures; infrastructure errors and interruptions are recorded separately from scored outcomes.

## Video interpretation

LIBERO source videos include one initial frame, the actual warmup frames, and one frame for every control step, played at 20 FPS. Tool calls can include several control steps. Thinking and tool-transport delays are not inserted into playback.

RoboTwin source videos include one initial frame and one frame after every native action, played at 10 FPS. A native action can contain many interpolated physics steps. The video is therefore a sequence of action-end observations, not continuous physical-time playback.

Gallery videos are derived, compressed H.264 presentation assets. Re-encoding changes bytes and image quality, while retaining the source frame count and order. Public export metadata records the relationship between source videos and gallery files. Thumbnails are navigation aids; the full videos determine what is visible.

## Verification and limitations

The public validator checks the expected task/episode matrix, unique identities, aggregate native outcomes, media availability, metadata privacy, and publication size limits. With `--videos`, it decodes frame counts through `ffprobe` and checks H.264 encoding, pixel format, dimensions, and the source-to-export frame-count mapping.

These checks validate the exported metadata and presentation assets. Source provenance fingerprints identify the recorded inputs; they do not independently prove benchmark execution, policy isolation, or the correctness of private simulator scores. The original project performed additional runtime and isolation audits. Raw model reasoning, authentication data, private logs, and machine-local source paths are intentionally outside this publication.

RoboTwin's single sample per task is exploratory and does not estimate variation across initial states. LIBERO's ten initial states per task provide a broader sample, but neither result establishes performance outside the evaluated tasks and protocol. Different controls, camera views, task distributions, and budgets prevent direct comparison or pooling across these benchmarks. The gallery is a complete qualitative record of these selected evaluations, not an ablation study of harness components.
