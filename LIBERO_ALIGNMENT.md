# LIBERO instruction alignment audit

The central question is whether an operator can infer the benchmark’s intended goal from its instruction and the visible scene, without demonstration videos or access to the success-checker code. GPT-6 acts as a proxy for that human operator. This is not a controlled measurement of human task performance.

The main comparison covers 40 tasks × 10 fixed initial states. Before: 400 original episodes. After: a composite of 310 unchanged original episodes, 70 first-revision episodes, and 20 final-revision episodes. It is not a fresh 400-episode evaluation.

**Instinct-alignment score (IAS) = 1 − count(agent considers complete AND benchmark judges failure) / N.**

The blog separates the agent’s completion judgment from the benchmark’s verdict. Every outcome the benchmark judges successful is counted as complete on the agent side, including episodes terminated before a finish declaration. For outcomes the benchmark judges failures, retained explicit `visually_complete` claims count as “agent considers complete”; rejected claims and episodes without a completion claim count as “agent does not consider complete.” The review described below supplies the only correction. This accounting convention does not rewrite archived finish records or native outcomes.

## Before: original instructions

| Agent completion judgment | Bench judges success | Bench judges failure |
| --- | ---: | ---: |
| Agent considers complete | 322 | 47 |
| Agent does not consider complete | `\` | 31 |
| Total | 322 | 78 |

IAS = 1 − 47/400 = **88.25%**. Native success = **322/400 (80.50%)**.

## After: latest instruction composite

| Agent completion judgment | Bench judges success | Bench judges failure |
| --- | ---: | ---: |
| Agent considers complete | 357 | 0 |
| Agent does not consider complete | `\` | 43 |
| Total | 357 | 43 |

IAS = 1 − 0/400 = **100.00%** after human adjudication. Native success = **357/400 (89.25%)**. The original completion claim in `libero_goal_t05_r05` was rejected by human review: the policy mistook the wooden cabinet for the stove. This episode is counted as incomplete on the agent side and judged a failure by the benchmark; the native benchmark result remains failure. Before that correction, the raw-report IAS was 99.75%.

`\` means not applicable: the combination “agent does not consider complete / benchmark judges success” cannot occur under the table’s inclusion rule. This is a reporting convention, not a universal guarantee about an unaided model’s beliefs. Five original and nine final-composite native failures ended at the 500-step limit without a finish declaration; the table counts these as “agent does not consider complete” because no completion was declared. This assignment is not a human judgment of their terminal images. The original structured-report accounting is retained in the downloadable data.

The authors used **human-in-the-loop verification of videos where agent and benchmark judgments disagreed**. This review assists interpretation and helps identify mistaken agent self-assessments, so a disagreement is not automatically blamed on benchmark design. Its coverage is the disagreement cases; it does not establish a human rating for every episode. The published tables and IAS use the human-adjudicated labels. The user confirmed that only final-round `libero_goal_t05_r05` has its completion claim corrected to incomplete; all other disagreement labels remain as originally reported. The [correction log and recomputed statistics](data/libero-human-review.json) preserve that decision separately from the raw records.

IAS remains sensitive to reporting behavior. A policy that never declares completion on a native failure can obtain IAS 100% despite zero task success. Indeed, unchanged LIBERO-10 t03 and t09 each have IAS 100% and native success 0/10.

## Revision history

The original and final panels below use the confirmed human adjudications. First-revision rows retain their recorded agent labels; the only correction applies to the final round.

| Panel | Native success | Agent considers complete, benchmark judges failure | IAS |
| --- | ---: | ---: | ---: |
| Original full 400 | 322/400 | 47 | 88.25% |
| First-revision 400 composite | 345/400 | 19 | 95.25% |
| Final 400 composite, human-reviewed | 357/400 | 0 | 100.00% |
| Original nine-task subset | 40/90 | 47 | 47.78% |
| First revision of nine tasks | 63/90 | 19 | 78.89% |
| Final nine-task composite, human-reviewed | 75/90 | 0 | 100.00% |

| Revised task | Original | Revision 1 | Final |
| --- | ---: | ---: | ---: |
| Spatial t04 | 5/10 | 4/10 | 4/10 |
| Goal t00 | 8/10 | 10/10 | 10/10 |
| Goal t05 | 0/10 | 0/10 | 2/10 |
| Goal t09 | 7/10 | 10/10 | 10/10 |
| Object t00 | 2/10 | 10/10 | 10/10 |
| Object t04 | 8/10 | 10/10 | 10/10 |
| LIBERO-10 t05 | 0/10 | 0/10 | 10/10 |
| LIBERO-10 t06 | 1/10 | 9/10 | 9/10 |
| LIBERO-10 t07 | 9/10 | 10/10 | 10/10 |

Only Goal t05 and LIBERO-10 t05 received the final revision. Final instructions are:

- `push the plate to the front of the stove, close to its front edge`
- `pick up the book and place it in the back compartment of the caddy, between the two large side compartments`

All instruction versions are preserved verbatim in [the task records](data/libero-alignment.json). The first plate revision used an erroneous geometric offset caused by confusing the stove fixture origin with the visible burner center. Its 0/10 result remains in the revision history. The final wording contains no numeric distance. Goal t05 remains difficult: seven failures use 496–500 control steps, while one incorrectly identifies the cabinet as the stove and declares completion at 259 steps.

## Selection and pairing

Nine tasks were selected after inspecting all 47 original completion claims rejected by the native benchmark and retained by human review. Each revised task contributes all ten seeds/initial-state IDs 0–9 from its latest specified instruction stage. No favorable per-seed outcome is selected. The spatial regression remains included. Of the 400 paired slots, 38 change failure→success, 3 change success→failure, 319 remain successful, and 40 remain unsuccessful. Reused outcomes are identical by construction, not independent new replications.

The original archive contains 404 attempts for 400 slots. Four infrastructure-error attempts (`codex_error`) were followed by one valid attempt each, at Spatial t02 r00/r02 and LIBERO-10 t03 r03/r04. Each slot has exactly one valid outcome. The 90- and 20-episode reruns have no excluded attempts, infrastructure errors, timeouts, or retries. The archive validates statuses but does not independently diagnose each service error.

The authors developed the revisions using code, demonstrations, and observed failures, including the same initial states. The policy never received the code or demonstration videos directly; it received the resulting revised instruction and live observations. This is an adaptive diagnostic intervention, not a held-out, preregistered, or causal estimate of the effect of wording. Ten episodes per task and stochastic model responses limit generalization.

## Protocol and provenance

All stages requested `gpt-6-astra`, high reasoning, fixed initial states, 512-pixel camera observations, 500 control steps, 750 tool calls, and a 3,600-second wall-clock limit. Requested model identifiers are verified in the archive; the remote service’s actual resolved model is not independently attested. The policy used task instructions, live RGB observations, robot proprioception, camera calibration, and generic control guidance. It had no access to demonstration videos or success-checker code. There was no policy fine-tuning, task-specific cross-episode memory, hidden object-pose input, or native reward/success-label input to the policy. Native success still automatically stops an episode. “Zero-shot” describes this protocol, not guaranteed absence of pretraining exposure.

Worker counts were 10, 8, and 4. Original/first-revision workers used GPUs 4–6; final-revision workers used GPUs 0–3. Native BDDL files, initial-state files, controller/scoring source hashes, tool/control budgets, and generic prompt templates match in checked provenance. The server wrapper/report code changed to support instruction overrides. Scheduling, time of execution, and stochastic outputs are documented differences.

| Stage | Run name | Manifest SHA256 |
| --- | --- | --- |
| Original | `astra_libero_v5_calibrated_parallel10_r4` | `df08694520ff7ea3e9bfee061a29223e46c4db76bc54a07e637cbfcbe93f42f8` |
| Revision 1 | `astra_libero_v5_instruction_refined_parallel8_r1` | `1fe4a3d8fadb450d032d237c5e77f0da1e5275f7452de9988b8fa5c9f28ce269` |
| Revision 2 | `astra_libero_v5_instruction_minimal_parallel4_r2` | `08e43c9fb96ffebf033f0e93fd5371a8ef36b41566eadfa89db80b4958381847` |

Native source: [LIBERO commit 8f1084e](https://github.com/Lifelong-Robot-Learning/LIBERO/tree/8f1084e3132a39270c3a13ebe37270a43ece2a01). The archive audit checks 510 valid attempts, 110 replacement-to-original pairs, 80 native task/initialization files, and 53,662 recorded instruction observations. Native outcomes are cross-checked among result, environment, final state, and trajectory records; explicit assessments must match a structured finish tool call.

## Videos and public verification

[Video metadata](data/libero-blog-media.json) records seven paired cases and four failure examples, with stage, native outcome, explicit assessment, instruction, seed, task rate, and source/output hashes. Each paired example is the lowest rollout index showing the stated transition in the frozen runs. The failure examples are named diagnostic selections after review. They illustrate mechanisms and are not a random sample. Eighteen full recordings preserve original frames, dimensions, and 20 fps playback; scene camera is left and wrist camera right. Inference waiting time is omitted. Nine original videos are reused; nine revision videos are web-compressed. Native success can stop the recording before release.

Public data contain no private reasoning traces, credentials, or host paths. The [400-row CSV](data/libero-alignment-episodes.csv) preserves every slot and all stage assignments; the [raw aggregate JSON](data/libero-alignment.json) includes original self-report matrices, task-level instructions, source hashes, methods, and limitations. The separate [human-review JSON](data/libero-human-review.json) binds each correction to its source result and contains the recomputed two-category tables and IAS. An uncorrected report and an adjudicated assessment remain distinguishable. Recompute and validate these public exports from this repository:

```sh
python3 scripts/validate_libero_blog.py
python3 scripts/validate_libero_blog.py --probe
python3 scripts/review_libero_alignment.py --check --require-complete
```

The second command requires `ffprobe` and checks all video streams. The third recomputes the reviewed tables, checks the correction against the frozen source record, and requires confirmed review coverage. This verifies published accounting and assets; regenerating from the raw runs additionally requires the source archives. Export scripts do not contain those archives. The original gallery remains [400 baseline episodes](gallery/libero/); the essay’s reruns are separate assets.

## Interpretation limits

Instruction refinement can improve agreement about completion while manipulation success stays low or decreases. Spatial t04’s native success fell from 5/10 to 4/10, but explicit completion claims rejected by the benchmark fell from 3 to 0. Four of its six final failures explicitly reported inability to continue; two reached the step limit without claiming completion. The matched r01 episode failed the native check under both instructions, changing from a completion claim to an explicit inability report. Goal t05 improved only from 0/10 to 2/10 native successes while raw rejected completion claims fell from 9 to 1; its last claim is the separately corrected r05. These counts describe closer agreement with the evaluator, not evidence that all original interpretations were unreasonable or all final failures were explicitly recognized.

A higher IAS here means fewer episodes in which the agent considers the task complete but the benchmark judges it a failure, after the documented correction and under the stated reporting convention. Human review corrects known policy self-assessment errors, including the final plate fixture confusion, before the score is computed. The resulting 100% IAS does not mean perfect policy performance: 43 native failures remain, and the review did not independently rate every video. IAS can improve because native success improves or a failed rollout has no successful-completion claim. Report native success and the reporting rule with it.

The human-in-the-loop review was qualitative verification of disagreement videos, not a controlled human performance study. No post-training experiment was performed. The proposed harm from ambiguous instruction–demonstration pairings is a hypothesis, not a measured degradation of policy quality. A direct experiment would control demonstrations, initialization, and training compute while changing instruction clarity, then evaluate independently specified held-out transfer tasks.
