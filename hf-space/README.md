---
title: BenchMend · LIBERO Gallery
emoji: 🛠️
colorFrom: green
colorTo: gray
sdk: static
app_file: index.html
pinned: true
short_description: Original and repaired instructions, episode by episode.
---

# BenchMend: LIBERO gallery

**Agent-Guided Instruction Repair for Robotics Benchmarks.**

Browse 400 original-instruction LIBERO evaluations and 110 additional evaluations
after instruction repair (90 in revision 1, 20 in revision 2). Video files and
episode metadata live in the separate [benchmend/libero dataset](https://huggingface.co/datasets/benchmend/libero).

The **Final evaluation** view combines 310 unchanged original episodes, 70
revision-1 episodes, and 20 revision-2 episodes. It contains 400 evaluations;
it does not represent 400 additional rollouts. Native success is the result
of the benchmark's original checker, which was not modified.

The static app uses `episodes.json` for browsing and `media-hosting.js` to pin
video and poster URLs to an immutable dataset revision. It has no backend,
tracking, third-party fonts, or package dependencies at runtime. Host this
directory with any static HTTP server to preview it locally.

Features: version, suite, outcome and text filters; per-task episode selectors;
native video controls; original/revised instruction comparison with edits in
bold; same-initial-state version switching; shareable episode links; downloads;
and responsive keyboard-accessible dialogs.
