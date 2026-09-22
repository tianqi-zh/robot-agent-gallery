(() => {
  'use strict';
  const scriptUrl = new URL(document.currentScript.src);
  const configUrl = new URL('gallery-hosting.json', scriptUrl);
  configUrl.search = scriptUrl.search;
  window.galleryHosting = fetch(configUrl).then(async response => {
    if (!response.ok) throw new Error(`Cannot load gallery hosting: ${response.status}`);
    const config = await response.json();
    for (const key of ['galleryUrl', 'mediaBaseUrl']) {
      const url = new URL(config[key]);
      if (url.protocol !== 'https:' || !url.pathname.endsWith('/') || url.search || url.hash) {
        throw new Error(`Invalid gallery hosting URL: ${key}`);
      }
    }
    return config;
  });
})();
