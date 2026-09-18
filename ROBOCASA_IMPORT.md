# Importing the RoboCasa365 evaluation

This guide rebuilds and publishes the complete 815-episode catalog: the existing 450 LIBERO/RoboTwin episodes and all 365 RoboCasa365 episodes. A strict final collection audit is required before export; partial collections and synthetic fixtures are not publishable. See [METHODOLOGY.md](METHODOLOGY.md) for the actual native outcomes, recovery seeds and limitations.

RoboCasa365 adds 65 atomic and 300 composite tasks, each with one episode. Successes, policy failures and policy timeouts are all retained. Only documented infrastructure failures and invalid scenes that already satisfy the task before any policy action are excluded. A completed collection audit selects the exact source run, seed and attempt for every task and binds the source videos and results to SHA256 fingerprints. The final report must have `passed`, `scope_complete` and `full_goal_complete` all true, `scope=all_365_tasks`, `allow_partial=false`, 365 valid episodes, and no unresolved tasks or audit issues. A legacy single-run report or partial collection report is insufficient for this export.

## Prepare the complete local export

After evaluation, infrastructure recovery and the full collection audit finish:

```bash
python3 scripts/export_gallery.py \
  --source-root ../robot-agent/eval_runs \
  --robocasa-audit ../robot-agent/eval_runs/robocasa365_astra_firstpass_20260918/reports/final_collection_audit.json \
  --plan-only

python3 scripts/export_gallery.py \
  --source-root ../robot-agent/eval_runs \
  --robocasa-audit ../robot-agent/eval_runs/robocasa365_astra_firstpass_20260918/reports/final_collection_audit.json \
  --jobs 4

python3 scripts/validate_gallery.py --require-robocasa --videos
```

`--plan-only` checks selection without writing metadata or media. The real export resumes from verified encoding-cache entries. Original LIBERO and RoboTwin video files retain their previous encoding and hashes. RoboCasa presentation copies preserve all source frames, their order, 20 FPS, the original 1536 × 512 dimensions and the three camera panels. They use H.264/yuv420p/faststart, with CRF 26, a 2 Mbps maximum rate and a 4 Mbit encoder buffer. These are presentation copies; source recordings remain unchanged in the evaluation directory.

The complete catalog has 455 tasks and 815 episodes across three benchmarks. RoboCasa outcomes are never combined into a pooled success rate with LIBERO or RoboTwin. Per-benchmark evaluation dates remain September 17 and September 18, 2026.

## Local files and website delivery

All 365 RoboCasa MP4 files are saved locally under `media/robocasa/`, alongside their JPEG posters. The MP4s are ignored by Git and distributed as assets of this same repository's `robocasa365-20260918` release. Posters, metadata and website code are committed normally. A fresh clone can obtain the MP4 files from that release or reproduce the export from the private audited sources.

This separation keeps the Pages website below its size limit while preserving the full recordings. Local serving uses the MP4 files in the checkout. `build_site.py` stages the catalog, all posters, and the existing LIBERO/RoboTwin videos, and configures RoboCasa playback to use its declared release URLs. Both the player and the MP4 download button use the same source. The CSV keeps the local `video` path and adds `remoteVideo` for RoboCasa's public download URL.

Release creation and publication are explicit operations in `scripts/release_media.py`. Prepare and verify all assets before publishing the release or pushing the completed site. The release helper supports resuming an upload, skips assets with identical SHA256 and size, and rejects conflicting assets instead of overwriting them. Its upload and publication checks require the final private collection audit; its public check only needs the exported report and the released asset registry.

The Pages workflow requires the complete 815-episode export and validates all 365 release assets against their recorded SHA256 digests, sizes and exact URLs. When local RoboCasa MP4s are present, the validator checks those bytes too. Source-machine paths, authentication data, model conversations and raw logs are not part of the public export.

## Release tag and publication order

Complete the full collection audit, the real 815-episode export, local video validation, local browser checks and final documentation before creating the reviewed gallery commit `X`. Keep the RoboCasa presentation MP4s local and ignored; commit the exported metadata, posters, code and documentation. Record the full commit SHA and keep that reviewed commit fixed throughout publication.

1. Create `robocasa365-20260918` at `X` and push **only that tag**. Verify the remote tag's peeled commit SHA equals `X`. Do not push `main` yet.
2. Use the unchanged release helper to create/resume the draft and upload all 365 verified videos. Then run its explicit publication command; it rechecks the final collection, local files and complete remote asset set.
3. Run anonymous verification of the published Release and the gallery's Release-media validation. Preview the staged page using the real released videos.
4. Push the same commit `X` to `main`. Wait for Pages deployment, then check the public site and actual playback with the browser smoke test.

The helper currently creates drafts with `--target main`. An existing **remote** tag is retained, so that option does not change the pre-pushed tag. Without this tag-first step, publishing while `main` still contains the older 450-episode code would associate the release with that older code. This behavior follows [GitHub's release API](https://docs.github.com/en/rest/releases/releases#create-a-release) and [gh 2.45's implementation](https://github.com/cli/cli/blob/v2.45.0/pkg/cmd/release/create/create.go). The Pages workflow matches pushes to `main`, so a tag-only push does not trigger it; see [GitHub's branch/tag filter rules](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushbranchestagsbranches-ignoretags-ignore).

After creating the reviewed local commit, use these commands from this repository. Inspect both local and remote commit SHAs before continuing; a conflicting existing tag must not be overwritten.

```bash
GALLERY_FINAL_COMMIT=$(git rev-parse HEAD)
git tag -a robocasa365-20260918 "$GALLERY_FINAL_COMMIT" -m "RoboCasa365 audited gallery videos"
git push origin refs/tags/robocasa365-20260918
git rev-parse 'robocasa365-20260918^{commit}'
git ls-remote origin 'refs/tags/robocasa365-20260918' 'refs/tags/robocasa365-20260918^{}'
```

For this annotated tag, the remote `^{}` line must equal `GALLERY_FINAL_COMMIT`. If resuming after the tag was pushed, compare these identities and reuse the existing matching tag rather than creating or force-updating it. Then:

```bash
python3 scripts/release_media.py --upload-draft \
  --collection-audit ../robot-agent/eval_runs/robocasa365_astra_firstpass_20260918/reports/final_collection_audit.json \
  --source-root ../robot-agent/eval_runs

python3 scripts/release_media.py --publish \
  --collection-audit ../robot-agent/eval_runs/robocasa365_astra_firstpass_20260918/reports/final_collection_audit.json \
  --source-root ../robot-agent/eval_runs

python3 scripts/release_media.py --check
python3 scripts/validate_gallery.py --require-robocasa --release-media
python3 scripts/build_site.py
python3 -m http.server 8080 --directory _site
```

The public release check reads the anonymous API and validates all 365 digests, sizes and exact URLs. With the staged server running, run `npm run test:browser` in another terminal to verify Release-backed playback. Serving the repository root instead uses local MP4s; a fresh clone needs those files downloaded from the Release or the staged preview shown above. `--release-media --videos` also probes remote RoboCasa videos and is not an offline check.

After those checks pass, publish the fixed commit to `main` without force:

```bash
git push origin "${GALLERY_FINAL_COMMIT}:refs/heads/main"
```

Wait for the Pages workflow, then check the actual deployed site:

```bash
npm run test:browser -- https://tianqi-zh.github.io/robot-agent-gallery/
```

Local synthetic tests only exercise code paths; they are never a substitute for the completed source audit, full media validation or actual published playback. Release publication and tag push alone do not establish that Pages has deployed the new catalog.
