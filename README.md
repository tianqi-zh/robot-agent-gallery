# Robot Agent Gallery

Browse every scored episode from two coding-agent robot evaluations, including failures. The policy uses `gpt-6-astra` with `high` reasoning and controls the robot from RGB images, robot proprioception, and calibration.

**Website:** [tianqi-zh.github.io/robot-agent-gallery](https://tianqi-zh.github.io/robot-agent-gallery/)

| Evaluation | Tasks | Episodes | Successes | Failures | Success rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| LIBERO v5 r4 | 40 | 400 | 322 | 78 | 80.5% |
| RoboTwin first pass | 50 | 50 | 36 | 14 | 72.0% |

LIBERO suite results are Spatial 95/100, Goal 79/100, Object 89/100, and LIBERO-10 59/100. RoboTwin's failures include one timeout. These evaluations use different tasks, controls, and budgets; their rates are not directly comparable. RoboTwin has only one sampled episode per task.

Videos are compressed presentation copies that retain every recorded frame. LIBERO plays at 20 FPS and includes initialization and warmup. RoboTwin plays at 10 FPS with one frame after each native action; its playback is not physical elapsed time. Read [METHODOLOGY.md](METHODOLOGY.md) for selection, scoring, and limitations.

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
npm install
npx playwright install chromium
npm run test:browser
```

Pass a different website URL after `--` to check a deployment. Screenshots are saved under the ignored `artifacts/browser/` directory. Node dependencies are only needed for this check; the website itself has none.

The gallery exports contain task descriptions, episode results, provenance fingerprints, and local presentation assets. They exclude raw model reasoning, credentials, private logs, and source-machine paths. See [METHODOLOGY.md](METHODOLOGY.md) for what can be verified from this public export.

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
