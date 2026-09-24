# Shared BenchMend Space

The live [Space source](https://huggingface.co/spaces/benchmend/gallery/tree/main)
contains both the LIBERO app and a collaborator's RoboTwin gallery. This local
`hf-space/` directory remains the standalone LIBERO source; uploading it over the
Space root would replace the shared interface. The original publisher rejects
that operation before changing either remote repository.

The [playback repair](https://huggingface.co/spaces/benchmend/gallery/commit/600b54fc1c253ea2f61c9329da69577180fed016)
restored the LIBERO entry, corrected media routing, and recovered missing
comparison videos while preserving the contributor's latest catalogs.

## Current layout

- `gallery/libero/`: the standalone LIBERO app, 400 Original and 90 Revision
  episodes, with links back to the shared gallery. Its five local files are
  `index.html`, `app.js`, `styles.css`, `media-hosting.js`, and `episodes.json`.
- `gallery/index.html`: RoboTwin Before (482 episodes) and V4 (182 episodes),
  plus an entrance to LIBERO. The contributor's catalogs remain unchanged.
- Root `app.js` and `media-hosting.js`: shared RoboTwin UI and media routing.
- Root comparison HTML pages and corresponding JSON: permanent HF media URLs.

LIBERO streams from the pinned `benchmend/libero` Dataset. Before/V4 stream from
the Space. Archived comparison videos stream from the pinned
`Alan0928/robot-agent-gallery` Dataset; 19 recovered After videos and posters
live in the Space. Their bytes match the contributor's export report.

## Publishing a change

Start from the latest Space revision, merge the intended files, and publish
only those files using `HfApi.create_commit(..., parent_commit=revision)`.
If the parent has changed, fetch and merge the intervening changes. Preserve
other contributors' catalogs, uploads, and native evaluation outcomes.

When updating the isolated LIBERO app, retain its navigation back to the shared
gallery and bump the script/style URL versions. Keep the original/revision
episode metadata consistent with the separate LIBERO Dataset.

Verify playback in both LIBERO versions, RoboTwin Before/V4, and the standalone
comparison pages. Checking that a file exists is insufficient: use a browser to
confirm decoded video dimensions and advancing playback, and inspect failed
network requests. Root LIBERO version/episode links should still redirect to
the isolated page.
