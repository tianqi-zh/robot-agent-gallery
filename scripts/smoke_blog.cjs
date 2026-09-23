// Self-contained browser regression for the essay and its legacy gallery links.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const prefix = '/project-preview/robot-agent-gallery/';
const hosting = JSON.parse(fs.readFileSync(path.join(root, 'gallery-hosting.json'), 'utf8'));
const robotwin = JSON.parse(fs.readFileSync(path.join(root, 'data/robotwin-alignment-summary.json'), 'utf8'));
const robotwinInstructions = JSON.parse(fs.readFileSync(path.join(root, 'data/robotwin-instruction-examples.json'), 'utf8'));
const liberoMedia = JSON.parse(fs.readFileSync(path.join(root, 'data/libero-blog-media.json'), 'utf8'));
const selectedLiberoFailures = ['plate-control-budget','bottom-drawer-sequence'];
const selectedRobotwinFailures = ['move_can_pot_r01','place_dual_shoes_r00'];
const displayedRobotwinCases = robotwin.cases.filter(item=>item.after.benchSuccess || selectedRobotwinFailures.includes(item.episodeKey));
const overviewVideoPath = 'media/blog/overview/blog-showcase-v2.mp4';
const displayedVideoPaths = [
  overviewVideoPath,
  ...liberoMedia.pairs.flatMap(pair=>[liberoMedia.clips[pair.before].video,liberoMedia.clips[pair.after].video]),
  ...selectedLiberoFailures.map(id=>liberoMedia.clips[liberoMedia.failureCases.find(item=>item.id===id).clip].video),
  ...displayedRobotwinCases.map(item=>item.video)
];
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
  const errors = [], badResponses = [], localMediaRequests = [], externalMediaRequests = [];
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
    // Article playback must work even when the external media service is unavailable.
    await page.route(`${hosting.mediaBaseUrl}**`, route => {
      externalMediaRequests.push(route.request().url());
      return route.abort();
    });
    page.on('response',response => { if(response.status()>=400) badResponses.push([response.status(),response.url()]); });
    for (const mount of ['/',prefix]) {
      const base = `${origin}${mount}`;
      console.log(`Checking blog at ${mount}`);
      await page.goto(base);
      await page.waitForFunction(() => document.documentElement.dataset.blogReady === 'true');
      assert.ok((await page.locator('script[src]').evaluateAll(scripts=>scripts.map(script=>script.src)))
        .every(src=>new URL(src).searchParams.has('v')),'Entry scripts must have a cache version');
      assert.equal(await page.locator('#load-error').isVisible(),false);
      assert.match(await page.title(),/Small instruction edits, better-aligned benchmarks/);
      assert.equal((await page.locator('h1').innerText()).replace(/\s+/g,' ').trim(),'Small instruction edits. Better-aligned benchmarks.');
      const overview = page.locator('#overview-video');
      assert.equal(await page.locator('.hero #overview #overview-video').count(),1);
      assert.equal(await page.locator('#overview').evaluate(element => Boolean(element.compareDocumentPosition(document.querySelector('#takeaways')) & Node.DOCUMENT_POSITION_FOLLOWING)),true,'Place the overview before the key takeaways');
      assert.deepEqual(await overview.evaluate(video => ({
        src:video.src,poster:video.poster,controls:video.controls,playsInline:video.playsInline,
        autoplay:video.autoplay,preload:video.preload,width:video.width,height:video.height
      })),{src:base+overviewVideoPath,poster:base+overviewVideoPath.replace('.mp4','.jpg'),controls:true,playsInline:true,autoplay:false,preload:'none',width:1920,height:1080});
      assert.equal(await overview.evaluate(video=>video.paused),true,'The overview must wait for a user to play it');
      assert.equal(localMediaRequests.includes(base+overviewVideoPath),false,'Opening the article must not eagerly download the overview video');
      assert.equal(await page.locator('#overview a[download]').getAttribute('href'),overviewVideoPath);
      const articleSections = ['introduction','methods','results','failures','conclusion'];
      assert.deepEqual(await page.locator('.article-body > section').evaluateAll(sections=>sections.map(section=>section.id)),articleSections);
      assert.deepEqual(await page.locator('[aria-label="Article contents"] a').evaluateAll(links=>links.map(link=>link.hash)),articleSections.map(id=>`#${id}`));
      assert.equal(await page.locator('#results #libero #comparison').count(),1);
      assert.equal(await page.locator('#results #robotwin #robotwin-comparison').count(),1);
      assert.equal(await page.locator('#methods #review-note').count(),1);
      assert.equal(await page.locator('#methods #review-accounting').count(),1);
      assert.equal(await page.locator('#failures #failure-cases').count(),1);
      assert.equal(await page.locator('#failures #robotwin-failure-cases').count(),1);
      for (const anchor of ['question','training','instructions','cases']) assert.equal(await page.locator(`#${anchor}`).count(),1,`Preserve the #${anchor} article anchor`);
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
      assert.equal(await page.locator('#failure-cases .failure-case').count(),2);
      assert.equal(await page.locator('#robotwin-failure-cases .failure-case').count(),2);
      assert.equal(await page.locator('#paired-cases video, #failure-cases video').count(),16);
      assert.equal(await page.locator('#robotwin-cases video').count(),robotwin.cases.filter(item=>item.after.benchSuccess).length);
      assert.equal(await page.locator('#robotwin-failure-cases video').count(),2);
      assert.equal(await page.locator('#failures video').count(),4);
      assert.equal(await page.locator('video').count(),22);
      assert.equal(await page.locator('video').evaluateAll(videos=>new Set(videos.map(video=>video.src)).size),22,'The overview and each selected article recording appear once');
      assert.deepEqual((await page.locator('video').evaluateAll(videos=>videos.map(video=>video.src))).sort(),displayedVideoPaths.map(video=>base+video).sort(),'Render the selected failure episodes and preserve all result videos');
      assert.doesNotMatch(await page.locator('#failures').innerText(),/disagreement|agent (?:considers|claims?|claimed|reports)|completion (?:claim|judgment)|bench judges|before:|after:/i,'Failure analysis must focus on physical task difficulty');
      assert.equal(await page.locator('#failures .instruction-comparison, #failures .cross-table').count(),0);
      assert.deepEqual(await page.locator('#failures .task-rate strong').allTextContents(),['20% · 2/10','0% · 0/10','0% · 0/10','40% · 4/10']);
      for (const item of robotwin.cases.filter(item=>item.after.benchSuccess)) {
        const card = page.locator(`#robotwin-cases [data-episode="${item.episodeKey}"]`);
        const instruction = robotwinInstructions.cases.find(record=>record.episodeKey===item.episodeKey);
        assert.equal(await card.count(),1,`Place ${item.episodeKey} according to its actual revised outcome`);
        assert.equal(await card.locator('.instruction-base').textContent(),instruction.revisedBaseInstruction);
        assert.equal(await card.locator('.instruction-goal-criteria').textContent(),instruction.addedGoalSpec);
        assert.equal(await card.locator('.instruction-full').textContent(),instruction.revisedInstruction);
        assert.equal(await card.locator('.instruction-goal-criteria').evaluate(element=>getComputedStyle(element).whiteSpace),'pre-wrap');
        assert.ok((await card.locator('.instruction-provenance').textContent()).includes(instruction.comparisonNote));
        assert.match(await card.locator('.instruction-provenance').textContent(),new RegExp(`Baseline seed ${instruction.baselineSeed}; revised seed ${instruction.revisedSeed}`));
        assert.equal(await card.locator('.instruction-baseline').count(),instruction.sameBaseInstruction ? 0 : 1);
        if (!instruction.sameBaseInstruction) assert.equal(await card.locator('.instruction-baseline').textContent(),instruction.baselineInstruction);
        if (!instruction.sameSceneSeed) assert.match(await card.locator('.instruction-provenance').textContent(),/not a matched-scene instruction-only comparison/);
      }
      for (const episodeKey of selectedRobotwinFailures) {
        const card = page.locator(`#robotwin-failure-cases [data-episode="${episodeKey}"]`);
        const instruction = robotwinInstructions.cases.find(record=>record.episodeKey===episodeKey);
        assert.equal(await card.count(),1);
        assert.equal(await card.locator('.instruction-text').textContent(),`“${instruction.revisedBaseInstruction}”`);
        assert.equal(await card.locator('.instruction-label').textContent(),'Base instruction');
        assert.equal(await card.locator('.clip-header > span:first-child').textContent(),'Goal-spec rerun');
        assert.match(await card.locator('.clip-meta').textContent(),new RegExp(`seed ${instruction.revisedSeed}`));
      }
      assert.deepEqual(await page.locator('#robotwin-comparison .score-top > span').allTextContents(),[robotwin.before,robotwin.after].map(stats=>`n = ${stats.n}`));
      assert.deepEqual(await page.locator('#robotwin-comparison .score-value').allTextContents(),[robotwin.before,robotwin.after].map(stats=>`${(100*stats.instinctAlignment).toFixed(2)}%`));
      const mediaUrls = await page.locator('video').evaluateAll(videos=>videos.flatMap(video=>[video.src,video.poster]));
      assert.equal(mediaUrls.length,44);
      assert.ok(mediaUrls.every(url=>url.startsWith(base+'media/')),'All article videos and posters must load from this site');
      const downloads = await page.locator('.clip-meta a[download]').evaluateAll(links=>links.map(link=>link.href));
      assert.equal(downloads.length,21);
      assert.ok(downloads.every(link=>link.startsWith(base+'media/') && !new URL(link).search),'Article downloads must use local video files');
      assert.ok((await page.locator('[data-gallery-path]').evaluateAll(links=>links.map(link=>link.href))).every(url=>url.startsWith(hosting.galleryUrl) && new URL(url).pathname.endsWith('/index.html')));
      assert.match(await page.locator('#instruction-rows [data-task="libero_goal_t05"]').innerText(),/close to its front edge/);
      assert.match(await page.locator('#instruction-rows [data-task="libero_10_t05"]').innerText(),/between the two large side compartments/);
      for (const id of selectedLiberoFailures) assert.match(await page.locator(`#failure-${id} .clip-meta`).innerText(),/500 control steps/);
      assert.equal(await page.locator('#failure-bottom-drawer-sequence .clip-header > span:first-child').textContent(),'Unchanged instruction · baseline recording');
      assert.equal(await page.locator('#failure-plate-control-budget .clip-header > span:first-child').textContent(),'Revised instruction · revision 2');
      assert.match(await page.locator('#case-book-compartment .clip-meta').first().innerText(),/Agent considers the task complete/);
      assert.match(await page.locator('#case-book-compartment .clip-meta').last().innerText(),/Bench judges success/);
      assert.equal(await page.locator('#review-note').count(),1);
      assert.doesNotMatch(await page.locator('.clip-meta').allTextContents().then(items=>items.join(' ')),/Human review:|Completion: success|Agent: visually complete/);
      assert.ok((await page.locator('#results .clip-header .status').allTextContents()).every(text=>['Bench judges success','Bench judges failure'].includes(text)));
      assert.deepEqual(await page.locator('#failures .clip-header .status').allTextContents(),Array(4).fill('Failed episode'));
      assert.match(await page.locator('#review-accounting').textContent(),/357, 0, and 43/);
      assert.match(await page.locator('#review-accounting').textContent(),/agent considers the task complete and the bench judges failure/);
      assert.doesNotMatch(await page.locator('#review-accounting').textContent(),/human review|adjudication/i);
      assert.match(await page.locator('#case-plate-near-stove .case-detail').innerText(),/8 × 8 cm/);
      assert.match(await page.locator('#case-spatial-regression .case-detail').innerText(),/success → failure/);
      assert.match(await page.locator('#comparison .after .native-score').innerText(),/Bench judges success: 357\/400/);
      // Check every local link; local media is decoded below.
      const links = await page.locator('a[href]').evaluateAll(as => [...new Set(as.map(a => a.href))]);
      for(const link of links) {
        const parsed = new URL(link);
        if(parsed.origin !== origin || parsed.hash || parsed.pathname.endsWith('.mp4')) continue;
        const response = await page.request.head(link);
        assert.equal(response.ok(),true,`Broken link: ${link}`);
      }
      // Decode the overview and all 16 LIBERO and 5 RoboTwin clips while HF media is blocked.
      for(let i=0;i<displayedVideoPaths.length;i++) {
        await page.locator('video').nth(i).evaluate(video => {video.preload='metadata';video.load();});
        await page.waitForFunction(index => {
          const video = document.querySelectorAll('video')[index];
          return video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0 && video.duration > 0;
        },i);
        decoded++;
      }
      const overviewMetadata = await overview.evaluate(video=>({duration:video.duration,width:video.videoWidth,height:video.videoHeight}));
      assert.ok(Math.abs(overviewMetadata.duration-105.133)<0.2,`Unexpected overview duration: ${overviewMetadata.duration}`);
      assert.deepEqual([overviewMetadata.width,overviewMetadata.height],[1920,1080]);
      await overview.evaluate(async video=>{await video.play();});
      await page.waitForFunction(()=>{const video=document.querySelector('#overview-video');return !video.paused && video.currentTime>0;});
      await overview.evaluate(video=>video.pause());
      assert.equal(await overview.evaluate(video=>video.paused),true);
      for(const time of [55,75]) {
        await overview.evaluate((video,time)=>{video.currentTime=time;},time);
        await page.waitForFunction(time=>{const video=document.querySelector('#overview-video');return !video.seeking && video.readyState>=2 && Math.abs(video.currentTime-time)<0.2;},time);
        assert.equal(await overview.evaluate(video=>video.error),null,`Overview cannot seek to the results page at ${time}s`);
      }
      await overview.evaluate(video=>{video.pause();video.currentTime=0;});
      await page.locator('.play-pair').first().click();
      await page.waitForFunction(() => [...document.querySelectorAll('.case:first-child video')].every(v => !v.paused && v.currentTime > 0));
      await page.locator('.play-pair').first().click();
      assert.equal(await page.locator('.case').first().locator('video').evaluateAll(videos => videos.every(v => v.paused)),true);
      await page.locator('.instruction-comparison details').evaluateAll(details => details.forEach(item => { item.open = true; }));
      for(const width of [360,390,768,1440]) {
        await page.setViewportSize({width,height:1000});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true,`Blog overflows at ${width}`);
        const overviewBounds = await overview.boundingBox();
        assert.ok(Math.abs(overviewBounds.width/overviewBounds.height-16/9)<0.01,`Overview must retain its 16:9 frame at ${width}px`);
        assert.ok(overviewBounds.x>=0 && overviewBounds.x+overviewBounds.width<=width,`Overview must fit the viewport at ${width}px`);
      }
      await page.locator('.instruction-comparison details').evaluateAll(details => details.forEach(item => { item.open = false; }));
      if(mount === '/') {
        // Capture the actual initial poster state, without residual native playback UI.
        await page.reload();
        await page.waitForFunction(() => document.documentElement.dataset.blogReady === 'true');
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(output,'desktop-hero.png')});
        await page.locator('#overview').screenshot({path:path.join(output,'desktop-overview.png')});
        await page.locator('#results').screenshot({path:path.join(output,'desktop-results.png')});
        await page.locator('#libero .table-scroll').screenshot({path:path.join(output,'desktop-instructions.png')});
        await page.locator('.case').first().screenshot({path:path.join(output,'desktop-case.png')});
        await page.locator('#failures').screenshot({path:path.join(output,'desktop-failures.png')});
        const robotwinExample = page.locator('#robotwin-cases .robotwin-case').first();
        await robotwinExample.locator('details').first().evaluate(details => { details.open = true; });
        await robotwinExample.screenshot({path:path.join(output,'desktop-robotwin-case.png')});
        await page.setViewportSize({width:390,height:844});
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(output,'mobile-hero.png')});
        await page.locator('#overview').screenshot({path:path.join(output,'mobile-overview.png')});
        await page.locator('#results').screenshot({path:path.join(output,'mobile-results.png')});
        await robotwinExample.screenshot({path:path.join(output,'mobile-robotwin-case.png')});
        await page.locator('#failures').screenshot({path:path.join(output,'mobile-failures.png')});
        await page.locator('#robotwin-failure-cases .robotwin-case').first().screenshot({path:path.join(output,'mobile-robotwin-failure.png')});
        await robotwinExample.locator('details').first().evaluate(details => { details.open = false; });
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
    assert.ok(localMediaRequests.length >= 44,'Article media must load from the local site under both mounts');
    assert.deepEqual(externalMediaRequests,[],'Article playback must not depend on HF media');
    // Escaping remains intact when diff markup encounters punctuation and HTML-like words.
    const escapedData = structuredClone(alignment);
    const escapedTask = escapedData.tasks.find(task=>task.changed);
    escapedTask.instructionBefore = 'place "book" & <caddy> beside the tray';
    escapedTask.instructionAfter = 'place "book" & <caddy> safely beside the tray <img src="x" onerror="throw 1">';
    await page.route('**/data/libero-alignment.json',route=>route.fulfill({json:escapedData}));
    const escapedRobotwin = structuredClone(robotwinInstructions);
    const escapedExample = escapedRobotwin.cases.find(item=>robotwin.cases.some(record=>record.episodeKey===item.episodeKey && record.after.benchSuccess));
    escapedExample.revisedBaseInstruction = 'Lift the "bottle" & <stand>.';
    escapedExample.addedGoalSpec = 'height > 0.90 m; x < 0.15 m\n<img src="x" onerror="throw 1">';
    escapedExample.revisedInstruction = `${escapedExample.revisedBaseInstruction}\n\n${escapedExample.addedGoalSpec}`;
    await page.route('**/data/robotwin-instruction-examples.json',route=>route.fulfill({json:escapedRobotwin}));
    await page.goto(origin + '/');
    await page.waitForFunction(()=>document.documentElement.dataset.blogReady==='true');
    const escapedRow = page.locator(`#instruction-rows [data-task="${escapedTask.id}"]`);
    assert.equal(await escapedRow.locator('.instruction-original').textContent(),escapedTask.instructionBefore);
    assert.equal(await escapedRow.locator('.instruction-improved').textContent(),escapedTask.instructionAfter);
    assert.equal(await escapedRow.locator('img,caddy,script').count(),0);
    const escapedRobotwinCard = page.locator(`[data-episode="${escapedExample.episodeKey}"] .instruction-comparison`);
    assert.equal(await escapedRobotwinCard.locator('.instruction-base').textContent(),escapedExample.revisedBaseInstruction);
    assert.equal(await escapedRobotwinCard.locator('.instruction-goal-criteria').textContent(),escapedExample.addedGoalSpec);
    assert.equal(await escapedRobotwinCard.locator('.instruction-full').textContent(),escapedExample.revisedInstruction);
    assert.equal(await escapedRobotwinCard.locator('img,stand,script').count(),0);
    assert.deepEqual(errors,[]);
    assert.deepEqual(badResponses,[]);
    console.log(`Blog smoke passed: five article sections, two mount paths, 1080p overview playback and seeking, fixed 400-episode comparison, explicit judgment labels in results, 9 exact highlighted LIBERO instructions, 3 verbatim RoboTwin instruction comparisons, escaped markup, 7 LIBERO pairs, 3 RoboTwin successes, 2 LIBERO and 2 RoboTwin physical-task failure examples, ${decoded} local video decodes with HF media blocked, responsive layouts and HF forwarding.`);
  } finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => {console.error(error);process.exitCode=1;});
