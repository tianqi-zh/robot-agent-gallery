# Importing the RoboDojo evaluation

The import is complete: all 42 RoboDojo evaluation episodes and 34 training demonstrations have been added at `robot-agent-gallery/`. The evaluation catalog has **857 scored episodes from 497 tasks across four benchmarks**, extending the earlier 815-episode / 455-task release. The training catalog has 440 videos and 57 unavailable-source entries. Committing and pushing this revision to `main` triggers GitHub Pages; confirm workflow completion and the live catalog before treating it as deployed. No new Release is required.

## Audited evaluation

The only source is `robodojo42_astra_firstpass_20260919`, evaluated on September 19, 2026 with requested model `gpt-6-astra`, `high` reasoning and evaluation seed 0. All 42 standard tasks have exactly one completed policy attempt: **six successes, 36 failures, 14.29% success, zero timeouts and zero infrastructure errors**. There were no retries. Setup/smoke runs and the 12 random task variants are excluded.

The five native task groups are generalization (12), memory (6), precision (8), long-horizon (8) and open (8). Each task keeps its native action horizon. Policies executed 29,557 native actions in total, with eight actual simultaneous policy processes independently verified during the run. The final audit found a maximum overlap of eight policy episodes.

The task instruction is exactly the native `ObsManager.get_obs()[env_idx]['instruction']` supplied to VLA policies. The common prompt contains generic robot/tool procedure; it adds no task-specific description, name or hint. Native instructions are not rewritten or expanded. Policies receive native RGB, robot proprioception and control counters, without camera calibration, depth or privileged task state. Native reward-manager and termination logic determine private scores and success labels.

Private source evidence is under this run's `reports/` directory. The loader requires the complete final audit, final policy-boundary review and summary; the live review is supplementary evidence.

| Source evidence | Scope and role |
| --- | --- |
| `final_audit.json` | `scope=all_42_basic_tasks`, 42 audited episodes, `videos_decoded=true`, `passed=true`, no issues; checks the complete frozen run and every source video. |
| `final_policy_boundary_review.json` | `scope=all_42_terminal_episodes`, `full_scope_complete=true`, 42 reviewed terminal episodes, `passed=true`, no issues or pending/live tasks; checks instruction hashes, public tool fields, camera-block ordering, frozen sources and isolation evidence. |
| `live_boundary_review.json` | Supplementary live verification of eight simultaneous policy processes; this scoped report is not a required loader gate. |
| `summary.json` | 42 terminal/valid episodes, six successes, 36 failures, no timeouts/errors and no retries. |

The frozen manifest SHA256 is `fe327cacc7615e868096a025c1287a8ad070408851bac9104cf132c1349f6fd4`. Source records and reports must refer to that same manifest. Partial reports and synthetic fixtures are insufficient evidence for this import.

Saved tool-event image attachments are intentionally redacted. The frozen online runner decoded the original RGB payloads before redaction; the boundary review verifies retained image-block structure, camera order and matching observation counts. It cannot re-decode removed payload bytes. Source MP4s were independently decoded in full. Historical launch records, unique policy threads and readiness markers support exited policies; the live review supplied direct process checks while the first eight were running. See [METHODOLOGY.md](METHODOLOGY.md) for these limits and the existing benchmarks' recovery rules.

## Import commands

Run from this gallery checkout after the existing 815-episode baseline is present. Python and FFmpeg/ffprobe are required; no simulator or model call is made.

```bash
python3 scripts/robodojo_export.py \
  --run-dir ../robot-agent/eval_runs/robodojo42_astra_firstpass_20260919 \
  --output . \
  --plan-only

python3 scripts/robodojo_export.py \
  --run-dir ../robot-agent/eval_runs/robodojo42_astra_firstpass_20260919 \
  --output . \
  --jobs 4
```

`--plan-only` validates source selection without writing metadata or media. The real evaluation export appends RoboDojo and updates catalog totals and the combined CSV. Existing 815 episode metadata and media records remain unchanged, including RoboCasa's audited recovery selections and public Release URLs. This evaluation exporter does not modify `data/task-demos.json`; training demonstrations are added separately as described in [TRAINING_DEMOS.md](TRAINING_DEMOS.md).

RoboDojo's native score is retained in JSON and provenance. The CSV keeps its existing columns; it does not add a native-score column. Every new episode has a local video path and no `remoteVideo` URL.

## Video preservation and storage

All 42 RoboDojo presentation MP4s and their posters live locally under `media/robodojo/` as ordinary files eligible for Git tracking. The completed export contains **166,020,322 bytes of MP4 video** and 1,208,934 bytes of JPEG posters: 84 ordinary media files totaling 167,229,256 bytes. Each MP4 remains below the repository's individual-file size limit. No new Release is used.

The recordings contain **29,599 frames: 29,557 native actions plus one initial frame per episode**. Presentation encoding retains every frame in order, at **25 FPS and 1920 × 480**, with head, left-wrist and right-wrist views from left to right. There is no added warmup. Total playback is 19 minutes 43.96 seconds; model thinking and tool-transport delays are not represented.

Presentation copies may be compressed using H.264/yuv420p and faststart. Compression changes image quality and file hashes; it must not change frame counts, frame order, FPS, dimensions or camera layout. Source evaluation MP4s remain unchanged, and provenance records distinguish source bytes from presentation bytes.

The separate training-demo import adds 34 exact-task official demonstrations under `media/demos/robodojo/`, using full episode-zero head-camera previews. The eight Open tasks have no matching source in the pinned official training dataset and display **Unavailable**. All 455 earlier training-catalog records are preserved, bringing the catalog to 497 tasks, 440 videos and 57 unavailable-source entries. Demonstrations do not affect the 42 scored RoboDojo evaluation episodes.

## Local verification and preview

The completed evaluation and training import passed **178 automated tests** and the four-benchmark desktop/mobile browser smoke check. The browser verified existing functionality and RoboDojo's 42 tasks, six successes, 36 failures, five groups, search, native score, deep links and demo notice. It reported `errors=[]` and `badResponses=[]`. Its data source was a local HTTP server, not the public website.

The complete local catalog and media-hash validation passed with `--require-robocasa --require-robodojo --require-demos`, confirming 497 tasks and 857 episodes. Release-media validation also passed. After adding training demonstrations, site staging produced 2,241 files totaling about 744.8 MB. Existing three-benchmark objects, all 815 media records and their source selections match the baseline; the CSV retains the original bytes as its prefix. The separate demo update preserves all 455 original training records and adds 42 RoboDojo records, so the training-catalog file hash changes. That update passed 27 focused tests, complete decoding of its 34 videos, and another four-benchmark desktop/mobile browser check. The commands below reproduce validation and preview; `--videos` additionally probes all video recordings.

```bash
python3 scripts/validate_gallery.py \
  --require-robocasa --require-robodojo --require-demos

python3 scripts/validate_gallery.py \
  --require-robocasa --require-robodojo --require-demos --videos

python3 -m http.server 8080
```

Open [the local RoboDojo page](http://localhost:8080/#benchmark=robodojo). Verify task grouping and filtering, episode instruction and native outcome, MP4 playback/download, posters, share-link navigation, the 34 training demos and the eight explicit unavailable states. With the server running, run `npm run test:browser` separately for browser checks.

The combined local validator requires 497 tasks / 857 episodes and the complete 42-task RoboDojo result set. Its video mode checks the presentation recordings against their frame and encoding metadata. After committing and pushing the validated revision to `main`, check the Pages workflow and the deployed catalog and playback. A successful export, local browser test or Git push alone does not establish deployment success.
