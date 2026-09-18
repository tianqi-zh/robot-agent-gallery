# Robot Agent Gallery

Browse all **815 scored episodes from 455 tasks** across three coding-agent robot evaluations, including failures and timeouts. Each policy requests `gpt-6-astra` with `high` reasoning and controls the robot from RGB images, robot proprioception and calibration.

**Website:** [tianqi-zh.github.io/robot-agent-gallery](https://tianqi-zh.github.io/robot-agent-gallery/)

| Evaluation | Experiment date | Tasks | Episodes | Successes | Failures, including timeouts | Success rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LIBERO v5 r4 | 2026-09-17 | 40 | 400 | 322 | 78 | 80.5% |
| RoboTwin first pass | 2026-09-17 | 50 | 50 | 36 | 14 | 72.0% |
| RoboCasa365 | 2026-09-18 | 365 | 365 | 165 | 200 | 45.2% |

LIBERO suite results are Spatial 95/100, Goal 79/100, Object 89/100 and LIBERO-10 59/100. RoboCasa includes all 65 atomic tasks (28 successes) and 300 composite tasks (137 successes). RoboTwin's failures include one timeout; RoboCasa's include two. RoboTwin and RoboCasa each have one valid sampled episode per task. Different tasks, controls and budgets prevent direct comparison or a pooled success rate.

Success is the benchmark's native score. It is separate from the policy's written assessment or an independent visual judgment; the [methodology](METHODOLOGY.md) explains the known StackCans criterion limitation and how invalid initial scenes are excluded.

Videos are compressed presentation copies retaining every recorded frame. LIBERO plays at 20 FPS, including initialization and warmup. RoboTwin plays at 10 FPS, with an initial frame and one frame after each native action. RoboCasa plays at 20 FPS, with an initial frame and every native action across three camera views. Thinking and transport delays are omitted; playback duration is not evaluation wall time.

## Browse and share

Open [LIBERO](https://tianqi-zh.github.io/robot-agent-gallery/#benchmark=libero), [RoboTwin](https://tianqi-zh.github.io/robot-agent-gallery/#benchmark=robotwin), or [RoboCasa365](https://tianqi-zh.github.io/robot-agent-gallery/#benchmark=robocasa), then:

1. Choose a benchmark and suite or task group, search task names or instructions, and filter by **With failures** or **All successful**. RoboCasa has **Atomic** and **Composite** groups.
2. Open a task or episode. LIBERO retains all 10 episodes per task; RoboTwin and RoboCasa each show one. The player displays the native outcome, instruction, seed, action count and recorded camera views.
3. Use **Copy episode link** or **Download MP4**. For example: [RoboCasa, Prepare Broiling Station](https://tianqi-zh.github.io/robot-agent-gallery/#benchmark=robocasa&task=robocasa_preparebroilingstation&episode=robocasa_preparebroilingstation_r00).

Outcome filters select tasks and retain all episodes within each matching task. The [episode CSV](data/episodes.csv) contains the complete 815-episode set. Its `video` column is the local path; `remoteVideo` provides RoboCasa's public MP4 URL.

Each task also has a **Training demo** entry with its dataset source, instruction and original playback rate. There are 406 reference videos: all 40 LIBERO tasks, all 50 RoboTwin tasks, and 316 RoboCasa tasks. The other 49 RoboCasa tasks display an explicit unavailable state because their released training data contains no matching demonstration. See [training sources and export details](TRAINING_DEMOS.md). Demo videos have their own share links and do not contribute to the evaluation counts above.

## Videos and local preview

LIBERO and RoboTwin MP4s and all JPEG posters are stored in the repository. All 365 RoboCasa presentation MP4s are also kept locally under `media/robocasa/` in the export checkout, but are ignored by Git. Public RoboCasa videos are assets of the [same-repository Release](https://github.com/tianqi-zh/robot-agent-gallery/releases/tag/robocasa365-20260918). Pages stages the existing 450 MP4s, all posters and the catalog, and uses those Release URLs for RoboCasa playback and downloads.

For a fresh clone, verify the published Release and preview the staged website:

```bash
python3 scripts/validate_gallery.py --require-robocasa --release-media
python3 scripts/build_site.py
python3 -m http.server 8080 --directory _site
```

Open [localhost:8080](http://localhost:8080/). The website is static and requires no model access or API key. The staged preview uses public network access for RoboCasa videos. To serve the repository root with `python3 -m http.server 8080`, first download the RoboCasa MP4 assets into `media/robocasa/` or reproduce the full local export; the root page uses local video paths.

## Validate

With all 815 MP4s present locally:

```bash
python3 scripts/validate_gallery.py --require-robocasa
python3 scripts/validate_gallery.py --require-robocasa --videos
```

The first command checks the complete task matrix, native results, CSV, public metadata, media hashes and size limits. The second also uses `ffprobe` to verify every video against its frame and encoding metadata.

Add `--require-demos` to require the task demonstration catalog. When the catalog is present, both validation modes include its available videos and explicit missing-source entries. Pages requires this catalog and includes the training videos locally.

With Release-hosted RoboCasa media:

```bash
python3 scripts/release_media.py --check
python3 scripts/validate_gallery.py --require-robocasa --release-media
```

These commands check the public asset registry's exact names, SHA256 digests, sizes, upload state and URLs. The validator still checks any local RoboCasa MP4s that are present. Adding `--videos` to Release-media validation probes the remote RoboCasa videos as well and requires network access.

The browser check exercises task groups, filters, episode switching, actual playback, share links, history navigation and mobile layouts. With a local server running:

```bash
npm ci
npx playwright install chromium
npm run test:browser
```

Pass a different website URL after `--` to check a deployment. Screenshots are saved under the ignored `artifacts/browser/` directory. Node dependencies are only needed for this check.

The export contains task descriptions, results and provenance fingerprints. It excludes raw model reasoning, credentials, private logs and source-machine paths. Public checks do not replace the private source audit; see [METHODOLOGY.md](METHODOLOGY.md).

## Publish to GitHub Pages

[The Pages workflow](.github/workflows/pages.yml) runs on pushes to `main` or manual dispatch. It requires the complete 815-episode catalog and runs `validate_gallery.py --require-robocasa --release-media` before staging `_site/`. Full video decoding and browser checks are separate verification steps. The repository's **Settings → Pages → Source** uses **GitHub Actions**.

The release tag must point to the final validated gallery commit. Finish the full local export, verification and documentation, create that commit, and push only its `robocasa365-20260918` tag first. Verify the remote tag's peeled commit SHA, upload and publish the verified videos, then check the public Release before pushing the same commit to `main`. A tag-only push does not trigger this Pages workflow. See [ROBOCASA_IMPORT.md](ROBOCASA_IMPORT.md) for the complete commands and resume behavior.

## Files and rebuilding

- `index.html`, `app.js`, `styles.css`: static interface.
- `data/gallery.json` and `data/episodes.csv`: the complete task and episode catalog.
- `data/task-demos.json`, `media/demos/`: training demonstration mappings, videos and posters.
- `data/export-report.json`: source selections, exclusion provenance and media fingerprints.
- `media/libero/`, `media/robotwin/`, `media/robocasa/`: presentation media; RoboCasa MP4s are local/Release assets and its posters are tracked.
- `scripts/export_gallery.py`, `scripts/robocasa_export.py`: source selection and export.
- `scripts/export_training_demos.py`, `scripts/export_robocasa_demos.py`, `scripts/assemble_training_demos.py`: training-video export and catalog assembly.
- `scripts/validate_gallery.py`, `scripts/release_media.py`, `scripts/build_site.py`: verification, Release handling and Pages staging.
- [METHODOLOGY.md](METHODOLOGY.md): protocol, native scoring, recovery and limitations.

Rebuilding requires Python 3.10+, FFmpeg/ffprobe and the private original evaluation runs, including every registered RoboCasa recovery run and its complete collection audit. Follow [ROBOCASA_IMPORT.md](ROBOCASA_IMPORT.md); the exporter reads existing recordings and does not call a model or start new episodes. The public gallery alone does not include the private evidence needed to repeat the source audit.
