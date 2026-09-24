# Shared gallery overview

These four runtime files deploy under `gallery/` in the live BenchMend Space:
`index.html`, `landing.css`, `benchmend-shell.css`, and `entry.js`.

The overview gives LIBERO and RoboTwin the same card layout and navigation
level. Instruction versions sit within their benchmark: Original / Revision
for LIBERO and Before / V4 for RoboTwin. Counts match the published catalogs;
update them together if a collection changes.

`entry.js` forwards historical episode links to the appropriate benchmark.
An ordinary visit stays on the overview. The Space's root `index.html` forwards
to this page while preserving episode parameters.

The benchmark pages use `benchmend-shell.css` and the same Overview / LIBERO /
RoboTwin navigation. Their app code, source catalogs, and media routing live in
the remote Space. See [shared maintenance notes](../SHARED_SPACE.md) for the
layout and publication procedure. Add content hashes to changed script and
stylesheet URLs when staging an update.
