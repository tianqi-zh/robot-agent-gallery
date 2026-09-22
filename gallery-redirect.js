(() => {
  'use strict';
  const link = document.querySelector('[data-gallery-path]');
  const destination = base => {
    const target = new URL(link.dataset.galleryPath, base);
    target.search = location.search;
    target.hash = location.hash;
    return target.href;
  };
  // Keep the visible fallback usable even if the hosting configuration cannot load.
  const fallback = new URL(link.href);
  fallback.search = location.search;
  fallback.hash = location.hash;
  link.href = fallback.href;
  window.galleryHosting.then(config => {
    link.href = destination(config.galleryUrl);
    location.replace(link.href);
  }).catch(error => console.error(error));
})();
