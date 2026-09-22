# Agent as Policy

The [homepage](https://tianqi-zh.github.io/robot-agent-gallery/) asks whether LIBERO’s instructions communicate the goals its evaluator expects. GPT-6 serves as a proxy for a human robot operator, acting from the instruction and live observations without access to demonstration videos or success-checker code. Paired recordings and public evidence document the instruction revisions and their outcomes.

The [gallery](https://tianqi-zh.github.io/robot-agent-gallery/gallery/) presents **1,286 playable scored episodes from 497 task entries across four current collections**. Each benchmark has its own page:

| Collection | Route | Experiment date | Tasks | Episodes | Successes | Failures, including timeouts | Success rate |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| LIBERO v5 r4 | [/gallery/libero/](https://tianqi-zh.github.io/robot-agent-gallery/gallery/libero/) | 2026-09-17 | 40 | 400 | 322 | 78 | 80.5% |
| Robotwin | [/gallery/robotwin/](https://tianqi-zh.github.io/robot-agent-gallery/gallery/robotwin/) | 2026-09-22 | 50 | 479 | 396 | 83 | 82.67% |
| RoboCasa365 | [/gallery/robocasa/](https://tianqi-zh.github.io/robot-agent-gallery/gallery/robocasa/) | 2026-09-18 | 365 | 365 | 165 | 200 | 45.2% |
| RoboDojo | [/gallery/robodojo/](https://tianqi-zh.github.io/robot-agent-gallery/gallery/robodojo/) | 2026-09-19 | 42 | 42 | 6 | 36 | 14.29% |

**Robotwin is the newer 10-rollout collection only**, internally identified as `robotwin_nvidia10`. It publishes 479 playable scored episodes from 500 planned rollouts in the local goal-spec rerun; 21 planned rollouts did not yield a playable scored episode. The older 50-episode first-pass collection has no gallery entry, selector, search results or task cards. `/gallery/robotwin_nvidia10/` redirects to `/gallery/robotwin/`.

The historical source archive remains intact: [gallery.json](data/gallery.json), [episodes.csv](data/episodes.csv), the export report and media retain **1,336 episodes and 547 task entries**, including the older 50 Robotwin episodes. **Download source CSV** deliberately downloads that complete archive, so its row count differs from the current gallery. The essay's diagnostic rerun clips are separate from both gallery evaluation totals.

LIBERO suite results are Spatial 95/100, Goal 79/100, Object 89/100 and LIBERO-10 59/100. RoboCasa includes 65 atomic tasks (28 successes) and 300 composite tasks (137 successes), with two timeouts. RoboDojo has zero timeouts and zero infrastructure errors. Different tasks, controls and budgets prevent direct comparison or a pooled success rate.

Success is the benchmark's native score. It is separate from the policy's written assessment or an independent visual judgment. The [methodology](METHODOLOGY.md) explains the protocols, the known StackCans criterion limitation and exclusion of invalid initial scenes. Each policy requests `gpt-6-astra` with `high` reasoning and controls the robot from RGB images and robot proprioception. Calibration inputs depend on the benchmark; RoboDojo receives no camera calibration.

## Local preview and browsing

With the full local media export present:

```bash
python3 -m http.server 8080
```

Open the [essay](http://localhost:8080/), [gallery overview](http://localhost:8080/gallery/) or a benchmark page such as [Robotwin](http://localhost:8080/gallery/robotwin/). The static site requires no model access or API key. The same routes and media links work under a GitHub Pages project prefix.

1. Select a benchmark, then choose a suite or task group, search names or instructions, and filter by **With failures** or **All successful**. Filters select tasks and retain all episodes within matching tasks.
2. Open a task or episode. LIBERO has ten episodes per task; Robotwin has up to ten; RoboCasa and RoboDojo have one. The player shows native outcome, instruction, seed, action count and camera views.
3. Switch between agent episodes and training demonstrations, use **Copy episode link** or **Copy demo link**, or download the selected MP4.

Legacy `#benchmark=…&task=…&episode=…` and `view=demo` links remain supported. Root links open the corresponding gallery page. Historical Robotwin episode identifiers display a missing-recording notice instead of being relabeled as newer episodes.

The current four collections offer 440 training reference videos: 40 LIBERO, 50 Robotwin, 316 RoboCasa and 34 RoboDojo. The other 49 RoboCasa tasks and eight RoboDojo Open tasks display an explicit unavailable state. The archived training catalog has records for all 547 task entries, including the older Robotwin collection. See [training sources and export details](TRAINING_DEMOS.md). Demonstrations never contribute to evaluation counts.

## Media and playback

Videos are compressed presentation copies retaining every recorded frame. LIBERO plays at 20 FPS, including initialization and warmup. Robotwin plays at 10 FPS, with an initial frame and one frame after each native action. RoboCasa plays at 20 FPS across three views. RoboDojo plays at 25 FPS in a 1920 × 480 head/left-wrist/right-wrist panel. Thinking and transport delays are omitted; playback duration is not evaluation wall time.

LIBERO, both Robotwin exports, RoboDojo and all JPEG posters are stored in the repository. The 365 RoboCasa evaluation MP4s are available locally under `media/robocasa/` in the export checkout but ignored by Git; their public copies are assets of the existing [same-repository Release](https://github.com/tianqi-zh/robot-agent-gallery/releases/tag/robocasa365-20260918). Training videos remain local site assets.

The essay’s 2×2 tables distinguish **the agent’s judgment of completion** from **the benchmark’s verdict**. Every outcome the benchmark judges successful is counted as complete on the agent side; `\` marks the reverse combination as inapplicable under this rule. For outcomes the benchmark judges failures, retained completion claims count as “agent considers complete”; rejected claims and episodes without a completion claim count as “agent does not consider complete.” All disputed claims were manually checked against the instruction; the only correction is recorded in [libero-human-review.json](data/libero-human-review.json). Downloadable source data retain original finish records. See [the accounting rules](LIBERO_ALIGNMENT.md).

The essay reuses some baseline LIBERO media and adds explicitly cataloged clips under `media/blog/`. [libero-blog-media.json](data/libero-blog-media.json) records their selection, sources and fingerprints. These illustrative examples are purposefully selected diagnostic cases, not a random sample or a held-out causal estimate.

A fresh clone can stage the site with RoboCasa Release playback:

```bash
python3 scripts/validate_gallery.py --require-robocasa --require-robodojo --require-demos --release-media
python3 scripts/validate_libero_blog.py
python3 scripts/review_libero_alignment.py --check --require-complete
python3 scripts/build_site.py
python3 -m http.server 8080 --directory _site
```

The build copies the essay, nested gallery pages and declared public assets, and enables Release playback on every gallery page. The staged preview needs network access for RoboCasa videos. Serving the checkout directly uses local MP4 paths, so a fresh clone needs those RoboCasa files downloaded or reproduced from the audited source.

## Validation

With the complete local evaluation and training media present:

```bash
python3 scripts/validate_gallery.py --require-robocasa --require-robodojo --require-demos
python3 scripts/validate_gallery.py --require-robocasa --require-robodojo --require-demos --videos
python3 scripts/validate_libero_blog.py
python3 scripts/review_libero_alignment.py --check --require-complete
python3 scripts/validate_libero_blog.py --probe
python3 -m pytest -q
```

The gallery validator checks the entire historical archive: task matrices, native results, CSV, public metadata, media hashes, demo coverage and size limits. `--videos` also probes evaluation and training videos with `ffprobe`. Blog clips join the media inventory only through explicit video/poster references in a complete `libero-blog-media.json`; missing, unsafe or unlisted assets remain errors. The separate essay validator checks its evidence and clip fingerprints, and `--probe` decodes all selected essay videos to check frame counts.

Existing RoboCasa Release checks remain available with `python3 scripts/release_media.py --check` and the gallery validator's `--release-media` option. They verify public asset names, SHA256 digests, sizes, upload state and URLs. Local RoboCasa files are checked when present; `--release-media --videos` also probes remote videos.

Browser checks cover browsing, filtering, playback, demos, share links, history and mobile layouts:

```bash
npm ci
npx playwright install chromium
# With the local preview server already running:
npm run test:browser -- http://127.0.0.1:8080/gallery/
# Self-contained route check, including a simulated GitHub project prefix:
npm run test:routes
# Self-contained essay check: statistics, all 18 clips, mobile layout and legacy links:
npm run test:blog
# Check the staged release (including remote RoboCasa playback):
node scripts/test_gallery_routes.cjs _site
node scripts/smoke_blog.cjs _site
```

Browser screenshots are saved under ignored `artifacts/browser/`. Node dependencies are only needed for browser checks. The public export excludes raw model reasoning, credentials, private logs and source-machine paths; public checks do not replace the private source audit.

## Files, rebuilding and publication

- `index.html`, `blog.js`, `blog.css`: the English essay.
- `gallery/`, `app.js`, `styles.css`: gallery overview, benchmark routes and shared player.
- `data/gallery.json`, `data/episodes.csv`, `data/export-report.json`: complete historical evaluation archive and provenance.
- `data/task-demos.json`, `media/demos/`: training references and explicit unavailable records.
- `data/libero-alignment.json`, `data/libero-alignment-episodes.csv`, `data/libero-blog-media.json`, `data/libero-human-review.json`, `media/blog/`: essay evidence and selected recordings.
- `scripts/validate_gallery.py`, `scripts/validate_libero_blog.py`, `scripts/review_libero_alignment.py`, `scripts/release_media.py`, `scripts/build_site.py`: verification, existing Release handling and site staging.

Rebuilding evaluation exports requires Python 3.10+, FFmpeg/ffprobe and the private original runs. Earlier procedures and evidence are retained in [ROBOCASA_IMPORT.md](ROBOCASA_IMPORT.md), [ROBODOJO_IMPORT.md](ROBODOJO_IMPORT.md) and [TRAINING_DEMOS.md](TRAINING_DEMOS.md). Those records describe their historical import counts. Exporters read existing recordings; they do not call a model or start new episodes.

A push to `main` triggers the [Pages workflow](.github/workflows/pages.yml). A successful push does not establish a successful deployment: check the workflow result and the live routes afterward. The existing RoboCasa Release remains unchanged.
