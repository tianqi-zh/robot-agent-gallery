# LIBERO instruction alignment audit

The main comparison covers 40 tasks × 10 fixed initial states. Before: 400 original episodes. After: a composite of 310 unchanged original episodes, 70 first-revision episodes, and 20 final-revision episodes. It is not a fresh 400-episode evaluation.

**Instinct-alignment score (IAS) = 1 − count(agent success AND native benchmark failure) / N.**

The blog uses a two-category reporting convention. Every native benchmark success is accepted as agent success, including episodes terminated by the environment before a finish declaration. Among native failures, an explicit `visually_complete` claim counts as agent success; the remaining episodes count as agent failure. Thus benchmark success is a subset of accepted agent success in this presentation. The converse need not hold. This convention does not rewrite the archived finish records or the native benchmark outcomes.

## Before: original instructions

| Agent assessment | Bench success | Bench failure |
| --- | ---: | ---: |
| Agent success | 322 | 47 |
| Agent failure | `\` | 31 |
| Total | 322 | 78 |

IAS = 1 − 47/400 = **88.25%**. Native success = **322/400 (80.50%)**.

## After: latest instruction composite

| Agent assessment | Bench success | Bench failure |
| --- | ---: | ---: |
| Agent success | 357 | 1 |
| Agent failure | `\` | 42 |
| Total | 357 | 43 |

IAS = 1 − 1/400 = **99.75%**. Native success = **357/400 (89.25%)**. The one remaining explicit false-complete report is `libero_goal_t05_r05` from the final revision.

`\` means not applicable: the agent-failure / bench-success cell cannot occur under the table’s inclusion rule. This is a reporting convention, not a universal guarantee about an unaided model’s beliefs. Five original and nine final-composite native failures ended at the 500-step limit without a finish declaration; the table assigns those to agent failure because no successful completion was declared. This assignment is not a human judgment of their terminal images. The original structured-report accounting is retained in the downloadable data.

The authors used **human-in-the-loop verification of videos where agent and benchmark judgments disagreed**. This review assists interpretation and helps identify mistaken agent self-assessments, so a disagreement is not automatically blamed on benchmark design. Its coverage is the disagreement cases; it does not establish a human rating for every episode. The disagreement counts retain the agent’s original completion claims; they are not corrected human labels.

IAS remains sensitive to reporting behavior. A policy that never declares completion on a native failure can obtain IAS 100% despite zero task success. Indeed, unchanged LIBERO-10 t03 and t09 each have IAS 100% and native success 0/10.

## Revision history

| Panel | Native success | Explicit false completions | IAS |
| --- | ---: | ---: | ---: |
| Original full 400 | 322/400 | 47 | 88.25% |
| First-revision 400 composite | 345/400 | 19 | 95.25% |
| Final 400 composite | 357/400 | 1 | 99.75% |
| Original nine-task subset | 40/90 | 47 | 47.78% |
| First revision of nine tasks | 63/90 | 19 | 78.89% |
| Final nine-task composite | 75/90 | 1 | 98.89% |

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

Nine tasks were selected after inspecting all 47 original explicit false-complete judgments. Each revised task contributes all ten seeds/initial-state IDs 0–9 from its latest specified instruction stage. No favorable per-seed outcome is selected. The spatial regression remains included. Of the 400 paired slots, 38 change failure→success, 3 change success→failure, 319 remain successful, and 40 remain unsuccessful. Reused outcomes are identical by construction, not independent new replications.

The original archive contains 404 attempts for 400 slots. Four infrastructure-error attempts (`codex_error`) were followed by one valid attempt each, at Spatial t02 r00/r02 and LIBERO-10 t03 r03/r04. Each slot has exactly one valid outcome. The 90- and 20-episode reruns have no excluded attempts, infrastructure errors, timeouts, or retries. The archive validates statuses but does not independently diagnose each service error.

The revisions were developed using code, demonstrations, and observed failures, including the same initial states. This is an adaptive diagnostic intervention, not a held-out, preregistered, or causal estimate of the effect of wording. Ten episodes per task and stochastic model responses limit generalization.

## Protocol and provenance

All stages requested `gpt-6-astra`, high reasoning, fixed initial states, 512-pixel camera observations, 500 control steps, 750 tool calls, and a 3,600-second wall-clock limit. Requested model identifiers are verified in the archive; the remote service’s actual resolved model is not independently attested. There was no policy fine-tuning, demonstration input, task-specific cross-episode memory, hidden object-pose input, or native reward/success-label input to the policy. Native success still automatically stops an episode. “Zero-shot” describes this protocol, not guaranteed absence of pretraining exposure.

Worker counts were 10, 8, and 4. Original/first-revision workers used GPUs 4–6; final-revision workers used GPUs 0–3. Native BDDL files, initial-state files, controller/scoring source hashes, tool/control budgets, and generic prompt templates match in checked provenance. The server wrapper/report code changed to support instruction overrides. Scheduling, time of execution, and stochastic outputs are documented differences.

| Stage | Run name | Manifest SHA256 |
| --- | --- | --- |
| Original | `astra_libero_v5_calibrated_parallel10_r4` | `df08694520ff7ea3e9bfee061a29223e46c4db76bc54a07e637cbfcbe93f42f8` |
| Revision 1 | `astra_libero_v5_instruction_refined_parallel8_r1` | `1fe4a3d8fadb450d032d237c5e77f0da1e5275f7452de9988b8fa5c9f28ce269` |
| Revision 2 | `astra_libero_v5_instruction_minimal_parallel4_r2` | `08e43c9fb96ffebf033f0e93fd5371a8ef36b41566eadfa89db80b4958381847` |

Native source: [LIBERO commit 8f1084e](https://github.com/Lifelong-Robot-Learning/LIBERO/tree/8f1084e3132a39270c3a13ebe37270a43ece2a01). The archive audit checks 510 valid attempts, 110 replacement-to-original pairs, 80 native task/initialization files, and 53,662 recorded instruction observations. Native outcomes are cross-checked among result, environment, final state, and trajectory records; explicit assessments must match a structured finish tool call.

## Videos and public verification

[Video metadata](data/libero-blog-media.json) records seven paired cases and four failure examples, with stage, native outcome, explicit assessment, instruction, seed, task rate, and source/output hashes. Each paired example is the lowest rollout index showing the stated transition in the frozen runs. The failure examples are named diagnostic selections after review. They illustrate mechanisms and are not a random sample. Eighteen full recordings preserve original frames, dimensions, and 20 fps playback; scene camera is left and wrist camera right. Inference waiting time is omitted. Nine original videos are reused; nine revision videos are web-compressed. Native success can stop the recording before release.

Public data contain no private reasoning traces, credentials, or host paths. The [400-row CSV](data/libero-alignment-episodes.csv) preserves every slot and all stage assignments; the [aggregate JSON](data/libero-alignment.json) includes matrices, task-level instructions, source hashes, methods, and limitations. Recompute and validate these public exports from this repository:

```sh
python3 scripts/validate_libero_blog.py
python3 scripts/validate_libero_blog.py --probe
```

The second command requires `ffprobe` and checks all video streams. This verifies published accounting and assets; regenerating from the raw runs additionally requires the source archives. Export scripts do not contain those archives. The original gallery remains [400 baseline episodes](gallery/libero/); the essay’s reruns are separate assets.

## Interpretation limits

A higher IAS here means fewer agent-success/native-failure reports under this policy and reporting convention. It does not establish that the native predicate is wrong whenever the agent claims success. Some disagreements are policy errors, including the final plate fixture confusion. Human review of disagreement videos helps diagnose such errors. IAS can improve because native success improves or a failed rollout has no successful-completion claim. Report native success and the reporting rule with it.

The human-in-the-loop review was qualitative verification of disagreement videos, not a controlled human performance study. No post-training experiment was performed. The proposed harm from ambiguous instruction–demonstration pairings is a hypothesis, not a measured degradation of policy quality. A direct experiment would control demonstrations, initialization, and training compute while changing instruction clarity, then evaluate independently specified held-out transfer tasks.
