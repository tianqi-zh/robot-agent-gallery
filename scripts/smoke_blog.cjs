// Self-contained browser regression for the essay and its legacy gallery links.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const prefix = '/project-preview/robot-agent-gallery/';
const mediaRoot = process.env.MEDIA_ROOT ? path.resolve(process.env.MEDIA_ROOT) : null;
const hosting = JSON.parse(fs.readFileSync(path.join(root, 'gallery-hosting.json'), 'utf8'));
const robotwin = JSON.parse(fs.readFileSync(path.join(root, 'data/robotwin-alignment-summary.json'), 'utf8'));
const types = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.jpg':'image/jpeg', '.svg':'image/svg+xml', '.mp4':'video/mp4', '.csv':'text/csv'};
const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost');
  const fixture = mediaRoot && url.pathname.startsWith('/__hf_media__/');
  const mount = fixture ? '/__hf_media__/' : url.pathname.startsWith(prefix) ? prefix : '/';
  const directory = fixture ? mediaRoot : root;
  let file = path.resolve(directory, decodeURIComponent(url.pathname.slice(mount.length)));
  if (!file.startsWith(directory + path.sep) && file !== directory) { response.writeHead(403).end(); return; }
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
  const errors = [], badResponses = [], localMediaRequests = [];
  const alignment = JSON.parse(fs.readFileSync(path.join(root,'data/libero-alignment.json'),'utf8'));
  const changedTasks = alignment.tasks.filter(task => task.changed);
  const expectedHighlights = {
    libero_goal_t00:['fully'],
    libero_goal_t05:['close','to','its','front','edge'],
    libero_goal_t09:['upper','with','its','base','against','the','lower','rail'],
    libero_object_t00:['blue','and','yellow','can'],
    libero_object_t04:['white','capped','bottle'],
    libero_10_t05:['between','the','two','large','side','compartments'],
    libero_10_t06:['in','center','of','the','immediately'],
    libero_10_t07:['fully','inside'],
    libero_spatial_t04:['in','center','of','the']
  };
  const output = path.join(__dirname,'../artifacts/browser/blog');
  fs.mkdirSync(output,{recursive:true});
  let decoded = 0;
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    page.on('pageerror',error => errors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.origin === origin && /\/media\//.test(url.pathname)) localMediaRequests.push(url.href);
    });
    // Exercise forwarding without depending on the live Space's gallery runtime.
    await page.route(`${hosting.galleryUrl}**`, route => route.fulfill({contentType:'text/html',body:'<!doctype html><title>Hugging Face gallery destination</title><main>Gallery destination</main>'}));
    if (mediaRoot) {
      await page.route(`${hosting.mediaBaseUrl}**`, async route => {
        const relative = route.request().url().slice(hosting.mediaBaseUrl.length);
        const response = await route.fetch({url:`${origin}/__hf_media__/${relative}`});
        await route.fulfill({response});
      });
    }
    page.on('response',response => { if(response.status()>=400) badResponses.push([response.status(),response.url()]); });
    for (const mount of ['/',prefix]) {
      const base = `${origin}${mount}`;
      console.log(`Checking blog at ${mount}`);
      await page.goto(base);
      await page.waitForFunction(() => document.documentElement.dataset.blogReady === 'true');
      assert.equal(await page.locator('#load-error').isVisible(),false);
      assert.match(await page.title(),/When bench cannot judge actor/);
      assert.equal((await page.locator('h1').innerText()).replace(/\s+/g,' ').trim(),'When bench cannot judge actor');
      assert.equal(await page.locator('[data-scope]').count(),0);
      assert.deepEqual(await page.locator('#comparison .score-top > span').allTextContents(),['n = 400','n = 400']);
      assert.equal(await page.locator('#comparison .cross-table').count(),2);
      assert.deepEqual(await page.locator('#comparison .cross-table caption').allTextContents(),Array(2).fill('Agent’s completion judgment × benchmark’s verdict'));
      assert.deepEqual(await page.locator('#comparison .cross-table thead th').allTextContents(),Array(2).fill(['Agent’s completion judgment','Bench judges success','Bench judges failure']).flat());
      assert.deepEqual(await page.locator('#comparison .cross-table tbody th').allTextContents(),Array(2).fill(['Agent considers complete','Agent does not consider complete']).flat());
      assert.doesNotMatch(await page.locator('#comparison').innerText(),/\b(?:agent|bench) (?:success|failure)\b/i);
      assert.deepEqual(await page.locator('#comparison .score-value').allTextContents(),['88.25%','100.00%']);
      assert.equal(await page.locator('#comparison .cross-table tbody tr').count(),4);
      assert.deepEqual(await page.locator('#comparison .cross-table .success td:first-of-type').allTextContents(),['322','357']);
      assert.deepEqual(await page.locator('#comparison .cross-table .failure td:last-of-type').allTextContents(),['31','43']);
      assert.deepEqual(await page.locator('#comparison .cross-table .not-applicable').allTextContents(),['\\','\\']);
      assert.doesNotMatch(await page.locator('body').innerText(),/unknown|no explicit finish assessment/i);
      assert.deepEqual(await page.locator('#comparison .cross-table .mismatch').allTextContents(),['47','0']);
      assert.equal(await page.locator('#instruction-rows tr').count(),9);
      assert.equal(await page.locator('#instruction-rows .revision-label').count(),0);
      for (const task of changedTasks) {
        const row = page.locator(`#instruction-rows [data-task="${task.id}"]`);
        assert.equal(await row.locator('.instruction-original').textContent(),task.instructionBefore);
        assert.equal(await row.locator('.instruction-original *').count(),0,'Original instruction must be unformatted');
        assert.equal(await row.locator('.instruction-improved').textContent(),task.instructionAfter,'Highlighting must preserve exact instruction text');
        assert.deepEqual(await row.locator('.instruction-improved strong').allTextContents(),expectedHighlights[task.id],task.id);
        assert.equal(await row.locator('.instruction-improved :not(strong)').count(),0);
      }
      assert.equal(await page.locator('.case').count(),7);
      assert.equal(await page.locator('.failure-case').count(),4);
      assert.equal(await page.locator('#paired-cases video, #failure-cases video').count(),18);
      assert.equal(await page.locator('#robotwin-cases video').count(),8);
      assert.equal(await page.locator('video').count(),26);
      assert.deepEqual(await page.locator('#robotwin-comparison .score-top > span').allTextContents(),[robotwin.before,robotwin.after].map(stats=>`n = ${stats.n}`));
      assert.deepEqual(await page.locator('#robotwin-comparison .score-value').allTextContents(),[robotwin.before,robotwin.after].map(stats=>`${(100*stats.instinctAlignment).toFixed(2)}%`));
      const mediaUrls = await page.locator('video').evaluateAll(videos=>videos.flatMap(video=>[video.src,video.poster]));
      assert.equal(mediaUrls.length,52);
      assert.ok(mediaUrls.every(url=>url.startsWith(hosting.mediaBaseUrl+'media/')),'All videos and posters must be hosted on HF');
      const downloads = await page.locator('.clip-meta a[download]').evaluateAll(links=>links.map(link=>link.href));
      assert.equal(downloads.length,26);
      assert.ok(downloads.every(link=>link.startsWith(hosting.mediaBaseUrl+'media/') && new URL(link).searchParams.get('download') === 'true'),'HF download links must request attachment responses');
      assert.ok((await page.locator('[data-gallery-path]').evaluateAll(links=>links.map(link=>link.href))).every(url=>url.startsWith(hosting.galleryUrl) && new URL(url).pathname.endsWith('/index.html')));
      assert.match(await page.locator('#instruction-rows [data-task="libero_goal_t05"]').innerText(),/close to its front edge/);
      assert.match(await page.locator('#instruction-rows [data-task="libero_10_t05"]').innerText(),/between the two large side compartments/);
      assert.match(await page.locator('#failure-plate-control-budget .clip-meta').innerText(),/Agent reports unable to continue/);
      assert.match(await page.locator('#failure-plate-wrong-object .clip-meta').innerText(),/Agent claimed completion · corrected to incomplete/);
      assert.match(await page.locator('#failure-bottom-drawer-sequence .clip-meta').innerText(),/No completion claim · control budget exhausted/);
      assert.match(await page.locator('#case-book-compartment .clip-meta').first().innerText(),/Agent considers the task complete/);
      assert.match(await page.locator('#case-book-compartment .clip-meta').last().innerText(),/Bench judges success/);
      assert.equal(await page.locator('#review-note').count(),1);
      assert.doesNotMatch(await page.locator('.clip-meta').allTextContents().then(items=>items.join(' ')),/Human review:|Completion: success|Agent: visually complete/);
      assert.ok((await page.locator('.clip-header .status').allTextContents()).every(text=>['Bench judges success','Bench judges failure'].includes(text)));
      assert.match(await page.locator('#review-accounting').textContent(),/357, 0, and 43/);
      assert.match(await page.locator('#review-accounting').textContent(),/agent considers the task complete and the bench judges failure/);
      assert.doesNotMatch(await page.locator('#review-accounting').textContent(),/human review|adjudication/i);
      assert.match(await page.locator('#case-plate-near-stove .case-detail').innerText(),/8 × 8 cm/);
      assert.match(await page.locator('#case-spatial-regression .case-detail').innerText(),/success → failure/);
      assert.match(await page.locator('#comparison .after .native-score').innerText(),/Bench judges success: 357\/400/);
      // Check every local link; media URLs are on HF and decoded below.
      const links = await page.locator('a[href]').evaluateAll(as => [...new Set(as.map(a => a.href))]);
      for(const link of links) {
        const parsed = new URL(link);
        if(parsed.origin !== origin || parsed.hash || parsed.pathname.endsWith('.mp4')) continue;
        const response = await page.request.head(link);
        assert.equal(response.ok(),true,`Broken link: ${link}`);
      }
      // Decode all 18 LIBERO and 8 RoboTwin clips through their external HF URLs.
      for(let i=0;i<26;i++) {
        await page.locator('video').nth(i).evaluate(video => {video.preload='metadata';video.load();});
        await page.waitForFunction(index => {
          const video = document.querySelectorAll('video')[index];
          return video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0 && video.duration > 0;
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
        await page.locator('#instructions .table-scroll').screenshot({path:path.join(output,'desktop-instructions.png')});
        await page.locator('.case').first().screenshot({path:path.join(output,'desktop-case.png')});
        await page.setViewportSize({width:390,height:844});
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(output,'mobile-hero.png')});
        await page.locator('#results').screenshot({path:path.join(output,'mobile-results.png')});
        await page.setViewportSize({width:1440,height:1000});
      }
      console.log(`Decoded all clips and checked layout at ${mount}`);
      // Essay anchors stay on the essay; historical links preserve query and hash on HF.
      await page.goto(`${base}#results`);
      assert.equal(new URL(page.url()).pathname,mount);
      await page.waitForFunction(() => document.documentElement.dataset.blogReady === 'true');
      await page.evaluate(() => { location.hash = 'benchmark=robotwin'; });
      await page.waitForURL(`${hosting.galleryUrl}gallery/robotwin/index.html#benchmark=robotwin`);
      for (const [hash, target] of [
        ['#benchmark=libero&task=libero_10_t05&episode=libero_10_t05_r00','gallery/libero/index.html'],
        ['#benchmark=robotwin_nvidia10','gallery/robotwin/index.html'],
        ['#task=robocasa_alpha&episode=robocasa_alpha_r00','gallery/robocasa/index.html'],
        ['#view=all','gallery/index.html']
      ]) {
        await page.goto(`${base}?source=old-link${hash}`);
        await page.waitForURL(`${hosting.galleryUrl}${target}?source=old-link${hash}`);
      }
      for (const name of ['', 'libero', 'robotwin', 'robotwin_nvidia10', 'robocasa', 'robodojo']) {
        const route = `gallery/${name ? name + '/' : ''}`;
        const target = (name === 'robotwin_nvidia10' ? 'gallery/robotwin/' : route) + 'index.html';
        const state = '?source=bookmark#benchmark=libero&task=libero_10_t05&episode=libero_10_t05_r00';
        await page.goto(`${base}${route}${state}`);
        await page.waitForURL(`${hosting.galleryUrl}${target}${state}`);
      }
    }
    // Static forwarding links work when JavaScript is disabled.
    const noScript = await browser.newContext({javaScriptEnabled:false});
    const fallbackPage = await noScript.newPage();
    await fallbackPage.goto(`${origin}${prefix}gallery/robotwin_nvidia10/`);
    assert.equal(await fallbackPage.locator('[data-gallery-path]').getAttribute('href'),`${hosting.galleryUrl}gallery/robotwin/index.html`);
    await noScript.close();
    assert.deepEqual(localMediaRequests,[],'The blog must never request media from GitHub Pages');
    // Escaping remains intact when diff markup encounters punctuation and HTML-like words.
    const escapedData = structuredClone(alignment);
    const escapedTask = escapedData.tasks.find(task=>task.changed);
    escapedTask.instructionBefore = 'place "book" & <caddy> beside the tray';
    escapedTask.instructionAfter = 'place "book" & <caddy> safely beside the tray <img src="x" onerror="throw 1">';
    await page.route('**/data/libero-alignment.json',route=>route.fulfill({json:escapedData}));
    await page.goto(origin + '/');
    await page.waitForFunction(()=>document.documentElement.dataset.blogReady==='true');
    const escapedRow = page.locator(`#instruction-rows [data-task="${escapedTask.id}"]`);
    assert.equal(await escapedRow.locator('.instruction-original').textContent(),escapedTask.instructionBefore);
    assert.equal(await escapedRow.locator('.instruction-improved').textContent(),escapedTask.instructionAfter);
    assert.equal(await escapedRow.locator('img,caddy,script').count(),0);
    assert.deepEqual(errors,[]);
    assert.deepEqual(badResponses,[]);
    console.log(`Blog smoke passed: two mount paths, fixed 400-episode comparison, explicit judgment labels, 9 exact highlighted instructions, escaped markup, 7 LIBERO pairs, 4 LIBERO failure cases, 8 RoboTwin cases, ${decoded} external video decodes, responsive layouts and HF forwarding.`);
  } finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => {console.error(error);process.exitCode=1;});
