// Self-contained browser regression for direct and legacy nested gallery URLs.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const prefix = '/project-preview/robot-agent-gallery/';
const types = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.jpg':'image/jpeg', '.svg':'image/svg+xml', '.mp4':'video/mp4', '.csv':'text/csv'};
const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost');
  const mount = url.pathname.startsWith(prefix) ? prefix : '/';
  let file = path.resolve(root, decodeURIComponent(url.pathname.slice(mount.length)));
  if (!file.startsWith(root + path.sep) && file !== root) { response.writeHead(403).end(); return; }
  try {
    if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    const stat = fs.statSync(file);
    const headers = {'Content-Type':types[path.extname(file)] || 'application/octet-stream', 'Accept-Ranges':'bytes'};
    const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || '');
    let start = 0, end = stat.size - 1;
    if (range) {
      start = Number(range[1]); end = range[2] ? Math.min(Number(range[2]), end) : end;
      if (start > end) { response.writeHead(416).end(); return; }
      headers['Content-Range'] = `bytes ${start}-${end}/${stat.size}`;
    }
    headers['Content-Length'] = end - start + 1;
    response.writeHead(range ? 206 : 200, headers);
    if (request.method === 'HEAD') { response.end(); return; }
    const stream = fs.createReadStream(file, {start, end});
    stream.on('error', () => response.destroy());
    response.on('close', () => stream.destroy());
    stream.pipe(response);
  } catch { response.writeHead(404).end('Not found'); }
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const data = JSON.parse(fs.readFileSync(path.join(root, 'data/gallery.json'), 'utf8'));
  const demos = JSON.parse(fs.readFileSync(path.join(root, 'data/task-demos.json'), 'utf8'));
  const published = data.benchmarks.filter(b => b.id !== 'robotwin');
  const slug = id => id === 'robotwin_nvidia10' ? 'robotwin' : id;
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  const errors = [], badResponses = [];
  let checks = 0;
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}, permissions:['clipboard-read','clipboard-write']});
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => { if (response.status() >= 400) badResponses.push([response.status(),response.url()]); });
    const ready = async () => {
      await page.waitForFunction(() => document.querySelectorAll('.task-card').length > 0);
      assert.equal(await page.locator('#load-error').isVisible(), false);
    };
    for (const mount of ['/', prefix]) {
      const base = `${origin}${mount}`;
      await page.goto(`${base}gallery/`);
      await ready();
      assert.equal(await page.locator('.benchmark-summary').count(), published.length);
      assert.equal(await page.locator('#total-episodes').textContent(), String(published.reduce((n,b) => n+b.summary.episodes,0)));
      assert.equal(await page.locator('#total-tasks').textContent(), String(published.reduce((n,b) => n+b.tasks.length,0)));
      assert.equal(await page.locator('a[data-benchmark="robotwin"]').count(), 0);
      assert.equal(await page.locator('.brand').getAttribute('href'), '../');
      assert.equal(await page.locator('.benchmark-tabs [data-benchmark="robotwin_nvidia10"]').innerText(), 'Robotwin 482');
      assert.equal(await page.locator('.benchmark-tabs [data-benchmark="robotwin_nvidia10"]').getAttribute('href'), `${base}gallery/robotwin/`);
      checks++;

      for (const b of published) {
        const canonical = `${base}gallery/${slug(b.id)}/`;
        await page.goto(canonical);
        await ready();
        assert.equal(await page.locator('body').getAttribute('data-benchmark'), b.id);
        assert.equal(await page.locator('.task-card').count(), b.tasks.length);
        assert.equal(await page.locator('#total-episodes').textContent(), String(b.summary.episodes));
        assert.deepEqual(await page.locator('.media-thumb').evaluateAll(elements => [...new Set(elements.map(el => el.dataset.openBenchmark))]), [b.id]);
        assert.equal(await page.locator('.benchmark-summary').count(), 1);
        const poster = await page.locator('.media-thumb img').first().getAttribute('src');
        assert.equal(poster, new URL(b.tasks[0].episodes[0].poster, base).href);
        assert.equal(await page.locator('.brand').evaluate(a => a.href), base);
        assert.equal(await page.locator('a.text-link[download]').evaluate(a => a.href), new URL('data/episodes.csv', base).href);

        // A direct child link needs no benchmark hash, and keeps its selected episode on reload.
        const task = b.tasks[0], episode = task.episodes.at(-1);
        const deep = `${canonical}#task=${task.id}&episode=${episode.id}`;
        await page.goto(deep);
        await page.waitForFunction(id => document.querySelector('#episode-video').dataset.episode === id, episode.id);
        const source = await page.evaluate(episode => assetUrl(resolveVideoSource(episode)), episode);
        assert.equal(await page.locator('#episode-video').getAttribute('src'), source);
        assert.equal(await page.locator('#download-video').getAttribute('href'), source);
        assert.equal(await page.locator('#task-instruction').textContent(), episode.instruction || task.instruction);
        // Native media is actually decoded, including files addressed from the nested project mount.
        await page.waitForFunction(() => document.querySelector('#episode-video').readyState >= 2);
        await page.locator('#copy-link').click();
        assert.equal(await page.evaluate(() => navigator.clipboard.readText()), page.url());
        await page.locator('#close-dialog').click();
        await page.waitForFunction(() => !document.querySelector('dialog').open);
        assert.equal(new URL(page.url()).pathname, new URL(canonical).pathname);

        const demoTask = b.tasks.find(task => demos.tasks[task.id]?.status === 'available');
        if (demoTask) {
          await page.goto(`${canonical}#task=${demoTask.id}&view=demo`);
          await page.waitForFunction(id => document.querySelector('#episode-video').dataset.media === `demo:${id}` && document.querySelector('#episode-video').readyState >= 2, demoTask.id);
          assert.equal(await page.locator('#download-video').getAttribute('href'), new URL(demos.tasks[demoTask.id].video, base).href);
          await page.locator('#close-dialog').click();
          await page.waitForFunction(() => !document.querySelector('dialog').open);
        }
        for (const width of [360,768,1440]) {
          await page.setViewportSize({width,height:900});
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${b.id} overflows at ${width}`);
        }
        const next = published[(published.indexOf(b)+1)%published.length];
        await page.locator(`.benchmark-tabs [data-benchmark="${next.id}"]`).click();
        await ready();
        assert.equal(new URL(page.url()).pathname, `${mount}gallery/${slug(next.id)}/`);
        assert.equal(await page.locator('.task-card').count(), next.tasks.length);
        await page.goBack();
        await ready();
        assert.equal(await page.locator('.task-card').count(), b.tasks.length);
        checks++;
      }
      await page.goto(`${base}gallery/robotwin_nvidia10/?source=legacy#benchmark=robotwin_nvidia10`);
      await ready();
      assert.equal(new URL(page.url()).pathname, `${mount}gallery/robotwin/`);
      assert.equal(new URL(page.url()).search, '?source=legacy');
      assert.equal(new URL(page.url()).hash, '#benchmark=robotwin_nvidia10');
      const current = published.find(b => b.id === 'robotwin_nvidia10');
      const archived = data.benchmarks.find(b => b.id === 'robotwin').tasks[0];
      await page.goto(`${base}gallery/robotwin/#benchmark=robotwin&task=${archived.id}&episode=${archived.episodes[0].id}`);
      await ready();
      assert.equal(await page.locator('#route-notice').isVisible(), true);
      assert.equal(await page.locator('dialog').evaluate(d => d.open), false);
      assert.equal(await page.locator('.task-card').count(), current.tasks.length);
      await page.goto(`${base}gallery/robotwin/#task=${current.tasks[0].id}&episode=missing`);
      await ready();
      assert.equal(await page.locator('#route-notice').isVisible(), true);
      assert.equal(await page.locator('dialog').evaluate(d => d.open), false);
      await page.goto(`${base}gallery/libero/#benchmark=robotwin`);
      await ready();
      assert.equal(new URL(page.url()).pathname, `${mount}gallery/robotwin/`);
      checks++;
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(badResponses, []);
    console.log(JSON.stringify({passed:true,checks,mounts:['/',prefix],benchmarks:published.map(b => b.id),errors,badResponses}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; server.close(); });
