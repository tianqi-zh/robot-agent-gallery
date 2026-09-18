# Robot Agent Gallery

Browse every scored episode from two coding-agent robot evaluations, including failures. The policy uses `gpt-6-astra` with `high` reasoning and controls the robot from RGB images, robot proprioception, and calibration.

**Website:** [tianqi-zh.github.io/robot-agent-gallery](https://tianqi-zh.github.io/robot-agent-gallery/)

| Evaluation | Tasks | Episodes | Successes | Failures | Success rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| LIBERO v5 r4 | 40 | 400 | 322 | 78 | 80.5% |
| RoboTwin first pass | 50 | 50 | 36 | 14 | 72.0% |

LIBERO suite results are Spatial 95/100, Goal 79/100, Object 89/100, and LIBERO-10 59/100. RoboTwin's failures include one timeout. These evaluations use different tasks, controls, and budgets; their rates are not directly comparable. RoboTwin has only one sampled episode per task.

Videos are compressed presentation copies that retain every recorded frame. LIBERO plays at 20 FPS and includes initialization and warmup. RoboTwin plays at 10 FPS with one frame after each native action; its playback is not physical elapsed time. Read [METHODOLOGY.md](METHODOLOGY.md) for selection, scoring, and limitations.

## Browse and share

Open [LIBERO](https://tianqi-zh.github.io/robot-agent-gallery/#benchmark=libero) or [RoboTwin](https://tianqi-zh.github.io/robot-agent-gallery/#benchmark=robotwin), then:

1. Choose a LIBERO suite, search task names or instructions, and filter tasks by **With failures** or **All successful**. Sort by success rate to explore results.
2. Open a task or numbered episode. Each LIBERO task has all 10 episodes; each RoboTwin task has one. The player shows the native outcome, instruction, seed, steps, and recorded camera views.
3. Use **Copy episode link** to share the selected task and episode, or **Download MP4** to save its video. For example: [RoboTwin, stack three blocks, episode 1](https://tianqi-zh.github.io/robot-agent-gallery/#benchmark=robotwin&task=robotwin_stack_blocks_three&episode=stack_blocks_three_r00).

Outcome filters select tasks; they retain every episode within each matching task, including unsuccessful episodes. The complete episode table is available as [CSV](data/episodes.csv).

## Run locally

From this repository:

```bash
python3 -m http.server 8080
```

Open [localhost:8080](http://localhost:8080/). The site is static and requires no API key, model access, or server application.

## Validate

```bash
python3 scripts/validate_gallery.py
python3 scripts/validate_gallery.py --videos
```

The first command checks completeness, results, public metadata, media references, and size limits. The second also uses `ffprobe` to verify every video against its exported frame and encoding metadata.

The optional browser check exercises task filters, episode switching, actual playback, share links, history navigation, and mobile layouts. With the local server running:

```bash
npm ci
npx playwright install chromium
npm run test:browser
```

Pass a different website URL after `--` to check a deployment. Screenshots are saved under the ignored `artifacts/browser/` directory. Node dependencies are only needed for this check; the website itself has none.

The gallery exports contain task descriptions, episode results, provenance fingerprints, and local presentation assets. They exclude raw model reasoning, credentials, private logs, and source-machine paths. See [METHODOLOGY.md](METHODOLOGY.md) for what can be verified from this public export.

## Publish to GitHub Pages

[The Pages workflow](.github/workflows/pages.yml) runs on every push to `main`, or manually from **Actions → Deploy evaluation gallery → Run workflow**. It runs the default Python validator, stages the public site with `scripts/build_site.py`, uploads `_site/`, and deploys to the website linked above. Full video decoding and browser checks are separate local checks.

The repository's **Settings → Pages → Source** uses **GitHub Actions**. No model credentials or frontend build dependencies are needed for deployment.

## Files and rebuilding

- `index.html`, `app.js`, `styles.css`: the static gallery interface.
- `data/gallery.json`: task and episode metadata used by the interface.
- `data/episodes.csv`: the same selected episodes in tabular form.
- `data/export-report.json`: source-selection fingerprints and media validation metadata.
- `media/libero/`, `media/robotwin/`: compressed MP4 videos and JPEG posters.
- `scripts/`: export, validation, and publication staging tools.
- `.github/workflows/pages.yml`: GitHub Pages deployment.

Rebuilding the export requires Python 3.10+, `ffmpeg`, `ffprobe`, and access to both original evaluation run directories. For a sibling source checkout containing those runs:

```bash
python3 scripts/export_gallery.py --source-root ../robot-agent/eval_runs --jobs 6
python3 scripts/validate_gallery.py --videos
python3 scripts/build_site.py
```

The exporter reads existing results and recordings; it does not call a model or run new evaluations. `build_site.py` stages only the public website files in `_site/`. GitHub Pages uses that directory as its deployment artifact. The public gallery alone does not contain the private source runs needed to repeat the export.
