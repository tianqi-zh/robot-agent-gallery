# Agent as Policy

The [essay](https://tianqi-zh.github.io/robot-agent-gallery/) examines whether robot benchmark instructions communicate the goals their evaluators expect. This GitHub repository contains the essay, analysis data, and validation tools.

**[Open the video gallery on Hugging Face](https://huggingface.co/spaces/Alan0928/robot-agent-gallery)** · [Video Dataset](https://huggingface.co/datasets/Alan0928/robot-agent-gallery) · [Gallery source](https://huggingface.co/spaces/Alan0928/robot-agent-gallery/tree/main)

The standalone Hugging Face Space hosts the gallery interface and export tools. Its companion Dataset stores all evaluation recordings, training demonstrations, posters, and archived metadata; the Space streams them directly. This keeps the interface within the Space repository’s 1 GB limit. Its four current collections contain **1,286 playable scored episodes from 497 task entries**:

| Collection | Gallery | Tasks | Episodes |
| --- | --- | ---: | ---: |
| LIBERO | [Browse](https://alan0928-robot-agent-gallery.static.hf.space/gallery/libero/index.html) | 40 | 400 |
| Robotwin | [Browse](https://alan0928-robot-agent-gallery.static.hf.space/gallery/robotwin/index.html) | 50 | 479 |
| RoboCasa365 | [Browse](https://alan0928-robot-agent-gallery.static.hf.space/gallery/robocasa/index.html) | 365 | 365 |
| RoboDojo | [Browse](https://alan0928-robot-agent-gallery.static.hf.space/gallery/robodojo/index.html) | 42 | 42 |

The HF archive also preserves the 50 older Robotwin episodes, 490 training reference videos (including 50 archived Robotwin demonstrations), and nine additional diagnostic recordings: **1,835 MP4 files** in total. Current gallery evaluation totals exclude training demonstrations and diagnostic recordings.

## Preview the essay

```bash
python3 -m http.server 8080
```

Open http://localhost:8080/. Video playback needs network access to Hugging Face; no model API or credentials are needed. The essay's 26 video players load the same recordings from HF. Existing `/gallery/` routes and historical episode/demo links forward to the Space while preserving query parameters and fragments.

[gallery-hosting.json](gallery-hosting.json) configures the Space and media URLs. The media URL is pinned to a verified HF Dataset commit so future gallery updates do not silently change the essay's recordings. To adopt a new media revision, update this configuration and rerun validation.

## Validate and publish

```bash
python3 scripts/validate_libero_blog.py
python3 scripts/review_libero_alignment.py --check --require-complete
python3 scripts/build_site.py
python3 -m http.server 8080 --directory _site
```

The media validator downloads the 18 LIBERO evidence clips and their posters into an ignored cache, then verifies their recorded sizes and SHA256 hashes. For offline validation against a local Dataset checkout:

```bash
python3 scripts/validate_libero_blog.py --media-root /path/to/robot-agent-gallery-media
```

For tests and browser checks:

```bash
python3 -m pytest -q
npm ci
npx playwright install chromium
npm run test:blog
```

The browser check covers all 26 players, evidence tables, mobile layouts, HF links, and legacy redirects. The Pages build stages only the essay, public evidence, visual assets, and forwarding pages. It contains no gallery application or video files.

A push to `main` triggers the [Pages workflow](.github/workflows/pages.yml). Work on another branch does not publish the site. The standalone Space and media Dataset are updated separately in their HF repositories.

## Evidence and methods

- [LIBERO accounting and audit methods](LIBERO_ALIGNMENT.md)
- [Evaluation methodology](METHODOLOGY.md)
- [LIBERO alignment data](data/libero-alignment.json), [episode records](data/libero-alignment-episodes.csv), [reviewed labels](data/libero-human-review.json), and [clip provenance](data/libero-blog-media.json)
- [RoboTwin alignment summary](data/robotwin-alignment-summary.json)

The migration removes media from this branch's current file tree. Existing Git history and the historical RoboCasa GitHub Release remain available; the migration does not rewrite history.
