const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Optional ignored fixtures are intercepted in this browser only; public data is never written.
const args = process.argv.slice(2);
const fixtureIndex = args.indexOf('--fixture');
const fixturePath = fixtureIndex >= 0 ? args[fixtureIndex + 1] : null;
if (fixtureIndex >= 0) {
  assert.ok(fixturePath, '--fixture requires a JSON file');
  args.splice(fixtureIndex, 2);
}
assert.ok(args.length <= 1, 'Usage: node scripts/smoke_browser.cjs [URL] [--fixture JSON]');
const base = args[0] || 'http://127.0.0.1:8080/';
const output = path.join(__dirname, '..', 'artifacts', 'browser', fixturePath ? 'fixture' : 'published');
fs.mkdirSync(output, {recursive:true});

(async () => {
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000},permissions:['clipboard-read','clipboard-write']});
    const data = fixturePath ? JSON.parse(fs.readFileSync(fixturePath, 'utf8'))
      : await (await context.request.get(new URL('data/gallery.json', base).href)).json();
    if (fixturePath) {
      await context.route('**/data/gallery.json', route => route.fulfill({json:data}));
      await context.addInitScript(() => document.addEventListener('DOMContentLoaded', () => {
        const note = document.createElement('div');
        note.textContent = 'UI TEST FIXTURE — NOT EVALUATION RESULTS';
        note.style.cssText = 'position:fixed;top:0;left:0;z-index:1000;background:#702c24;color:white;padding:5px;font:11px Arial;pointer-events:none';
        document.body.append(note);
      }));
    }
    const benchmarks = data.benchmarks.filter(b => b.tasks.length && b.tasks.every(task => task.episodes.length));
    const totalTasks = benchmarks.reduce((n,b) => n + b.tasks.length, 0);
    const totalEpisodes = benchmarks.reduce((n,b) => n + b.tasks.reduce((m,task) => m + task.episodes.length, 0), 0);
    const errors = [], badResponses = [], mediaRequests = [];
    context.on('page', page => {
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => { if (response.status() >= 400) badResponses.push([response.status(),response.url()]); });
      page.on('request', request => { if (new URL(request.url()).pathname.endsWith('.mp4')) mediaRequests.push(request.url()); });
    });
    const page = await context.newPage();
    const count = async n => {
      await page.waitForFunction(n => document.querySelectorAll('.task-card').length === n, n);
      assert.equal(await page.locator('.task-card').count(), n);
    };
    const ready = async (target, episode) => {
      await target.waitForFunction(id => {
        const video = document.querySelector('#episode-video');
        return video.dataset.episode === id && video.readyState >= 2;
      }, episode.id);
      assert.equal(await target.locator('#video-error').isVisible(), false);
      const dimensions = await target.locator('#episode-video').evaluate(video => [video.videoWidth,video.videoHeight]);
      assert.deepEqual(dimensions, [episode.width,episode.height]);
    };
    const close = async target => {
      await target.locator('#close-dialog').click();
      await target.waitForFunction(() => !document.querySelector('dialog').open);
    };
    const fits = async (width, target = page) => {
      await target.setViewportSize({width,height:900});
      assert.equal(await target.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Horizontal overflow at ${width}`);
    };

    await page.goto(base, {waitUntil:'networkidle'});
    const first = benchmarks.find(b => b.id === 'libero') || benchmarks[0];
    await count(first.tasks.length);
    assert.equal(mediaRequests.length, 0, 'Video data must not preload in the collection');
    assert.equal(await page.locator('.benchmark-tabs button').count(), benchmarks.length);
    assert.equal(await page.locator('.benchmark-summary').count(), benchmarks.length);
    assert.equal(await page.locator('#total-tasks').textContent(), String(totalTasks));
    assert.equal(await page.locator('#total-episodes').textContent(), String(totalEpisodes));
    assert.equal(await page.locator('#nav-count').textContent(), String(totalEpisodes));
    // Exercise the staged-site source switch without requesting an unpublished release asset.
    assert.deepEqual(await page.evaluate(() => {
      const previous = window.GALLERY_REMOTE_VIDEOS;
      const sample = {video:'media/robocasa/test.mp4',remoteVideo:'https://example.invalid/test.mp4'};
      window.GALLERY_REMOTE_VIDEOS = false;
      const local = resolveVideoSource(sample);
      window.GALLERY_REMOTE_VIDEOS = 'true';
      const nonBoolean = resolveVideoSource(sample);
      window.GALLERY_REMOTE_VIDEOS = true;
      const remote = resolveVideoSource(sample);
      const fallback = resolveVideoSource({video:sample.video});
      window.GALLERY_REMOTE_VIDEOS = previous;
      return [local,nonBoolean,remote,fallback];
    }), ['media/robocasa/test.mp4','media/robocasa/test.mp4','https://example.invalid/test.mp4','media/robocasa/test.mp4']);
    for (const empty of data.benchmarks.filter(b => !b.tasks.length)) {
      assert.equal(await page.locator(`[data-benchmark="${empty.id}"]`).count(), 0, 'Unpublished benchmark must not be clickable');
    }
    if (benchmarks.length > 1) {
      const other = benchmarks.find(b => b.id !== first.id);
      await page.locator(`.benchmark-tabs [data-benchmark="${other.id}"]`).click();
      await count(other.tasks.length);
      await page.goBack();
      await count(first.tasks.length);
    }
    await page.screenshot({path:path.join(output, 'overview-desktop.png')});

    for (const b of benchmarks) {
      await page.setViewportSize({width:1440,height:1000});
      await page.locator(`.benchmark-tabs [data-benchmark="${b.id}"]`).click();
      await count(b.tasks.length);
      assert.ok((await page.locator('.task-meta').first().textContent()).includes(b.name.toUpperCase()));
      const summary = page.locator(`.benchmark-summary[data-benchmark="${b.id}"]`);
      assert.ok((await summary.textContent()).includes(`${b.summary.successes} / ${b.summary.episodes} successful`));
      if (b.suites.length > 1) {
        for (const suite of b.suites) {
          await page.locator(`[data-suite="${suite.id}"]`).click();
          const tasks = b.tasks.filter(task => task.suite === suite.id);
          await count(tasks.length);
          await page.selectOption('#outcome-filter', 'failures');
          await count(tasks.filter(task => task.failures > 0).length);
          await page.selectOption('#outcome-filter', 'all');
        }
        await page.locator('[data-suite="all"]').click();
      }
      if (b.id === 'robocasa') {
        assert.equal(b.tasks.length, 365);
        for (const [suite,expected] of [['robocasa_atomic',65],['robocasa_composite',300]]) {
          assert.equal(b.tasks.filter(task => task.suite === suite).length, expected);
          assert.ok((await page.locator(`[data-suite="${suite}"]`).textContent()).includes(String(expected)));
        }
      }
      await page.selectOption('#outcome-filter', 'failures');
      await count(b.tasks.filter(task => task.failures > 0).length);
      await page.selectOption('#outcome-filter', 'perfect');
      await count(b.tasks.filter(task => task.failures === 0).length);
      await page.selectOption('#outcome-filter', 'all');
      const search = b.tasks[0].id.toLowerCase();
      await page.fill('#task-search', search);
      await count(b.tasks.filter(task => `${task.name} ${task.instruction} ${task.suiteName} ${task.id}`.toLowerCase().includes(search)).length);
      await page.fill('#task-search', 'no-such-task-xyz');
      await count(0);
      assert.equal(await page.locator('#empty-state').isVisible(), true);
      await page.locator('#clear-filters').click();
      await count(b.tasks.length);
      await page.selectOption('#sort-order', 'hardest');
      const hardest = b.tasks.reduce((value,task) => task.successRate < value.successRate ? task : value);
      assert.equal(await page.locator('.media-thumb').first().getAttribute('data-task'), hardest.id);
      await page.selectOption('#sort-order', 'default');

      const task = b.tasks.find(task => task.episodes.some(ep => ep.status === 'timeout')) || b.tasks[0];
      let episode = task.episodes[0];
      await page.locator(`.media-thumb[data-task="${task.id}"]`).click();
      await ready(page, episode);
      assert.equal(await page.locator('.episode-button').count(), task.episodes.length);
      assert.deepEqual(await page.locator('#camera-labels span').allTextContents(), b.protocol.cameras);
      assert.ok((await page.locator('#video-note').textContent()).startsWith(b.protocol.videoNote));
      assert.ok((await page.locator('#episode-facts').textContent()).includes(`${episode.steps} / ${episode.maxSteps}`));
      assert.equal(await page.locator('#episode-status').textContent(), {success:'Success',failure:'Failure',timeout:'Timeout'}[episode.status]);
      await page.locator('#episode-video').evaluate(async video => { video.muted = true; await video.play(); });
      await page.waitForFunction(() => document.querySelector('#episode-video').currentTime > .15);
      await page.locator('#episode-video').evaluate(video => video.pause());
      await page.selectOption('#playback-speed', '2');
      assert.equal(await page.locator('#episode-video').evaluate(video => video.playbackRate), 2);
      if (task.episodes.length > 1) {
        await page.locator('#next-episode').click();
        await ready(page, task.episodes[1]);
        episode = task.episodes.at(-1);
        await page.locator('.episode-button').last().click();
        await ready(page, episode);
        assert.equal(await page.evaluate(() => document.activeElement.dataset.selectEpisode), episode.id);
      } else {
        assert.equal(await page.locator('#previous-episode').isDisabled(), true);
      }
      assert.equal(await page.locator('#next-episode').isDisabled(), true);
      await page.locator('#copy-link').click();
      await page.waitForFunction(() => document.querySelector('#copy-status').textContent.length > 0);
      assert.match(await page.locator('#copy-status').textContent(), /copied|http/);
      const source = await page.evaluate(episode => resolveVideoSource(episode), episode);
      assert.equal(await page.locator('#download-video').getAttribute('href'), source);
      assert.equal(await page.locator('#episode-video').getAttribute('src'), source);
      const shared = page.url();
      assert.equal(new URLSearchParams(new URL(shared).hash.slice(1)).get('episode'), episode.id);
      await page.screenshot({path:path.join(output, `player-${b.id}-desktop.png`)});
      await fits(390);
      await page.screenshot({path:path.join(output, `player-${b.id}-mobile.png`)});
      await close(page);
      await page.locator(`.media-thumb[data-task="${task.id}"]`).click();
      await ready(page, task.episodes[0]);
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('dialog').open);
      const deep = await context.newPage();
      await deep.goto(shared);
      await ready(deep, episode);
      await close(deep);
      await deep.close();
      for (const width of [360,768,1024,1440]) await fits(width);
      await fits(360);
      await page.locator('#collection').evaluate(section => section.scrollIntoView({block:'start',behavior:'instant'}));
      await page.screenshot({path:path.join(output, `collection-${b.id}-mobile.png`)});
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(badResponses, []);
    const report = {passed:true,dataSource:fixturePath ? 'isolated UI fixture; not evaluation results' : 'published gallery data',
      benchmarks:benchmarks.map(b => b.id),tasks:totalTasks,episodes:totalEpisodes,
      desktopAndMobile:true,filters:true,suites:true,allEpisodeSelection:true,playback:true,deepLinks:true,
      backCloseReopen:true,zeroEagerVideos:true,errors,badResponses,mediaRequests:mediaRequests.length};
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
