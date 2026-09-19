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
const demoFixtureIndex = args.indexOf('--demo-fixture');
const demoFixturePath = demoFixtureIndex >= 0 ? args[demoFixtureIndex + 1] : null;
if (demoFixtureIndex >= 0) {
  assert.ok(demoFixturePath, '--demo-fixture requires a JSON file');
  args.splice(demoFixtureIndex, 2);
}
assert.ok(args.length <= 1, 'Usage: node scripts/smoke_browser.cjs [URL] [--fixture JSON] [--demo-fixture JSON]');
const base = args[0] || 'http://127.0.0.1:8080/';
const output = path.join(__dirname, '..', 'artifacts', 'browser', fixturePath || demoFixturePath ? 'fixture' : 'published');
fs.mkdirSync(output, {recursive:true});

(async () => {
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000},permissions:['clipboard-read','clipboard-write']});
    const data = fixturePath ? JSON.parse(fs.readFileSync(fixturePath, 'utf8'))
      : await (await context.request.get(new URL('data/gallery.json', base).href)).json();
    const demos = demoFixturePath ? JSON.parse(fs.readFileSync(demoFixturePath, 'utf8'))
      : await (await context.request.get(new URL('data/task-demos.json', base).href)).json();
    if (demoFixturePath) await context.route('**/data/task-demos.json', route => route.fulfill({json:demos}));
    if (fixturePath) {
      await context.route('**/data/gallery.json', route => route.fulfill({json:data}));
    }
    if (fixturePath || demoFixturePath) {
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
    const demoReady = async (target, task, demo) => {
      await target.waitForFunction(id => {
        const video = document.querySelector('#episode-video');
        return video.dataset.media === `demo:${id}` && video.readyState >= 2;
      }, task.id);
      assert.equal(await target.locator('#episode-video').getAttribute('data-episode'), null);
      assert.equal(await target.locator('#video-error').isVisible(), false);
      assert.equal(await target.locator('#view-demo').getAttribute('aria-selected'), 'true');
      assert.equal(await target.locator('#episode-status').isVisible(), false);
      assert.equal(await target.locator('#episode-chooser').isVisible(), false);
      assert.equal(await target.locator('#episode-navigation').isVisible(), false);
      assert.equal(await target.locator('#task-instruction').textContent(), demo.instruction || task.name);
      assert.deepEqual(await target.locator('#camera-labels span').allTextContents(), demo.cameras);
      assert.deepEqual(await target.locator('#episode-video').evaluate(video => [video.videoWidth,video.videoHeight]), [demo.width,demo.height]);
      assert.equal(await target.locator('#demo-source-link').getAttribute('href'), demo.source.url);
      assert.ok((await target.locator('#video-note').textContent()).includes(`${demo.fps} FPS`));
      assert.ok((await target.locator('#episode-facts').textContent()).includes('Source FPS'));
      assert.equal(await target.locator('#episode-facts').getByText('Seed', {exact:true}).count(), 0);
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
    assert.equal(await page.locator('.task-demo').count(), first.tasks.length);
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
      assert.equal(await page.locator('.task-demo').count(), b.tasks.length);
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
      if (b.id === 'robodojo') {
        assert.equal(b.tasks.length, 42);
        assert.equal(b.summary.episodes, 42);
        assert.equal(b.summary.successes, 6);
        assert.equal(b.summary.failures, 36);
        assert.equal(b.protocol.episodesPerTask, 1);
        assert.equal(b.suites.length, 5);
        for (const [group,expected] of [['generalization',12],['memory',6],['precision',8],['long_horizon',8],['open',8]]) {
          const suite = `robodojo_${group}`;
          assert.equal(b.tasks.filter(task => task.suite === suite).length, expected);
          assert.ok((await page.locator(`[data-suite="${suite}"]`).textContent()).includes(String(expected)));
        }
        const coverage = demos.coverage?.robodojo;
        if (coverage) {
          assert.equal(coverage.tasks, 42);
          assert.equal(await page.locator('.task-demo:not(.unavailable)').count(), coverage.available);
          assert.equal(await page.locator('.task-demo.unavailable').count(), coverage.unavailable);
          assert.ok(b.tasks.every(task => demos.tasks[task.id]));
          assert.ok((await page.locator('#collection-demo-note').textContent()).includes(`${coverage.available} of 42`));
          assert.ok(!(await page.locator('.demo-card-status').allTextContents()).includes('Not imported'));
        } else {
          assert.equal(await page.locator('#collection-demo-note').textContent(), b.protocol.trainingDemoNote);
          assert.deepEqual(await page.locator('.demo-card-status').allTextContents(), Array(42).fill('Not imported'));
          assert.ok(b.tasks.every(task => !demos.tasks[task.id]));
        }
        assert.ok(b.tasks.every(task => task.episodes.length === 1));
        const instruction = b.tasks[0].instruction;
        await page.fill('#task-search', instruction);
        await count(b.tasks.filter(task => `${task.name} ${task.instruction} ${task.suiteName} ${task.id}`.toLowerCase().includes(instruction.toLowerCase())).length);
        await page.fill('#task-search', '');
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
      assert.equal(await page.locator('#task-instruction').textContent(), task.instruction);
      assert.deepEqual(await page.locator('#camera-labels span').allTextContents(), b.protocol.cameras);
      assert.ok((await page.locator('#video-note').textContent()).startsWith(b.protocol.videoNote));
      assert.ok((await page.locator('#episode-facts').textContent()).includes(`${episode.steps} / ${episode.maxSteps}`));
      assert.equal(await page.locator('#episode-status').textContent(), {success:'Success',failure:'Failure',timeout:'Timeout'}[episode.status]);
      if (Number.isFinite(episode.nativeScore)) {
        assert.equal(await page.locator('#episode-facts div').filter({has:page.getByText('Native score', {exact:true})}).locator('dd').textContent(), `${(episode.nativeScore * 100).toFixed(1)}%`);
      }
      if (b.id === 'robodojo') {
        assert.deepEqual([episode.width,episode.height], [1920,480]);
        assert.equal(b.protocol.cameras.length, 3);
        assert.match(await page.locator('#video-note').textContent(), /25\s*fps/i);
      }
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
      const demoTask = b.tasks.find(task => demos.tasks[task.id]?.status === 'available');
      if (demoTask) {
        const demo = demos.tasks[demoTask.id], lastEpisode = demoTask.episodes.at(-1);
        await page.locator(`.sample-dot[data-episode="${lastEpisode.id}"]`).click();
        await ready(page, lastEpisode);
        await page.locator('#view-demo').click();
        await demoReady(page, demoTask, demo);
        assert.equal(await page.locator('#episode-video').evaluate(video => video.paused), true);
        assert.equal(await page.locator('#episode-video').evaluate(video => video.playbackRate), 2);
        await page.locator('#episode-video').evaluate(async video => { video.muted = true; await video.play(); });
        await page.waitForFunction(() => document.querySelector('#episode-video').currentTime > .1);
        await page.locator('#copy-link').click();
        await page.waitForFunction(() => document.querySelector('#copy-status').textContent.length > 0);
        assert.match(await page.locator('#copy-status').textContent(), /Demo link copied|http/);
        const demoUrl = page.url();
        assert.equal(new URLSearchParams(new URL(demoUrl).hash.slice(1)).get('view'), 'demo');
        await fits(1440);
        await page.locator('#episode-dialog').evaluate(dialog => { dialog.scrollTop = 0; });
        await page.screenshot({path:path.join(output, `training-demo-${b.id}-desktop.png`)});
        await fits(390);
        await page.locator('#episode-dialog').evaluate(dialog => { dialog.scrollTop = 0; });
        await page.screenshot({path:path.join(output, `training-demo-${b.id}-mobile.png`)});
        // Tabs are keyboard operable, and returning to agent playback retains episode selection.
        await page.locator('#view-demo').focus();
        await page.keyboard.press('ArrowLeft');
        await ready(page, lastEpisode);
        assert.equal(await page.locator('#task-instruction').textContent(), demoTask.instruction);
        assert.equal(await page.evaluate(() => document.activeElement.id), 'view-episode');
        assert.equal(await page.locator('#episode-video').evaluate(video => video.paused), true);
        await page.keyboard.press('End');
        await demoReady(page, demoTask, demo);
        await close(page);
        assert.equal(await page.locator('#episode-video').getAttribute('src'), null);
        // The card control opens the same shareable training reference directly.
        await page.locator(`.task-demo[data-task="${demoTask.id}"]`).click();
        await demoReady(page, demoTask, demo);
        await page.goBack();
        await page.waitForFunction(() => !document.querySelector('dialog').open);
        assert.equal(await page.evaluate(() => document.activeElement.dataset.openDemo), b.id);
        await page.goForward();
        await demoReady(page, demoTask, demo);
        await page.keyboard.press('Escape');
        await page.waitForFunction(() => !document.querySelector('dialog').open);
        const directDemo = await context.newPage();
        await directDemo.goto(demoUrl);
        await demoReady(directDemo, demoTask, demo);
        await close(directDemo);
        await directDemo.close();
      }
      const unavailableTask = b.tasks.find(task => demos.tasks[task.id]?.status !== 'available');
      if (unavailableTask) {
        await page.locator(`.task-demo[data-task="${unavailableTask.id}"]`).click();
        await page.waitForSelector('#demo-unavailable');
        const reason = demos.tasks[unavailableTask.id]?.reason || b.protocol.trainingDemoNote || 'A training demonstration is not available for this task yet.';
        assert.equal(await page.locator('#demo-unavailable-reason').textContent(), reason);
        assert.equal(await page.locator('#episode-video').getAttribute('src'), null);
        assert.equal(await page.locator('#episode-status').isVisible(), false);
        if (b.id === 'robodojo') {
          const imported = Boolean(demos.tasks[unavailableTask.id]);
          assert.equal(await page.locator('#demo-unavailable-title').textContent(), imported ? 'Training demo unavailable' : 'Training demo not imported');
          assert.equal(await page.locator('#download-video').isVisible(), false);
          if (!imported) assert.match(reason, /have not been imported/);
          await page.locator('#copy-link').click();
          await page.waitForFunction(() => document.querySelector('#copy-status').textContent.length > 0);
          const demoUrl = page.url(), directDemo = await context.newPage();
          assert.equal(new URLSearchParams(new URL(demoUrl).hash.slice(1)).get('view'), 'demo');
          await directDemo.goto(demoUrl);
          await directDemo.waitForSelector('#demo-unavailable');
          assert.equal(await directDemo.locator('#demo-unavailable-reason').textContent(), reason);
          assert.equal(await directDemo.locator('#episode-video').getAttribute('src'), null);
          await directDemo.locator('#view-episode').click();
          await ready(directDemo, unavailableTask.episodes[0]);
          await directDemo.close();
        }
        await fits(1440);
        await page.screenshot({path:path.join(output, `training-unavailable-${b.id}-desktop.png`)});
        await fits(390);
        await page.screenshot({path:path.join(output, `training-unavailable-${b.id}-mobile.png`)});
        await close(page);
      }
      for (const width of [360,768,1024,1440]) await fits(width);
      await fits(360);
      await page.locator('#collection').evaluate(section => section.scrollIntoView({block:'start',behavior:'instant'}));
      await page.screenshot({path:path.join(output, `collection-${b.id}-mobile.png`)});
    }
    // Isolate a missing-data fixture so this branch stays covered as real demo coverage grows.
    const missingTask = first.tasks[0];
    const missingContext = await browser.newContext({viewport:{width:390,height:844}});
    try {
      const missingPage = await missingContext.newPage();
      missingPage.on('pageerror', error => errors.push(error.message));
      await missingContext.route('**/data/gallery.json', route => route.fulfill({json:data}));
      await missingContext.route('**/data/task-demos.json', route => route.fulfill({json:{schemaVersion:1,tasks:{[missingTask.id]:{
        taskId:missingTask.id,benchmark:first.id,status:'unavailable',reason:'Training recording is not available in this test fixture.',
        source:{dataset:'Missing-data UI test fixture',url:'https://example.invalid/training-fixture'}
      }}}}));
      await missingPage.goto(new URL(`#benchmark=${first.id}&task=${missingTask.id}&view=demo`, base).href);
      await missingPage.waitForSelector('#demo-unavailable');
      assert.equal(await missingPage.locator('#episode-video').isVisible(), false);
      assert.equal(await missingPage.locator('#episode-video').getAttribute('src'), null);
      assert.equal(await missingPage.locator('#download-video').isVisible(), false);
      assert.equal(await missingPage.locator('#episode-status').isVisible(), false);
      assert.match(await missingPage.locator('#demo-unavailable-reason').textContent(), /test fixture/);
      await fits(360, missingPage);
      await missingPage.locator('#view-episode').click();
      await ready(missingPage, missingTask.episodes[0]);
      await missingPage.locator('#view-demo').click();
      assert.equal(await missingPage.locator('#episode-video').getAttribute('src'), null);
      await close(missingPage);
      assert.match(await missingPage.locator(`.task-demo[data-task="${missingTask.id}"]`).textContent(), /Unavailable/);
      // Losing the optional catalog still leaves the evaluation gallery usable.
      await missingContext.unroute('**/data/task-demos.json');
      await missingContext.route('**/data/task-demos.json', route => route.fulfill({status:503,body:'Temporary test outage'}));
      await missingPage.reload();
      await missingPage.waitForSelector('.task-card');
      assert.equal(await missingPage.locator('#total-episodes').textContent(), String(totalEpisodes));
      await missingPage.locator(`.media-thumb[data-task="${missingTask.id}"]`).click();
      await ready(missingPage, missingTask.episodes[0]);
    } finally { await missingContext.close(); }
    assert.deepEqual(errors, []);
    assert.deepEqual(badResponses, []);
    const report = {passed:true,dataSource:fixturePath ? 'isolated UI fixture; not evaluation results' : new URL('data/gallery.json', base).href,demoSource:demoFixturePath ? 'isolated UI fixture; not training demonstrations' : new URL('data/task-demos.json', base).href,
      benchmarks:benchmarks.map(b => b.id),tasks:totalTasks,episodes:totalEpisodes,
      desktopAndMobile:true,filters:true,suites:true,allEpisodeSelection:true,playback:true,deepLinks:true,
      backCloseReopen:true,zeroEagerVideos:true,trainingDemos:true,demoKeyboardTabs:true,demoDeepLinks:true,missingDemo:true,missingCatalogFallback:true,
      robodojoNativeScoreAndDemoNotice:benchmarks.some(b => b.id === 'robodojo'),errors,badResponses,mediaRequests:mediaRequests.length};
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
