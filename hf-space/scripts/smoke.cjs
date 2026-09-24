// Local regression: serve the exported dataset without uploading or modifying it.
// Usage: node hf-space/scripts/smoke.cjs [dataset directory]
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const site = path.resolve(__dirname,'..');
const dataset = path.resolve(process.argv[2] || '/playpen-ssd/tianqizh/benchmend-libero-merged');
const episodes = JSON.parse(fs.readFileSync(path.join(site,'episodes.json'),'utf8'));
const output = path.resolve(__dirname,'../../artifacts/browser/benchmend');
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.mp4':'video/mp4','.jpg':'image/jpeg'};
const server = http.createServer((request,response) => {
  const url = new URL(request.url,'http://localhost');
  const isMedia = url.pathname.startsWith('/media/');
  const root = isMedia ? dataset : site;
  let relative = decodeURIComponent(url.pathname.slice(isMedia ? 7 : 1));
  if (!relative) relative='index.html';
  const file = path.resolve(root,relative);
  if (!file.startsWith(root+path.sep)) {response.writeHead(403).end(); return;}
  try {
    const stat=fs.statSync(file);
    const range=/^bytes=(\d+)-(\d*)$/.exec(request.headers.range||'');
    let start=0,end=stat.size-1;
    const headers={'Content-Type':mime[path.extname(file)]||'application/octet-stream','Accept-Ranges':'bytes'};
    if (range) {start=Number(range[1]);if(range[2])end=Math.min(end,Number(range[2]));headers['Content-Range']=`bytes ${start}-${end}/${stat.size}`;}
    if(start>end){response.writeHead(416).end();return;}
    headers['Content-Length']=end-start+1;
    response.writeHead(range?206:200,headers);
    if(request.method==='HEAD'){response.end();return;}
    const stream=fs.createReadStream(file,{start,end});
    stream.on('error',()=>response.destroy());response.on('close',()=>stream.destroy());stream.pipe(response);
  } catch {response.writeHead(404).end('Not found');}
});

(async()=>{
  fs.mkdirSync(output,{recursive:true});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1050},reducedMotion:'reduce'});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{if(response.status()>=400)errors.push(`${response.status()} ${response.url()}`);});
  await page.addInitScript(base=>{window.GALLERY_MEDIA_BASE=base;},`${origin}/media/`);
  try {
    await page.goto(origin);
    await page.waitForSelector('.task-card');
    assert.equal(await page.locator('.task-card').count(),40);
    assert.equal(await page.locator('.sample-dot').count(),400);
    assert.match(await page.locator('#version-score').innerText(),/322 \/ 400/);
    assert.equal(episodes.length,490);
    assert.equal(await page.locator('#version-tabs button').count(),2);
    assert.doesNotMatch(await page.locator('body').innerText(),/Revision [12]|Final evaluation|\bR[12]\b/);
    for(const [version,count,tasks] of [['revision',90,9],['original',400,40]]){
      await page.locator(`[data-version="${version}"]`).click();
      assert.equal(await page.locator('.sample-dot').count(),count);
      assert.equal(await page.locator('.task-card').count(),tasks);
      if(version==='revision')assert.match(await page.locator('#version-score').innerText(),/75 \/ 90/);
    }
    await page.locator('#suite').selectOption('libero_goal');
    assert.equal(await page.locator('.task-card').count(),10);
    assert.equal(await page.locator('.sample-dot').count(),100);
    await page.locator('#outcome').selectOption('failure');
    const failures=episodes.filter(item=>item.stage==='original'&&item.suite==='libero_goal'&&!item.nativeSuccess);
    assert.equal(await page.locator('.sample-dot').count(),failures.length);
    assert.equal(await page.locator('.sample-dot.success').count(),0);
    await page.locator('#search').fill('unmatched-query-404');
    assert.equal(await page.locator('#empty-state').isVisible(),true);
    await page.locator('#reset-filters').click();
    assert.equal(await page.locator('.sample-dot').count(),400);
    await page.locator('#search').fill('alphabet soup');
    assert.ok((await page.locator('.task-card').count())>0);
    assert.ok((await page.locator('.task-card').count())<40);
    await page.locator('#search').fill('');
    const revised=episodes.find(item=>item.id==='revision/libero_10_t05_r00');
    const original=episodes.find(item=>item.pairKey===revised.pairKey&&item.stage==='original');
    await page.locator(`.sample-dot[data-episode="${original.id}"]`).click();
    await page.waitForFunction(()=>document.querySelector('#episode-video').readyState>=2);
    assert.equal(await page.locator('#player-dialog').isVisible(),true);
    assert.equal(await page.locator('#player-versions button').count(),2);
    assert.ok((await page.locator('#revised-instruction strong').count())>0);
    assert.equal(await page.locator('#original-instruction').innerText(),original.instruction);
    assert.equal(new URL(page.url()).searchParams.get('episode'),original.id);
    await page.locator(`[data-player-episode="${revised.id}"]`).click();
    await page.waitForFunction(()=>document.querySelector('#episode-video').readyState>=2);
    assert.equal(await page.locator('#revised-instruction').innerText(),revised.instruction);
    assert.equal(await page.locator('#player-version').innerText(),'Revision');
    assert.equal(await page.locator('#player-init').innerText(),String(revised.initStateIndex));
    await page.locator('#episode-video').evaluate(async video=>{video.currentTime=Math.min(2,video.duration/2);await video.play();});
    await page.waitForFunction(()=>document.querySelector('#episode-video').currentTime>2.1);
    await page.locator('#episode-video').evaluate(video=>video.pause());
    assert.equal(await page.locator('#video-error').isVisible(),false);
    await page.screenshot({path:path.join(output,'desktop-player.png')});
    await page.locator('#playback-speed').selectOption('2');
    assert.equal(await page.locator('#episode-video').evaluate(video=>video.playbackRate),2);
    const download=new URL(await page.locator('#download-video').getAttribute('href'));
    assert.equal(download.searchParams.get('download'),'true');
    assert.ok(download.pathname.endsWith(revised.video));
    const deepLink=page.url();
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>!document.querySelector('#player-dialog').open);
    assert.equal(new URL(page.url()).searchParams.has('episode'),false);
    await page.goForward();
    await page.waitForFunction(()=>document.querySelector('#player-dialog').open);
    assert.equal(new URL(page.url()).searchParams.get('episode'),revised.id);
    await page.goto(deepLink);
    await page.waitForFunction(()=>document.querySelector('#player-dialog').open);
    assert.equal(await page.locator('#player-version').innerText(),'Revision');
    await page.setViewportSize({width:390,height:844});
    await page.waitForFunction(()=>document.querySelector('#episode-video').readyState>=2);
    assert.equal(await page.evaluate(()=>document.querySelector('dialog').scrollWidth<=document.querySelector('dialog').clientWidth),true);
    await page.screenshot({path:path.join(output,'mobile-player.png')});
    await page.locator('#close-player').click();
    await page.waitForFunction(()=>!document.querySelector('#player-dialog').open);
    for(const width of [360,390,768,1440]){
      await page.setViewportSize({width,height:1000});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`page overflow at ${width}`);
      if([390,1440].includes(width)){
        await page.evaluate(()=>scrollTo(0,0));
        await page.screenshot({path:path.join(output,`${width===390?'mobile':'desktop'}-gallery.png`),fullPage:false});
      }
    }
    await page.locator('[data-version="revision"]').click();
    for(const card of await page.locator('.task-card').all())assert.equal(await card.locator('.sample-dot').count(),10);
    assert.equal(await page.locator('[data-version="revision"]').getAttribute('aria-pressed'),'true');
    // Check the two replaced tasks and an unchanged revised task against their
    // original source bytes, then actually decode, seek and play each selection.
    const retained = [
      ['libero_10_t05_r00','7883e0c077fbbac2a7b2c8c89afdc807b23ec7c85eb8f5bee058cc74be73ab8f','_r2'],
      ['libero_goal_t05_r00','e0fc4527757c63c8a8a168aabff157ea79ce316aa89889e9fb7e9308fe3058b0','_r2'],
      ['libero_10_t06_r00','52948e0fb2d95e6725736195f2faf05b10d530777fc7370004b7f5c1c3843239','_r1']
    ];
    for(const [key,sha,suffix] of retained){
      const episode=episodes.find(item=>item.id===`revision/${key}`);
      assert.ok(episode.sourceRun.endsWith(suffix));
      assert.equal(episode.sha256,sha);
      assert.equal(require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(dataset,episode.video))).digest('hex'),sha);
      const url=new URL(origin);url.searchParams.set('version','revision');url.searchParams.set('episode',episode.id);
      await page.goto(url.href);
      await page.waitForFunction(()=>document.querySelector('#player-dialog').open&&document.querySelector('#episode-video').readyState>=2);
      assert.equal(await page.locator('#player-versions button').count(),2);
      assert.equal(await page.locator('#player-version').innerText(),'Revision');
      assert.equal(await page.locator('#revised-instruction').innerText(),episode.instruction);
      assert.ok((await page.locator('#revised-instruction strong').count())>0);
      const source=await page.locator('#episode-video').getAttribute('src');
      assert.ok(source.endsWith(episode.video));
      await page.locator('#episode-video').evaluate(async video=>{video.currentTime=video.duration/2;await video.play();});
      await page.waitForFunction(()=>{const v=document.querySelector('#episode-video');return v.currentTime>v.duration/2+0.15;});
      await page.locator('#episode-video').evaluate(video=>video.pause());
      assert.equal(await page.locator('#video-error').isVisible(),false);
      assert.doesNotMatch(await page.locator('body').innerText(),/Revision [12]|Final evaluation|\bR[12]\b/);
    }
    // Existing shared links must resolve to the sole public revision.
    for(const oldVersion of ['revised_r1','revised_r2','final']){
      const url=new URL(origin);url.searchParams.set('version',oldVersion);url.searchParams.set('episode',`${oldVersion==='revised_r2'?'revised_r2':'revised_r1'}/${revised.pairKey}`);
      await page.goto(url.href);
      await page.waitForFunction(()=>document.querySelector('#player-dialog').open);
      assert.equal(new URL(page.url()).searchParams.get('version'),'revision');
      assert.equal(new URL(page.url()).searchParams.get('episode'),revised.id);
      assert.equal(await page.locator('#player-version').innerText(),'Revision');
      assert.equal(await page.locator('#revised-instruction').innerText(),revised.instruction);
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: 490 episodes; original 400, revision 90; latest book/plate and retained mug source bytes; legacy links; filters; paired instructions; video play/seek; downloads; URL/back/escape; widths 360/390/768/1440.');
    console.log(`Screenshots: ${output}`);
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
