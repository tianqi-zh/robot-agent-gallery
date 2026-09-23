# Agent as Policy

**Small instruction edits. Better-aligned benchmarks.** The [essay](https://tianqi-zh.github.io/robot-agent-gallery/) uses GPT as a proxy for a human robot operator to diagnose instruction–evaluator mismatches in LIBERO and RoboTwin. It explains the motivation, evaluation method, instruction repairs and results, remaining difficulties, and implications for reusing existing demonstrations. This GitHub repository contains the essay, its local example videos and posters, analysis data, and validation tools.

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

Open http://localhost:8080/. The essay's 21 video players load recordings from this repository and work without access to Hugging Face. No model API or credentials are needed. Existing `/gallery/` routes and historical episode/demo links forward to the Space while preserving query parameters and fragments.

[gallery-hosting.json](gallery-hosting.json) configures the Space and media URLs. The archive media URL is pinned to a verified HF Dataset commit and is retained for validation and recovering missing files. Article playback uses local media; adopting a new example requires updating the evidence catalog and local assets together.

## Validate and publish

```bash
python3 scripts/validate_libero_blog.py
python3 scripts/review_libero_alignment.py --check --require-complete
python3 scripts/build_site.py
python3 -m http.server 8080 --directory _site
```

The media validator verifies the 18 local LIBERO evidence clips and their posters against recorded sizes and SHA256 hashes. It can recover missing files from the pinned HF archive into an ignored cache. To validate directly against another local Dataset checkout:

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

The browser check decodes all 21 embedded local videos with HF media requests blocked, and covers evidence tables, mobile layouts, HF gallery links, and legacy redirects. The build stages the essay, public evidence, the 52 video/poster files retained in its evidence catalog (about 24.4 MB), and forwarding pages. Unrelated gallery media and the gallery application are excluded.

GitHub Pages is configured to publish the repository root from `robotwin-blog-copy-20260922`; pushing to that branch updates the public essay through GitHub's branch-based Pages build. The checked-in staging workflow is separate from that deployment setting. The standalone Space and media Dataset are updated separately in their HF repositories.

## Render the presentation video

To render the silent 16:9 presentation video, install the browser dependencies above and FFmpeg, then run:

```bash
python3 scripts/build_blog_video.py
```

The output is `artifacts/video/blog-showcase.mp4` (1080p, 30 fps, approximately 105 seconds, no audio or subtitle track). Two LIBERO cases play the complete original recording on the left before revealing the revised instruction and recording on the right. Added words are bold; playback is labeled 2×. LIBERO and RoboTwin each have a separate results page using the blog’s before/after judgment matrices, followed by the three core takeaways on page five. The generated manifest records source hashes and scene timings; slide HTML and PNGs are retained alongside the video for editing.

## Evidence and methods

- [LIBERO accounting and audit methods](LIBERO_ALIGNMENT.md)
- [Evaluation methodology](METHODOLOGY.md)
- [LIBERO alignment data](data/libero-alignment.json), [episode records](data/libero-alignment-episodes.csv), [reviewed labels](data/libero-human-review.json), and [clip provenance](data/libero-blog-media.json)
- [RoboTwin alignment summary](data/robotwin-alignment-summary.json)
- [Verbatim RoboTwin instruction comparisons and source provenance](data/robotwin-instruction-examples.json)

Only videos and posters in the article evidence catalog remain in this branch; the full gallery archive lives on HF. Existing Git history and the historical RoboCasa GitHub Release remain available; the migration does not rewrite history.
