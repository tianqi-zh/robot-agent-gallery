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

Browse **490 LIBERO videos**: 400 original-instruction evaluations and 90
evaluations with revised instructions. The **Revision** collection uses the
latest instruction for each of nine tasks, with the same 10 initial states per
task as the original evaluation. Video files and
episode metadata live in the separate [benchmend/libero dataset](https://huggingface.co/datasets/benchmend/libero).

Each revised task has one public revision. Native success is the result of the
benchmark's original checker, which was not modified.

The static app uses `episodes.json` for browsing and `media-hosting.js` to pin
video and poster URLs to an immutable dataset revision. It has no backend,
tracking, third-party fonts, or package dependencies at runtime. Host this
directory with any static HTTP server to preview it locally.

Features: version, suite, outcome and text filters; per-task episode selectors;
native video controls; original/revised instruction comparison with edits in
bold; same-initial-state version switching; shareable episode links; downloads;
and responsive keyboard-accessible dialogs.
