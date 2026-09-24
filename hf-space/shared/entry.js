'use strict';
// Preserve old shared-gallery episode URLs without choosing a default benchmark.
(() => {
  const galleryRoot = new URL('.', document.currentScript.src);
  const query = new URLSearchParams(location.search);
  const legacy = new URLSearchParams(location.hash.slice(1));
  const benchmark = legacy.get('benchmark');
  const episode = legacy.get('episode') || '';
  const libero = query.has('version') || /^(original|revision|revised_r[12])\//.test(query.get('episode') || '') ||
    benchmark === 'libero' || episode.startsWith('libero_');
  const robotwin = benchmark?.startsWith('robotwin') || episode.startsWith('robotwin_');
  if (!libero && !robotwin) return;
  const target = new URL(libero ? 'libero/index.html' : 'robotwin/index.html', galleryRoot);
  target.search = location.search;
  target.hash = location.hash;
  if (libero && episode) {
    target.searchParams.set('episode', `original/${episode}`);
    target.hash = '';
  }
  location.replace(target.href);
})();
