# Robot Agent Gallery

Browse all **857 scored episodes from 497 tasks** across four coding-agent robot evaluations, including failures and timeouts. Each policy requests `gpt-6-astra` with `high` reasoning and controls the robot from RGB images and robot proprioception. Calibration inputs depend on the benchmark; RoboDojo receives no camera calibration.

**Website:** [tianqi-zh.github.io/robot-agent-gallery](https://tianqi-zh.github.io/robot-agent-gallery/). This revision adds 42 RoboDojo evaluation episodes and 34 training demonstrations to the earlier 815-episode / 455-task release. A push to `main` triggers GitHub Pages; deployment success and the live catalog must be verified separately.

| Evaluation | Experiment date | Tasks | Episodes | Successes | Failures, including timeouts | Success rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LIBERO v5 r4 | 2026-09-17 | 40 | 400 | 322 | 78 | 80.5% |
| RoboTwin first pass | 2026-09-17 | 50 | 50 | 36 | 14 | 72.0% |
| RoboCasa365 | 2026-09-18 | 365 | 365 | 165 | 200 | 45.2% |
| RoboDojo first pass, local | 2026-09-19 | 42 | 42 | 6 | 36 | 14.29% |

LIBERO suite results are Spatial 95/100, Goal 79/100, Object 89/100 and LIBERO-10 59/100. RoboCasa includes all 65 atomic tasks (28 successes) and 300 composite tasks (137 successes). RoboTwin's failures include one timeout; RoboCasa's include two. RoboDojo has zero timeouts and zero infrastructure errors. RoboTwin, RoboCasa and RoboDojo each have one valid sampled episode per task. Different tasks, controls and budgets prevent direct comparison or a pooled success rate.

Success is the benchmark's native score. It is separate from the policy's written assessment or an independent visual judgment; the [methodology](METHODOLOGY.md) explains the known StackCans criterion limitation and how invalid initial scenes are excluded.

RoboDojo adds all 42 standard tasks from `robodojo42_astra_firstpass_20260919`, with eight verified simultaneous policies and no retries. Its task instruction is exactly the native instruction supplied to VLA policies, with no extra task-specific hint. The shared prompt supplies generic robot/tool procedure only. The policies executed 29,557 native actions; all 29,599 recorded frames are retained. See [RoboDojo import and audit evidence](ROBODOJO_IMPORT.md).

Videos are compressed presentation copies retaining every recorded frame. LIBERO plays at 20 FPS, including initialization and warmup. RoboTwin plays at 10 FPS, with an initial frame and one frame after each native action. RoboCasa plays at 20 FPS across three camera views. RoboDojo plays at 25 FPS in a 1920 × 480 head/left-wrist/right-wrist panel. RoboCasa and RoboDojo include an initial frame and every native action. Thinking and transport delays are omitted; playback duration is not evaluation wall time.

## Local preview and browsing

With the full local media export present, serve this checkout:

```bash
python3 -m http.server 8080
```

Open [localhost:8080](http://localhost:8080/) or the [local RoboDojo view](http://localhost:8080/#benchmark=robodojo). The website is static and requires no model access or API key.

1. Choose a benchmark and suite or task group, search task names or instructions, and filter by **With failures** or **All successful**. RoboCasa has **Atomic** and **Composite** groups; RoboDojo has five native task groups.
2. Open a task or episode. LIBERO retains all ten episodes per task; RoboTwin, RoboCasa and RoboDojo each show one. The player displays the native outcome, instruction, seed, action count and recorded camera views.
3. Use **Copy episode link** or **Download MP4**. Share links use the current server address. Public RoboDojo links require a completed deployment containing this revision.

Outcome filters select tasks and retain all episodes within each matching task. The [episode CSV](data/episodes.csv) contains the complete 857-episode set. Its `video` column is the local path; `remoteVideo` retains RoboCasa's public MP4 URL. RoboDojo uses relative paths to repository media.

There are 440 training reference videos: 40 LIBERO, 50 RoboTwin, 316 RoboCasa and 34 RoboDojo. The other 49 RoboCasa tasks and eight RoboDojo Open tasks display an explicit unavailable state because the released training data has no matching demonstration. RoboDojo references use complete official episode-zero head-camera previews; only those previews and source metadata are downloaded. All 497 tasks have a training-catalog record. See [training sources and export details](TRAINING_DEMOS.md). Demo videos have their own share links and do not contribute to evaluation counts.

## Media storage

LIBERO and RoboTwin MP4s and all JPEG posters are stored in the repository. The 365 RoboCasa presentation MP4s are kept locally under `media/robocasa/` in the export checkout but ignored by Git; their public copies are assets of the existing [same-repository Release](https://github.com/tianqi-zh/robot-agent-gallery/releases/tag/robocasa365-20260918).

The 42 new RoboDojo MP4s and posters are ordinary local files under `media/robodojo/`, eligible for Git tracking. The completed import contains 166,020,322 bytes of RoboDojo MP4 video, retaining all 29,599 frames. They have no `remoteVideo` URL and no new Release. Original evaluation recordings remain in the source run; presentation compression preserves frame count, order, FPS, dimensions and camera layout.

A fresh clone can preview all four benchmarks while using RoboCasa's existing Release videos:

```bash
python3 scripts/validate_gallery.py --require-robocasa --require-robodojo --require-demos --release-media
python3 scripts/build_site.py
python3 -m http.server 8080 --directory _site
```

The staged preview uses network access for RoboCasa videos. Serving the repository root uses local MP4 paths, so a fresh clone needs the RoboCasa files downloaded into `media/robocasa/` or reproduced from the audited source. The RoboDojo addition and its verification are described separately in [ROBODOJO_IMPORT.md](ROBODOJO_IMPORT.md).

## Validate the local four-benchmark import

The completed local import passed 178 automated tests, complete catalog/media-hash validation, site staging and the four-benchmark desktop/mobile browser smoke check, with no browser errors or failed responses. See [the import record](ROBODOJO_IMPORT.md) for coverage and media totals.

With all 857 evaluation MP4s and the existing training videos present locally:

```bash
python3 scripts/validate_gallery.py --require-robocasa --require-robodojo --require-demos
python3 scripts/validate_gallery.py --require-robocasa --require-robodojo --require-demos --videos
```

The first command checks the task matrix, native results, CSV, metadata, media hashes, training-catalog coverage and size limits. The second also uses `ffprobe` to verify video frames and encoding metadata. The training catalog accounts for all 497 tasks, including explicit unavailable records, and preserves the original 455 task records.

Existing RoboCasa Release checks remain available with `python3 scripts/release_media.py --check` and the validator's `--release-media` option. They verify public asset names, SHA256 digests, sizes, upload state and URLs. Local RoboCasa files are still checked when present; `--release-media --videos` also probes remote videos and requires network access.

With a local server running, the browser check exercises task groups, filters, episode switching, playback, share links, history navigation and mobile layouts:

```bash
npm ci
npx playwright install chromium
npm run test:browser
```

Pass a different website URL after `--` to check it. Screenshots are saved under the ignored `artifacts/browser/` directory. Node dependencies are only needed for this check.

The export contains task descriptions, results and provenance fingerprints. It excludes raw model reasoning, credentials, private logs and source-machine paths. Gallery checks do not replace the private source audit; see [METHODOLOGY.md](METHODOLOGY.md).

## Publication status

The [Pages workflow](.github/workflows/pages.yml) runs after a push to `main` or manual dispatch, validates the catalog and stages the website. A successful Git push does not establish a successful deployment: check the workflow result and the live site afterward. RoboDojo media is included in the repository build; the existing RoboCasa Release remains unchanged.

[ROBOCASA_IMPORT.md](ROBOCASA_IMPORT.md) preserves the earlier three-benchmark Release publication and recovery procedure. It describes the earlier 815-episode baseline; the RoboDojo evaluation and training imports extend that catalog.

## Files and rebuilding

- `index.html`, `app.js`, `styles.css`: static interface.
- `data/gallery.json` and `data/episodes.csv`: the local task and episode catalog.
- `data/task-demos.json`, `media/demos/`: training mappings, videos and posters for all four benchmarks.
- `data/export-report.json`: source selections, exclusion provenance and media fingerprints.
- `media/libero/`, `media/robotwin/`, `media/robocasa/`, `media/robodojo/`: presentation media.
- `scripts/export_gallery.py`, `scripts/robocasa_export.py`: the earlier three-benchmark source export.
- `scripts/robodojo_export.py`: audited additive RoboDojo import, preserving the existing 815 episode records and media.
- `scripts/export_training_demos.py`, `scripts/export_robocasa_demos.py`, `scripts/export_robodojo_demos.py`, `scripts/assemble_training_demos.py`: training-video export and catalog assembly.
- `scripts/validate_gallery.py`, `scripts/release_media.py`, `scripts/build_site.py`: verification, existing Release handling and site staging.

Rebuilding requires Python 3.10+, FFmpeg/ffprobe and the private original evaluation runs. Reproduce the three-benchmark baseline using [ROBOCASA_IMPORT.md](ROBOCASA_IMPORT.md), including its registered recovery runs and full collection audit, then add RoboDojo using [ROBODOJO_IMPORT.md](ROBODOJO_IMPORT.md). Exporters read existing recordings; they do not call a model or start new episodes. The public gallery alone does not include the private evidence needed to repeat the source audits.
