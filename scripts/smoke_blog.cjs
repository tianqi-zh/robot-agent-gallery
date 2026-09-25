// Self-contained browser regression for the essay and its legacy gallery links.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const prefix = '/project-preview/robot-agent-gallery/';
const hosting = JSON.parse(fs.readFileSync(path.join(root, 'gallery-hosting.json'), 'utf8'));
const benchmendGallery = 'https://benchmend-gallery.static.hf.space/index.html';
const robotwin = JSON.parse(fs.readFileSync(path.join(root, 'data/robotwin-alignment-summary.json'), 'utf8'));
const liberoMedia = JSON.parse(fs.readFileSync(path.join(root, 'data/libero-blog-media.json'), 'utf8'));
const selectedLiberoTasks = ['libero_goal_t09','libero_10_t05'];
const selectedLiberoPairs = ['wine-rack','book-compartment'];
const selectedLiberoFailures = ['plate-control-budget','bottom-drawer-sequence'];
const selectedRobotwinExamples = ['adjust_bottle_r01','place_object_basket_r01'];
const expectedRobotwinHighlights = {
  adjust_bottle_r01:['keep it upright','move it to the right side of the table.'],
  place_object_basket_r01:['and then lift the basket with the toy car inside.']
};
const selectedRobotwinFailures = ['dump_bin_bigbin_r01','scan_object_r02'];
const displayedRobotwinFailures = robotwin.cases.filter(item=>selectedRobotwinFailures.includes(item.episodeKey));
const overviewVideoPath = 'media/blog/overview/blog-showcase-v4.mp4';
const displayedVideoPaths = [
  overviewVideoPath,
  ...liberoMedia.pairs.filter(pair=>selectedLiberoPairs.includes(pair.id)).flatMap(pair=>[liberoMedia.clips[pair.before].video,liberoMedia.clips[pair.after].video]),
  ...selectedLiberoFailures.map(id=>liberoMedia.clips[liberoMedia.failureCases.find(item=>item.id===id).clip].video),
  ...robotwin.selectedExamples.flatMap(item=>[item.before.video,item.after.video]),
  ...displayedRobotwinFailures.map(item=>item.video)
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
  const exampleTasks = alignment.tasks.filter(task => selectedLiberoTasks.includes(task.id));
  const expectedHighlights = {
    libero_goal_t09:['upper','with','its','base','against','the','lower','rail'],
    libero_10_t05:['between','the','two','large','side','compartments']
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
      assert.equal(await page.title(),'Agent-Guided Instruction Repair for Robotics Benchmarks');
      assert.equal((await page.locator('h1').innerText()).replace(/\s+/g,' ').trim(),'Agent-Guided Instruction Repair for Robotics Benchmarks');
      const overview = page.locator('#overview-video');
      assert.equal(await page.locator('.hero #overview #overview-video').count(),1);
      assert.equal(await page.locator('#overview').evaluate(element => Boolean(element.compareDocumentPosition(document.querySelector('#takeaways')) & Node.DOCUMENT_POSITION_FOLLOWING)),true,'Place the overview before the key takeaways');
      assert.deepEqual(await overview.evaluate(video => ({
        src:video.src,poster:video.poster,controls:video.controls,playsInline:video.playsInline,
        autoplay:video.autoplay,preload:video.preload,width:video.width,height:video.height
      })),{src:base+overviewVideoPath,poster:base+overviewVideoPath.replace('.mp4','.jpg'),controls:true,playsInline:true,autoplay:false,preload:'none',width:1920,height:1080});
      assert.equal(await overview.evaluate(video=>video.paused),true,'The overview must wait for a user to play it');
      assert.equal(localMediaRequests.includes(base+overviewVideoPath),false,'Opening the article must not eagerly download the overview video');
      assert.equal(await page.locator('#overview video a').getAttribute('href'),overviewVideoPath);
      assert.equal(await page.locator('#overview .overview-heading, #overview .overview-duration, #overview figcaption, #overview a[download]').count(),0);
      const articleSections = ['introduction','methods','results','failures','conclusion'];
      assert.deepEqual(await page.locator('.article-body > section').evaluateAll(sections=>sections.map(section=>section.id)),articleSections);
      assert.deepEqual(await page.locator('[aria-label="Article contents"] a').evaluateAll(links=>links.map(link=>link.hash)),articleSections.map(id=>`#${id}`));
      assert.equal(await page.locator('#results #libero #comparison').count(),1);
      assert.equal(await page.locator('#results #robotwin #robotwin-comparison').count(),1);
      assert.equal(await page.locator('#methods #review-note').count(),1);
      assert.equal(await page.locator('#review-accounting, #methods details, #conclusion details').count(),0);
      assert.equal(await page.locator('#methods > .prose').first().getByText('All stages requested gpt-6-astra with high reasoning.', {exact:true}).count(),1);
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
      assert.deepEqual(await page.locator('#instruction-rows tr').evaluateAll(rows=>rows.map(row=>row.dataset.task)),selectedLiberoTasks);
      assert.equal(await page.locator('#instruction-rows .revision-label').count(),0);
      for (const task of exampleTasks) {
        const row = page.locator(`#instruction-rows [data-task="${task.id}"]`);
        assert.equal(await row.locator('.instruction-original').textContent(),task.instructionBefore);
        assert.equal(await row.locator('.instruction-original *').count(),0,'Original instruction must be unformatted');
        assert.equal(await row.locator('.instruction-improved').textContent(),task.instructionAfter,'Highlighting must preserve exact instruction text');
        assert.deepEqual(await row.locator('.instruction-improved strong').allTextContents(),expectedHighlights[task.id],task.id);
        assert.equal(await row.locator('.instruction-improved :not(strong)').count(),0);
      }
      assert.deepEqual(await page.locator('#paired-cases .case').evaluateAll(cases=>cases.map(item=>item.id)),selectedLiberoPairs.map(id=>`case-${id}`));
      assert.equal(await page.locator('.failure-case').count(),4);
      assert.equal(await page.locator('#failure-cases .failure-case').count(),2);
      assert.equal(await page.locator('#robotwin-failure-cases .failure-case').count(),2);
      assert.equal(await page.locator('#paired-cases video, #failure-cases video').count(),6);
      assert.equal(await page.locator('#robotwin-cases video').count(),4);
      assert.equal(await page.locator('#robotwin-failure-cases video').count(),2);
      assert.equal(await page.locator('#failures video').count(),4);
      assert.equal(await page.locator('video').count(),13);
      assert.equal(await page.locator('video').evaluateAll(videos=>new Set(videos.map(video=>video.src)).size),13,'The overview and each selected article recording appear once');
      assert.deepEqual((await page.locator('video').evaluateAll(videos=>videos.map(video=>video.src))).sort(),displayedVideoPaths.map(video=>base+video).sort(),'Render only the selected result and failure episodes');
      assert.doesNotMatch(await page.locator('#failures').innerText(),/disagreement|agent (?:considers|claims?|claimed|reports)|completion (?:claim|judgment)|bench judges|before:|after:/i,'Failure analysis must focus on physical task difficulty');
      assert.equal(await page.locator('#failures .instruction-comparison, #failures .cross-table').count(),0);
      assert.deepEqual(await page.locator('#failures .task-rate strong').allTextContents(),['0% → 20%','0% → 0%','10% → 10%','10% → 20%']);
      assert.equal(await page.locator('#robotwin-summary-grid').count(),0);
      assert.deepEqual(await page.locator('#robotwin-instruction-rows tr').evaluateAll(rows=>rows.map(row=>row.dataset.episode)),selectedRobotwinExamples);
      assert.deepEqual(await page.locator('#robotwin-cases .case').evaluateAll(cards=>cards.map(card=>card.dataset.episode)),selectedRobotwinExamples);
      for (const item of robotwin.selectedExamples) {
        const row = page.locator(`#robotwin-instruction-rows [data-episode="${item.episodeKey}"]`);
        assert.equal(await row.locator('.instruction-original').textContent(),item.before.instruction);
        assert.equal(await row.locator('.instruction-original *').count(),0,'Original instruction must be unformatted');
        assert.equal(await row.locator('.instruction-improved').textContent(),item.after.instruction,'Highlighting must preserve exact instruction text');
        assert.deepEqual(await row.locator('.instruction-improved strong').allTextContents(),expectedRobotwinHighlights[item.episodeKey]);
        assert.equal(await row.locator('.instruction-improved :not(strong)').count(),0);
        assert.equal(await row.locator('td').last().textContent(),'failure → success');
        const card = page.locator(`#robotwin-cases [data-episode="${item.episodeKey}"]`);
        assert.equal(await card.count(),1,`Place ${item.episodeKey} according to its actual revised outcome`);
        assert.equal(await card.locator('.instruction-comparison').count(),0);
        assert.equal(await card.locator('.eyebrow').textContent(),`RoboTwin · Task ${String(item.taskId).padStart(2,'0')} · EPISODE ${String(item.episodeNumber).padStart(2,'0')}`);
        assert.equal(await card.locator('.task-rate strong').textContent(),'failure → success');
        assert.deepEqual(await card.locator('.clip-instruction').allTextContents(),[item.before,item.after].map(clip=>`“${clip.instruction}”`));
        assert.deepEqual(await card.locator('.clip-header .status').allTextContents(),['Bench judges failure','Bench judges success']);
        assert.deepEqual(await card.locator('video').evaluateAll(videos=>videos.map(video=>video.src)),[item.before,item.after].map(clip=>base+clip.video));
        assert.equal(await card.locator('.case-source a').getAttribute('href'),item.galleryUrl);
        assert.equal(item.before.seed,item.after.seed,'Paired recordings must use the same scene');
      }
      for (const episodeKey of selectedRobotwinFailures) {
        const card = page.locator(`#robotwin-failure-cases [data-episode="${episodeKey}"]`);
        const item = robotwin.cases.find(record=>record.episodeKey===episodeKey);
        assert.equal(await card.count(),1);
        assert.equal(await card.locator('.eyebrow').textContent(),item.label);
        assert.equal(await card.locator('.failure-description a').getAttribute('href'),item.galleryUrl);
        for (const phase of ['before','after']) {
          const rows = robotwin.episodes.filter(row=>row.task===item.taskName);
          assert.equal(item.task[phase].episodes,rows.length);
          assert.equal(item.task[phase].successes,rows.filter(row=>row[phase].nativeSuccess).length);
        }
        assert.equal(await card.locator('.task-rate > span:last-child').textContent(),`${item.task.before.successes}/10 → ${item.task.after.successes}/10 episodes`);
        assert.equal(await card.locator('.instruction-text').textContent(),`“${item.instruction}”`);
        assert.equal(await card.locator('.instruction-label').textContent(),'Task instruction');
        assert.equal(await card.locator('.clip-header > span:first-child').textContent(),'Revision');
        assert.match(await card.locator('.clip-meta').textContent(),new RegExp(`seed ${item.seed}`));
      }
      assert.deepEqual(await page.locator('#robotwin-comparison .score-top > span').allTextContents(),[robotwin.before,robotwin.after].map(stats=>`n = ${stats.n}`));
      assert.deepEqual(await page.locator('#robotwin-results-note strong').allTextContents(),[
        `${robotwin.before.benchSuccess}/${robotwin.before.n} to ${robotwin.after.benchSuccess}/${robotwin.after.n}`,
        `${robotwin.rerunsOnly.nativeSuccesses} now pass the benchmark`
      ]);
      assert.deepEqual(await page.locator('#robotwin-comparison .score-value').allTextContents(),[robotwin.before,robotwin.after].map(stats=>stats.agentUnknownBenchFalse ? `${(100*stats.instinctAlignmentBounds.min).toFixed(2)}–${(100*stats.instinctAlignmentBounds.max).toFixed(2)}%` : `${(100*stats.instinctAlignment).toFixed(2)}%`));
      assert.equal(await page.locator('#robotwin-comparison .unclassified').count(),robotwin.after.agentUnknownBenchFalse ? 1 : 0);
      if (robotwin.after.agentUnknownBenchFalse) assert.equal(await page.locator('#robotwin-comparison .unclassified td:last-child').textContent(),String(robotwin.after.agentUnknownBenchFalse));
      const mediaUrls = await page.locator('video').evaluateAll(videos=>videos.flatMap(video=>[video.src,video.poster]));
      assert.equal(mediaUrls.length,26);
      assert.ok(mediaUrls.every(url=>url.startsWith(base+'media/')),'All article videos and posters must load from this site');
      const downloads = await page.locator('.clip-meta a[download]').evaluateAll(links=>links.map(link=>link.href));
      assert.equal(downloads.length,12);
      assert.ok(downloads.every(link=>link.startsWith(base+'media/') && !new URL(link).search),'Article downloads must use local video files');
      assert.equal(await page.locator('[data-gallery-path]').count(),0);
      assert.deepEqual(await page.locator('[data-benchmend-gallery]').evaluateAll(links=>links.map(link=>({href:link.href,legacy:link.hasAttribute('data-gallery-path')}))),Array(2).fill({href:benchmendGallery,legacy:false}),'Main and sidebar entries must retain the gallery URL after legacy hosting initializes');
      assert.equal(await page.locator('.contents-gallery').textContent(),'Browse gallery on HF');
      assert.equal(await page.locator('.explore, .site-footer').count(),0);
      assert.match(await page.locator('#instruction-rows [data-task="libero_goal_t09"]').innerText(),/upper rack, with its base against the lower rail/);
      assert.match(await page.locator('#instruction-rows [data-task="libero_10_t05"]').innerText(),/between the two large side compartments/);
      for (const id of selectedLiberoFailures) assert.match(await page.locator(`#failure-${id} .clip-meta`).innerText(),/500 control steps/);
      assert.equal(await page.locator('#failure-bottom-drawer-sequence .clip-header > span:first-child').textContent(),'Unchanged instruction · baseline recording');
      assert.equal(await page.locator('#failure-plate-control-budget .clip-header > span:first-child').textContent(),'Revised instruction · revision 2');
      assert.match(await page.locator('#case-wine-rack .clip-meta').first().innerText(),/Agent considers the task complete/);
      assert.match(await page.locator('#case-wine-rack .clip-meta').last().innerText(),/Bench judges success/);
      assert.equal(await page.locator('#review-note').count(),1);
      assert.doesNotMatch(await page.locator('.clip-meta').allTextContents().then(items=>items.join(' ')),/Human review:|Completion: success|Agent: visually complete/);
      assert.ok((await page.locator('#results .clip-header .status').allTextContents()).every(text=>['Bench judges success','Bench judges failure'].includes(text)));
      assert.deepEqual(await page.locator('#failures .clip-header .status').allTextContents(),Array(4).fill('Failed episode'));
      assert.deepEqual(await page.locator('#paired-cases .task-rate strong').allTextContents(),['7/10 → 10/10','0/10 → 10/10']);
      assert.deepEqual(await page.locator('#paired-cases .eyebrow').allTextContents(),['LIBERO Goal · Task 09 · EPISODE 04','LIBERO Long · Task 05 · EPISODE 01']);
      assert.deepEqual(await page.locator('#case-wine-rack .clip-header .status').allTextContents(),['Bench judges failure','Bench judges success']);
      assert.ok((await page.locator('#case-wine-rack .clip-meta').allTextContents()).every(text=>text.includes('seed 3 · init 3')));
      assert.deepEqual(await page.locator('#case-book-compartment .clip-header .status').allTextContents(),['Bench judges failure','Bench judges success']);
      assert.match(await page.locator('#case-book-compartment .clip-meta').first().innerText(),/Agent considers the task complete/);
      assert.ok((await page.locator('#case-book-compartment .clip-meta').allTextContents()).every(text=>text.includes('seed 0 · init 0')));
      assert.match(await page.locator('#comparison .after .native-score').innerText(),/Bench judges success: 357\/400/);
      // Check every local link; local media is decoded below.
      const links = await page.locator('a[href]').evaluateAll(as => [...new Set(as.map(a => a.href))]);
      for(const link of links) {
        const parsed = new URL(link);
        if(parsed.origin !== origin || parsed.hash || parsed.pathname.endsWith('.mp4')) continue;
        const response = await page.request.head(link);
        assert.equal(response.ok(),true,`Broken link: ${link}`);
      }
      // Decode the overview and all 6 LIBERO and 6 RoboTwin clips while HF media is blocked.
      for(let i=0;i<displayedVideoPaths.length;i++) {
        await page.locator('video').nth(i).evaluate(video => {video.preload='metadata';video.load();});
        await page.waitForFunction(index => {
          const video = document.querySelectorAll('video')[index];
          return video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0 && video.duration > 0;
        },i);
        decoded++;
      }
      const overviewMetadata = await overview.evaluate(video=>({duration:video.duration,width:video.videoWidth,height:video.videoHeight}));
      assert.ok(Math.abs(overviewMetadata.duration-98.9)<0.2,`Unexpected overview duration: ${overviewMetadata.duration}`);
      assert.deepEqual([overviewMetadata.width,overviewMetadata.height],[1920,1080]);
      await overview.evaluate(async video=>{await video.play();});
      await page.waitForFunction(()=>{const video=document.querySelector('#overview-video');return !video.paused && video.currentTime>0;});
      await overview.evaluate(video=>video.pause());
      assert.equal(await overview.evaluate(video=>video.paused),true);
      for(const time of [50,68,86]) {
        await overview.evaluate((video,time)=>{video.currentTime=time;},time);
        await page.waitForFunction(time=>{const video=document.querySelector('#overview-video');return !video.seeking && video.readyState>=2 && Math.abs(video.currentTime-time)<0.2;},time);
        assert.equal(await overview.evaluate(video=>video.error),null,`Overview cannot seek to the results page at ${time}s`);
      }
      await overview.evaluate(video=>{video.pause();video.currentTime=0;});
      for (const container of ['#paired-cases','#robotwin-cases']) {
        const pair = page.locator(`${container} .case`).first();
        await pair.locator('.play-pair').click();
        await page.waitForFunction(selector => [...document.querySelector(selector).querySelectorAll('video')].every(video => !video.paused && video.currentTime > 0),`${container} .case`);
        await pair.locator('.play-pair').click();
        assert.equal(await pair.locator('video').evaluateAll(videos => videos.every(video => video.paused)),true);
      }
      for(const width of [360,390,768,1440]) {
        await page.setViewportSize({width,height:1000});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true,`Blog overflows at ${width}`);
        const overviewBounds = await overview.boundingBox();
        assert.ok(Math.abs(overviewBounds.width/overviewBounds.height-16/9)<0.01,`Overview must retain its 16:9 frame at ${width}px`);
        assert.ok(overviewBounds.x>=0 && overviewBounds.x+overviewBounds.width<=width,`Overview must fit the viewport at ${width}px`);
      }
      if(mount === '/') {
        // Capture the actual initial poster state, without residual native playback UI.
        await page.reload();
        await page.waitForFunction(() => document.documentElement.dataset.blogReady === 'true');
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(output,'desktop-hero.png')});
        await page.locator('#overview').screenshot({path:path.join(output,'desktop-overview.png')});
        await page.locator('#results').screenshot({path:path.join(output,'desktop-results.png')});
        await page.locator('#libero .table-scroll').screenshot({path:path.join(output,'desktop-instructions.png')});
        await page.locator('#robotwin .table-scroll').screenshot({path:path.join(output,'desktop-robotwin-instructions.png')});
        await page.locator('#robotwin-comparison').screenshot({path:path.join(output,'desktop-robotwin-comparison.png')});
        await page.locator('.case').first().screenshot({path:path.join(output,'desktop-case.png')});
        await page.locator('#failures').screenshot({path:path.join(output,'desktop-failures.png')});
        const robotwinExample = page.locator('#robotwin-cases .robotwin-case').first();
        await robotwinExample.screenshot({path:path.join(output,'desktop-robotwin-case.png')});
        await page.setViewportSize({width:390,height:844});
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(output,'mobile-hero.png')});
        await page.locator('#overview').screenshot({path:path.join(output,'mobile-overview.png')});
        await page.locator('#results').screenshot({path:path.join(output,'mobile-results.png')});
        await robotwinExample.screenshot({path:path.join(output,'mobile-robotwin-case.png')});
        await page.locator('#failures').screenshot({path:path.join(output,'mobile-failures.png')});
        await page.locator('#robotwin-failure-cases .robotwin-case').first().screenshot({path:path.join(output,'mobile-robotwin-failure.png')});
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
    for (const mount of ['/',prefix]) {
      await fallbackPage.goto(`${origin}${mount}`);
      assert.deepEqual(await fallbackPage.locator('[data-benchmend-gallery]').evaluateAll(links=>links.map(link=>link.href)),Array(3).fill(benchmendGallery),'All three BenchMend entries, including noscript, must work without JavaScript');
    }
    await fallbackPage.goto(`${origin}${prefix}gallery/robotwin_nvidia10/`);
    assert.equal(await fallbackPage.locator('[data-gallery-path]').getAttribute('href'),`${hosting.galleryUrl}gallery/robotwin/index.html`);
    await noScript.close();
    assert.ok(localMediaRequests.length >= 26,'Article media must load from the local site under both mounts');
    assert.deepEqual(externalMediaRequests,[],'Article playback must not depend on HF media');
    // Escaping remains intact when diff markup encounters punctuation and HTML-like words.
    const escapedData = structuredClone(alignment);
    const escapedTask = escapedData.tasks.find(task=>task.id===selectedLiberoTasks[0]);
    escapedTask.instructionBefore = 'place "book" & <caddy> beside the tray';
    escapedTask.instructionAfter = 'place "book" & <caddy> safely beside the tray <img src="x" onerror="throw 1">';
    await page.route('**/data/libero-alignment.json',route=>route.fulfill({json:escapedData}));
    const escapedRobotwinSummary = structuredClone(robotwin);
    const escapedPair = escapedRobotwinSummary.selectedExamples[0];
    escapedPair.before.instruction = 'Lift the "bottle" & <stand>.';
    escapedPair.after.instruction = 'Lift the "bottle" & <stand> higher <img src="x" onerror="throw 1">.';
    const escapedExample = escapedRobotwinSummary.cases.find(item=>item.episodeKey===selectedRobotwinFailures[0]);
    escapedExample.instruction = 'Lift the "bin" & <container> over the tray <img src="x" onerror="throw 1">.';
    await page.route('**/data/robotwin-alignment-summary.json',route=>route.fulfill({json:escapedRobotwinSummary}));
    await page.goto(origin + '/');
    await page.waitForFunction(()=>document.documentElement.dataset.blogReady==='true');
    const escapedRow = page.locator(`#instruction-rows [data-task="${escapedTask.id}"]`);
    assert.equal(await escapedRow.locator('.instruction-original').textContent(),escapedTask.instructionBefore);
    assert.equal(await escapedRow.locator('.instruction-improved').textContent(),escapedTask.instructionAfter);
    assert.equal(await escapedRow.locator('img,caddy,script').count(),0);
    const escapedPairRow = page.locator(`#robotwin-instruction-rows [data-episode="${escapedPair.episodeKey}"]`);
    assert.equal(await escapedPairRow.locator('.instruction-original').textContent(),escapedPair.before.instruction);
    assert.equal(await escapedPairRow.locator('.instruction-improved').textContent(),escapedPair.after.instruction);
    assert.equal(await escapedPairRow.locator('img,stand,script').count(),0);
    const escapedPairCard = page.locator(`#robotwin-cases [data-episode="${escapedPair.episodeKey}"]`);
    assert.deepEqual(await escapedPairCard.locator('.clip-instruction').allTextContents(),[escapedPair.before,escapedPair.after].map(clip=>`“${clip.instruction}”`));
    assert.equal(await escapedPairCard.locator('img,stand,script').count(),0);
    const escapedRobotwinCard = page.locator(`#robotwin-failure-cases [data-episode="${escapedExample.episodeKey}"]`);
    assert.equal(await escapedRobotwinCard.locator('.instruction-text').textContent(),`“${escapedExample.instruction}”`);
    assert.equal(await escapedRobotwinCard.locator('img,container,script').count(),0);
    assert.deepEqual(errors,[]);
    assert.deepEqual(badResponses,[]);
    console.log(`Blog smoke passed: five article sections, two mount paths, 1080p overview playback and seeking, fixed 400-episode comparison, explicit judgment labels in results, 2 exact highlighted instruction examples per benchmark, escaped markup, 2 LIBERO and 2 RoboTwin video pairs, 2 LIBERO and 2 RoboTwin physical-task failure examples, ${decoded} local video decodes with HF media blocked, responsive layouts and HF forwarding.`);
  } finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => {console.error(error);process.exitCode=1;});
