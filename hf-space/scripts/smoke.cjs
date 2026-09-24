// Local regression: serve the exported dataset without uploading or modifying it.
// Usage: node hf-space/scripts/smoke.cjs [dataset directory]
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const site = path.resolve(__dirname,'..');
const dataset = path.resolve(process.argv[2] || '/playpen-ssd/tianqizh/benchmend-libero');
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
    for(const [version,count,tasks] of [['revised_r1',90,9],['revised_r2',20,2],['final',400,40],['original',400,40]]){
      await page.locator(`[data-version="${version}"]`).click();
      assert.equal(await page.locator('.sample-dot').count(),count);
      assert.equal(await page.locator('.task-card').count(),tasks);
      if(version==='final')assert.match(await page.locator('#version-score').innerText(),/357 \/ 400/);
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
    const revised=episodes.find(item=>item.stage==='revised_r2');
    const original=episodes.find(item=>item.pairKey===revised.pairKey&&item.stage==='original');
    await page.locator(`.sample-dot[data-episode="${original.id}"]`).click();
    await page.waitForFunction(()=>document.querySelector('#episode-video').readyState>=2);
    assert.equal(await page.locator('#player-dialog').isVisible(),true);
    assert.equal(await page.locator('#player-versions button').count(),3);
    assert.ok((await page.locator('#revised-instruction strong').count())>0);
    assert.equal(await page.locator('#original-instruction').innerText(),original.instruction);
    assert.equal(new URL(page.url()).searchParams.get('episode'),original.id);
    await page.locator(`[data-player-episode="${revised.id}"]`).click();
    await page.waitForFunction(()=>document.querySelector('#episode-video').readyState>=2);
    assert.equal(await page.locator('#revised-instruction').innerText(),revised.instruction);
    assert.equal(await page.locator('#player-version').innerText(),'Revision 2');
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
    assert.equal(await page.locator('#player-version').innerText(),'Revision 2');
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
    await page.locator('[data-version="final"]').click();
    for(const card of await page.locator('.task-card').all())assert.equal(await card.locator('.sample-dot').count(),10);
    assert.equal(await page.locator('[data-version="final"]').getAttribute('aria-pressed'),'true');
    assert.deepEqual(errors,[]);
    console.log('PASS: 510 episodes; original 400, r1 90, r2 20, final 400; filters; paired instructions; video play/seek; downloads; URL/back/escape; widths 360/390/768/1440.');
    console.log(`Screenshots: ${output}`);
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
