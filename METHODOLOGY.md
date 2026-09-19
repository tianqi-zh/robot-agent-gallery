# Evaluation methodology

This gallery contains all 857 scored episode videos from 497 tasks across LIBERO v5 r4, RoboTwin first pass, the RoboCasa365 collection and RoboDojo. LIBERO and RoboTwin were evaluated on September 17, 2026; RoboCasa's primary experiment began on September 18, and RoboDojo was evaluated on September 19. Each evaluation requested `gpt-6-astra` with `high` reasoning. This identifies the requested configuration, not an independent attestation of the served model. Success means the benchmark's native score, separate from the model's written assessment or an independent visual judgment.

This revision extends the earlier 815-episode / 455-task release with RoboDojo evaluation and training videos. Pushing `main` triggers Pages; the workflow result and live catalog establish whether deployment has completed. See [the import guide](ROBODOJO_IMPORT.md).

## Evaluation sets and selection

**LIBERO v5 r4:** 40 tasks across Spatial, Goal, Object and LIBERO-10, with official initial states 0–9 per task: 400 episodes, 322 successes and 78 failures (80.5%). Suite success counts, each out of 100, are 95, 79, 89 and 59 respectively. Each episode allows up to 500 control steps, 750 tool calls and 3,600 seconds including initialization. Up to 10 initialization warmup steps are outside the control-step budget.

The source is `astra_libero_v5_calibrated_parallel10_r4`. Four infrastructure failures were retried with fresh contexts under the same frozen protocol, giving 404 retained attempts and 400 valid results. Earlier r1–r3 runs are excluded entirely. Policy failures were not retried to improve the score.

**RoboTwin first pass:** 50 official tasks, one valid episode each, using `demo_clean`, the Aloha AgileX embodiment and seen instructions: 36 successes and 14 failures (72.0%), including one timeout. Each task uses its native action horizon, up to 750 tool calls and 1,800 seconds of policy time. Environment preparation has a separate timeout.

The source is `robotwin_astra_firstpass_20260917`. Initial seeds start at 100000. The private host applies RoboTwin's expert validity screening, then resets to the same valid scene before the policy begins. Expert actions and state are not policy inputs. Increasing concurrency from six to eight interrupted six active attempts, which were rerun with fresh contexts. The source retains 56 attempts and 50 valid results. The setup pilot is excluded; no valid policy failure or timeout was rerun for a better score.

For LIBERO and RoboTwin, the exporter selects the latest attempt for each planned episode and requires success, failure or timeout. Earlier attempts must be documented infrastructure failures or interruptions; it does not select the highest score.

**RoboCasa365:** all 65 atomic and 300 composite tasks, one valid policy episode each, with the PandaOmron mobile manipulator and `pretrain` scene/object split. Native outcomes are 165 successes, 198 non-timeout failures and two timeouts: 45.2% success, with 200 unsuccessful episodes retained.

| Task group | Tasks / episodes | Successes | Non-timeout failures | Timeouts | Success rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Atomic | 65 | 28 | 37 | 0 | 43.1% |
| Composite | 300 | 137 | 161 | 2 | 45.7% |
| All RoboCasa365 | 365 | 165 | 198 | 2 | 45.2% |

The 317 tasks with published v1.0.1 dataset-registry horizons use those action budgets. The remaining 48 use an explicit 7,200-step cap; that fallback is an experiment setting, not a published task-specific horizon. Each episode allows up to 1,500 tool calls and 3,600 seconds of policy time, with a separate 1,800-second preparation timeout. The original run used eight simultaneous policy/simulator pairs. Independent collection checks require evidence of that original overlap and no more than eight overlapping registered attempts.

## RoboDojo first pass

**RoboDojo:** all 42 standard tasks, one episode per task at evaluation seed 0: six successes and 36 failures, or **14.29%** success. There were no timeouts, infrastructure errors, interruptions or retries: 42 retained attempts produced 42 scored episodes. The 12 random variants are outside this standard-task evaluation. The task groups contain 12 generalization, six memory, eight precision, eight long-horizon and eight open tasks.

The sole source is `robodojo42_astra_firstpass_20260919`. Every episode uses its task's native `self.step_lim` action horizon, ranging from 200 to 1,900 actions, up to 1,500 tool calls and 3,600 seconds of policy time. Preparation has a separate 2,400-second timeout. Eight isolated policy/simulator pairs ran concurrently; a live process review verified eight simultaneous policies, and the complete audit found a maximum of eight overlapping policy episodes. This is observed concurrency, not just a worker setting.

The task instruction is the verbatim native `ObsManager.get_obs()[env_idx]['instruction']` supplied to VLA policies. The shared policy prompt contains generic robot/tool procedure only; it adds no task name, task description or task-specific hint. Native task instructions are neither expanded nor rewritten. The policy receives the native RGB cameras, robot proprioception and control counters, with no camera calibration, depth or privileged task state. Each episode has a fresh policy context and isolated workspace, with no reset or memory shared across episodes. Fixed native layout replay and evaluation seed 0 were used without success-based filtering or layout search.

Across the 42 episodes, the policies executed 29,557 native actions. All six successes and all 36 failures are retained. Setup and transport smoke tests are excluded. Native reward-manager and task-termination logic determine the private score and success label; the policy's self-assessment does not replace them.

## RoboCasa recovery and retained evidence

The primary source is `robocasa365_astra_firstpass_20260918`, with seed 100000. The final collection retains 375 attempts: 365 valid selected episodes, six excluded initial-scene rejections and four excluded API infrastructure failures. The four API failures were independently verified and retried at the same seed with fresh policy contexts. All valid policy failures and timeouts were accepted without score-based retries.

Three tasks—PrepareBroilingStation, RecycleBottlesByType and StackCans—each produced two initial-scene rejections at seed 100000. The initial native predicate was already true, before any native action or valid visual observation. Those six attempts remain invalid and unscored even though their private native state records success.

The recovery rule was fixed before replacement-seed runs and required two strict initial-scene rejections at the primary seed 100000 before starting a separate registered run at 100001. A candidate seed could advance to the next integer only if every retained attempt at that seed proved the same initial-scene error with zero native actions and zero valid RGB observations. The first normal RGB observation or native action locked the seed; any ordinary infrastructure failure then required recovery at that same seed, subject to its independent evidence checks. Every candidate and attempt had to be retained, and the first valid success, failure or timeout was accepted regardless of score. All three tasks became executable at 100001, so no higher seed was used:

| Task | Selected seed | Accepted native outcome |
| --- | ---: | --- |
| PrepareBroilingStation | 100001 | Success |
| RecycleBottlesByType | 100001 | Success |
| StackCans | 100001 | Failure |

The other 362 selected episodes retain seed 100000. Replacement runs began after the primary pass and its same-seed recovery finished. Original manifests, attempts and native criteria were preserved. Completion belongs to the independently audited cross-run collection; it does not turn the primary run's invalid scenes into valid results or describe all selected episodes as seed 100000. The public [export report](data/export-report.json) records the source run, seed, attempt and exclusion fingerprints for every selection.

Across all four benchmarks, the gallery includes 497 tasks and 857 valid episodes. It reports per-benchmark rates without pooling them. Task filters retain every selected episode within a matching task; the [CSV](data/episodes.csv) contains the complete set. Displayed elapsed times are runner episode wall times, including preparation and cleanup, rather than model-only inference time or video duration.

## Policy inputs and native scoring

Each attempt starts a new policy process and conversation with an empty workspace and isolated temporary state. Episodes share no conversation history or memory. The policy receives the current instruction, RGB cameras, robot proprioception and control counters. The first three benchmarks also provide camera and robot calibration; RoboDojo provides no camera calibration. It can observe, command actions, request visual verification and finish. It may use its interaction history within that episode.

LIBERO supplies a scene camera and a wrist camera. RoboTwin supplies a head camera and two wrist cameras. RoboCasa supplies left and right agent-view cameras and a wrist camera. RoboDojo supplies native head, left-wrist and right-wrist cameras. The policy receives no object ground-truth poses, depth, segmentation, contact or grasp labels, reward, success flags, expert trajectories, source files or external tools.

LIBERO saves the native `env.step()` success signal before refreshing synchronized sensors. RoboTwin latches native success during action execution. RoboCasa evaluates its native `_check_success()` predicate privately. RoboDojo uses its native reward manager and task-termination logic. The evaluator owns scoring and stopping; a `visually_complete` statement does not override the native result. Timeouts count as failures. Proven infrastructure failures and invalid initial scenes remain separate from scored policy outcomes.

StackCans has a known limitation in its unchanged [native criterion](https://github.com/robocasa/robocasa/blob/4f8a2980def75a55dff96b990745b83540425f09/robocasa/environments/kitchen/composite/arranging_cabinets/stack_cans.py#L118-L157): its pair test uses only world-X separation below 0.02 m, while its height OR imposes no stacking-height constraint. Success requires two disjoint matching pairs and the gripper to be far from all cans, but does not establish actual vertical stacks, Y proximity or can-to-can contact. Native success therefore need not mean visually confirmed physical stacking. The criterion was not modified; the retained seed-100001 policy episode is a native failure.

## Video interpretation and storage

LIBERO source videos include an initial frame, the actual warmup frames and one frame per control step, at 20 FPS. RoboTwin includes an initial frame and one frame after each native action, at 10 FPS; each action can contain many interpolated physics steps. RoboCasa includes an initial frame and every native action, without added warmup, at 20 FPS. Its 1536 × 512 panels are left agent view, right agent view and wrist view. The 365 selected RoboCasa recordings contain 631,117 frames, including 365 initial frames, totaling 8 hours 45 minutes 55.85 seconds of playback. Thinking and tool-transport delays are omitted; these durations are not evaluation wall time.

RoboDojo records an initial frame and every native action, with no added warmup: 29,599 frames across 42 videos, at 25 FPS and 1920 × 480. The panels are head, left wrist and right wrist, in that order. Total recorded playback is 19 minutes 43.96 seconds. The completed presentation export totals 166,020,322 bytes of MP4 video.

Gallery MP4s are compressed H.264/yuv420p presentation copies. Re-encoding changes bytes and image quality while retaining recorded frame count, order, frame rate, dimensions and camera layout. Source recordings remain unchanged. Metadata records source and presentation hashes, and each JPEG poster comes from the episode's middle frame. The existing 450 LIBERO/RoboTwin videos retain their prior presentation encodings and hashes.

All 857 presentation MP4s are kept locally in the export checkout, including the 42 new RoboDojo files under `media/robodojo/`. RoboDojo media is included directly in the repository's static-site build. RoboCasa's 365 MP4s are ignored by Git and delivered publicly through the [same-repository Release](https://github.com/tianqi-zh/robot-agent-gallery/releases/tag/robocasa365-20260918); its posters and metadata are tracked. The static-site build carries LIBERO, RoboTwin and RoboDojo MP4s and their posters, using Release URLs for RoboCasa playback and downloads. This preserves every recorded frame without placing all MP4 bytes in the Pages artifact. The CSV includes both local paths and RoboCasa's public `remoteVideo` URLs.

## Verification and limitations

The final private RoboCasa collection audit rereads retained tool-event records, native trajectories, checkpoints and videos across every registered source. For observation transport, the live host decoded each successful response's three 512 × 512 RGB images and counted successful observations before the image payloads were redacted from the retained event log. The final audit checks the logged response structure, allowed public fields and agreement with those recorded decoding counts; it cannot independently re-decode all the removed JPEG attachments. It also verifies the frozen protocol, task/seed identities, strict exclusion proofs, first-valid-outcome selection and concurrency. Selected and excluded attempts are bound to result/video SHA256 digests and evidence-directory fingerprints. Previous partial or scoped reports cannot substitute for the complete audit.

RoboDojo's private `reports/final_audit.json` covers all 42 standard tasks, passed with no issues, and fully decoded every source video. `reports/final_policy_boundary_review.json` independently covers all 42 terminal episodes and also passed with no issues. It verifies the frozen source hashes, verbatim instruction hashes, allowed tool fields, three native image blocks in camera order, and per-episode isolation evidence. `reports/live_boundary_review.json` additionally checked the first eight simultaneous policy processes while they existed. Historical launch records, unique policy threads and readiness markers support the exited policies; a later audit cannot reread their departed `/proc` entries.

RoboDojo image attachments were decoded as RGB by the frozen online runner before redaction from saved events. The boundary review checks the retained block structure and matching online observation counts; it cannot independently re-decode the removed image bytes. Full MP4 decoding verifies the separate recordings, not the removed tool attachments. These evidence limits remain part of the local import. The local import also passed 178 automated tests, complete catalog/media-hash validation, site staging and the four-benchmark desktop/mobile browser smoke check, with no browser errors or failed responses. These gallery checks are separate from the private evaluation audits and do not indicate publication.

The gallery validator checks the expected task/episode matrix, identities, aggregate native outcomes, CSV agreement, privacy, hashes and size limits. The four-benchmark matrix is 497 tasks / 857 episodes; the earlier three-benchmark release contained 455 / 815. Local `--videos` validation uses `ffprobe` to check frame counts, codec, pixel format, dimensions, frame rates and the source/export frame mapping. Release-media validation verifies all 365 public assets by digest, size, upload state and exact URL, and hashes any local RoboCasa MP4s present. Adding `--videos` in Release mode probes the remote RoboCasa videos too.

The Pages workflow validates the gallery before staging and runs on pushes to `main` or manual dispatch. Full video probing and real browser playback are separate checks; local validation and Git push success do not prove the live site has deployed. The existing RoboCasa Release remains in use. Its original tag-first publication procedure is preserved in [ROBOCASA_IMPORT.md](ROBOCASA_IMPORT.md); RoboDojo media needs no new Release.

Public fingerprints identify the private audited inputs; they do not independently prove simulator correctness or let the public site replay policy isolation. Raw model reasoning, authentication data, private logs and machine-local source paths are excluded. RoboTwin, RoboCasa and RoboDojo each have one sampled valid episode per task, so they do not estimate variation across initial states. RoboCasa's transparent rejection of initially satisfied scenes also changes three sampled initializations. LIBERO's ten initial states give a broader sample, but none of these results establishes performance outside the evaluated tasks and protocol. Different controls, observations, task distributions and budgets prevent direct comparison or pooling. This gallery is a qualitative record of the selected evaluations, not an ablation study of harness components.


## Training demonstration references

Task pages provide training demonstrations when an exact-task source exists in the released datasets. The separate [training catalog](data/task-demos.json) contains 440 videos: 40 LIBERO, 50 RoboTwin, 316 RoboCasa and 34 RoboDojo, plus explicit unavailable records for 49 RoboCasa tasks and eight RoboDojo Open tasks. It records the actual training instruction, source episode, camera, original FPS and file hashes. RoboDojo uses the pinned official dataset's episode-zero head-camera preview for each exact task; the extra training folder `dlc` is not a substitute for any missing Open task. Demo views do not display an agent outcome, seed or evaluation score. The 857 locally cataloged scored evaluation episodes and their aggregate results use the audited evaluation records; demonstration videos do not enter those counts.

The demo exporter retains every frame of one complete recorded training episode and uses its main external camera. Training configurations and object variants can differ from the gallery evaluation scene, and the demo instruction reflects the selected training episode. See [Training demonstrations](TRAINING_DEMOS.md) for source selection, encoding, coverage and reproduction.
