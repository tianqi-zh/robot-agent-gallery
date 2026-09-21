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
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const errors = [], badResponses = [];
  const output = path.join(__dirname,'../artifacts/browser/blog');
  fs.mkdirSync(output,{recursive:true});
  let decoded = 0;
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    page.on('pageerror',error => errors.push(error.message));
    page.on('response',response => { if(response.status()>=400) badResponses.push([response.status(),response.url()]); });
    for (const mount of ['/',prefix]) {
      const base = `${origin}${mount}`;
      console.log(`Checking blog at ${mount}`);
      await page.goto(base);
      await page.waitForFunction(() => document.documentElement.dataset.blogReady === 'true');
      assert.equal(await page.locator('#load-error').isVisible(),false);
      assert.equal(await page.locator('.cross-table').count(),2);
      assert.deepEqual(await page.locator('.score-value').allTextContents(),['88.25%','100.00%']);
      assert.equal(await page.locator('.cross-table tbody tr').count(),4);
      assert.deepEqual(await page.locator('.cross-table .success td:first-of-type').allTextContents(),['322','357']);
      assert.deepEqual(await page.locator('.cross-table .failure td:last-of-type').allTextContents(),['31','43']);
      assert.deepEqual(await page.locator('.cross-table .not-applicable').allTextContents(),['\\','\\']);
      assert.doesNotMatch(await page.locator('body').innerText(),/unknown|no explicit finish assessment/i);
      assert.deepEqual(await page.locator('.cross-table .mismatch').allTextContents(),['47','0']);
      assert.equal(await page.locator('#instruction-rows tr').count(),9);
      assert.equal(await page.locator('.case').count(),7);
      assert.equal(await page.locator('.failure-case').count(),4);
      assert.equal(await page.locator('video').count(),18);
      assert.match(await page.locator('#instruction-rows [data-task="libero_goal_t05"]').innerText(),/close to its front edge/);
      assert.match(await page.locator('#instruction-rows [data-task="libero_10_t05"]').innerText(),/between the two large side compartments/);
      assert.match(await page.locator('#failure-plate-control-budget .clip-meta').innerText(),/Agent: unable to continue/);
      assert.match(await page.locator('#failure-plate-wrong-object .clip-meta').innerText(),/Human review: failure/);
      assert.match(await page.locator('#review-accounting').textContent(),/357, 0, and 43/);
      assert.match(await page.locator('#case-plate-near-stove .case-detail').innerText(),/8 × 8 cm/);
      assert.match(await page.locator('#case-spatial-regression .case-detail').innerText(),/success → failure/);
      await page.locator('[data-scope="revised"]').click();
      assert.deepEqual(await page.locator('.score-value').allTextContents(),['47.78%','100.00%']);
      assert.match(await page.locator('.after .native-score').innerText(),/75\/90/);
      assert.deepEqual(await page.locator('.cross-table .success td:first-of-type').allTextContents(),['40','75']);
      assert.deepEqual(await page.locator('.cross-table .failure td:last-of-type').allTextContents(),['3','15']);
      await page.locator('[data-scope="all"]').click();
      assert.deepEqual(await page.locator('.score-value').allTextContents(),['88.25%','100.00%']);
      // Check every local link; media payloads are fetched by video decoding below.
      const links = await page.locator('a[href]').evaluateAll(as => [...new Set(as.map(a => a.href))]);
      for(const link of links) {
        const parsed = new URL(link);
        if(parsed.origin !== origin || parsed.hash || parsed.pathname.endsWith('.mp4')) continue;
        const response = await page.request.head(link);
        assert.equal(response.ok(),true,`Broken link: ${link}`);
      }
      // Real decode of each full clip, including the new reruns under a project prefix.
      for(let i=0;i<18;i++) {
        await page.locator('video').nth(i).evaluate(video => {video.preload='metadata';video.load();});
        await page.waitForFunction(index => {
          const video = document.querySelectorAll('video')[index];
          return video.readyState >= 2 && video.videoWidth === 1024 && video.videoHeight === 512 && video.duration > 0;
        },i);
        decoded++;
      }
      await page.locator('.play-pair').first().click();
      await page.waitForFunction(() => [...document.querySelectorAll('.case:first-child video')].every(v => !v.paused && v.currentTime > 0));
      await page.locator('.play-pair').first().click();
      assert.equal(await page.locator('.case').first().locator('video').evaluateAll(videos => videos.every(v => v.paused)),true);
      for(const width of [360,390,768,1440]) {
        await page.setViewportSize({width,height:1000});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true,`Blog overflows at ${width}`);
      }
      if(mount === '/') {
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(output,'desktop-hero.png')});
        await page.locator('#results').screenshot({path:path.join(output,'desktop-results.png')});
        await page.locator('.case').first().screenshot({path:path.join(output,'desktop-case.png')});
        await page.setViewportSize({width:390,height:844});
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(output,'mobile-hero.png')});
        await page.locator('#results').screenshot({path:path.join(output,'mobile-results.png')});
        await page.setViewportSize({width:1440,height:1000});
      }
      console.log(`Decoded all clips and checked layout at ${mount}`);
      // Essay anchors stay on the essay; historical gallery hashes route to the child page.
      await page.goto(`${base}#results`);
      assert.equal(new URL(page.url()).pathname,mount);
      await page.goto(`${base}#benchmark=libero&task=libero_10_t05&episode=libero_10_t05_r00`);
      await page.waitForURL(`**${mount}gallery/libero/**`);
      await page.waitForFunction(() => document.querySelector('#episode-video').dataset.episode === 'libero_10_t05_r00');
      await page.goto(`${base}#benchmark=robotwin_nvidia10`);
      await page.waitForURL(`**${mount}gallery/robotwin/**`);
      await page.waitForFunction(() => document.querySelectorAll('.task-card').length === 50);
    }
    assert.deepEqual(errors,[]);
    assert.deepEqual(badResponses,[]);
    console.log(`Blog smoke passed: two mount paths, two denominators, 9 instructions, 7 pairs, 4 failure cases, ${decoded} video decodes, responsive layouts and legacy links.`);
  } finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => {console.error(error);process.exitCode=1;});
