# Agent as Policy

**Small instruction edits. Better-aligned benchmarks.** The [essay](https://tianqi-zh.github.io/robot-agent-gallery/) uses GPT as a proxy for a human robot operator to diagnose instruction–evaluator mismatches in LIBERO and RoboTwin. It explains the motivation, evaluation method, instruction repairs and results, remaining difficulties, and implications for reusing existing demonstrations. This GitHub repository contains the essay, its local example videos and posters, analysis data, and validation tools.

**[BenchMend gallery](https://huggingface.co/spaces/benchmend/gallery)** · [LIBERO Dataset](https://huggingface.co/datasets/benchmend/libero)

The BenchMend collection contains **400 original-instruction LIBERO evaluations and one 90-episode revision**. The revision keeps 70 recordings from the first repair run and replaces the two further-refined tasks (`libero_goal_t05` and `libero_10_t05`) with their 20 second-run recordings. All 490 selected videos are retained byte-for-byte, with instructions, native outcomes, matched initial states, provenance hashes, and preview images. Its [LIBERO page](https://benchmend-gallery.static.hf.space/gallery/libero/index.html) offers Original and Revision views with suite, outcome, and text filters, playback, and instruction comparisons. The article’s final 400-episode comparison combines 310 unchanged originals with the 90 revision episodes. The shared Space also preserves the contributor’s RoboTwin Before (482 videos) and V4 (182 videos) collections. See [the LIBERO app source](hf-space/README.md), [shared Space maintenance notes](hf-space/SHARED_SPACE.md), and [exporter](scripts/export_benchmend_libero.py).

**Historical multi-benchmark archive:** [Gallery](https://huggingface.co/spaces/Alan0928/robot-agent-gallery) · [Video Dataset](https://huggingface.co/datasets/Alan0928/robot-agent-gallery) · [Gallery source](https://huggingface.co/spaces/Alan0928/robot-agent-gallery/tree/main)

The historical Hugging Face Space hosts the multi-benchmark gallery interface and export tools. Its companion Dataset stores evaluation recordings, training demonstrations, posters, and archived metadata; the Space streams them directly. Its four archived collections contain **1,286 playable scored episodes from 497 task entries**:

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

Open http://localhost:8080/. The essay's 22 video players (the overview and 21 episode examples) load recordings from this repository and work without access to Hugging Face. No model API or credentials are needed. Existing `/gallery/` routes and historical episode/demo links forward to the Space while preserving query parameters and fragments.

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

The browser check decodes all 22 embedded local videos with HF media requests blocked, and covers evidence tables, mobile layouts, HF gallery links, and legacy redirects. The build stages the essay, public evidence, the 52 video/poster files retained in its evidence catalog plus the overview video and poster (about 31.5 MB total), and forwarding pages. Unrelated gallery media and the gallery application are excluded.

GitHub Pages is configured to publish the repository root from `robotwin-blog-copy-20260922`; pushing to that branch updates the public essay through GitHub's branch-based Pages build. The checked-in staging workflow is separate from that deployment setting. The standalone Space and media Dataset are updated separately in their HF repositories.

## Reproduce the BenchMend LIBERO Dataset and app

The exporter reads the three archived evaluation runs without modifying them. It checks every selected result against the audited article data, copies the original video bytes, fully decodes each recording, and generates posters and public metadata. Keep the Dataset output outside this Git repository.

```bash
python3 scripts/export_benchmend_libero.py --runs /path/to/robot-agent/eval_runs --output /path/to/benchmend-libero
python3 scripts/publish_benchmend.py --dataset-root /path/to/benchmend-libero --validate-only
```

The source in `hf-space/` is the standalone LIBERO app. The live shared Space hosts it under `gallery/libero/` alongside the contributor's RoboTwin pages. Videos remain in their respective HF repositories; existing article example videos are independent of the Space.

`scripts/publish_benchmend.py` supports a new or existing standalone LIBERO Space, with HF authentication and hash verification. It now refuses to publish over a Space containing other contributors' files, before any remote changes. Maintain `benchmend/gallery` with targeted changes against its latest revision as described in [the shared Space notes](hf-space/SHARED_SPACE.md).

## Render the presentation video

To render the silent 16:9 presentation video, install the browser dependencies above and FFmpeg, then run:

```bash
python3 scripts/build_blog_video.py --output artifacts/video/blog-showcase-v2.mp4
```

The output is `artifacts/video/blog-showcase-v2.mp4` (1080p, 30 fps, approximately 105 seconds, no audio or subtitle track). Two LIBERO cases play the complete original recording on the left before revealing the revised instruction and recording on the right. Added words are bold; playback is labeled 2×. LIBERO and RoboTwin each have a separate results page using the blog’s before/after judgment matrices, followed by the three core takeaways on page five. The generated manifest records source hashes and scene timings; slide HTML and PNGs are retained alongside the video for editing.

The article embeds a copy at `media/blog/overview/blog-showcase-v2.mp4` with a 16:9 poster, playback controls, and a download link. It loads only when the reader plays it.

## Evidence and methods

- [LIBERO accounting and audit methods](LIBERO_ALIGNMENT.md)
- [Evaluation methodology](METHODOLOGY.md)
- [LIBERO alignment data](data/libero-alignment.json), [episode records](data/libero-alignment-episodes.csv), [reviewed labels](data/libero-human-review.json), and [clip provenance](data/libero-blog-media.json)
- [RoboTwin alignment summary](data/robotwin-alignment-summary.json)
- [Verbatim RoboTwin instruction comparisons and source provenance](data/robotwin-instruction-examples.json)

Only the article’s overview and evidence videos and posters remain in this branch; the full gallery archive lives on HF. Existing Git history and the historical RoboCasa GitHub Release remain available; the migration does not rewrite history.
