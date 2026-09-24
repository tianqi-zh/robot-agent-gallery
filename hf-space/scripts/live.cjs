// Anonymous, bounded playback check against the published static Space.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.argv[2]||'https://benchmend-gallery.static.hf.space/index.html';
const output=path.resolve(__dirname,'../../artifacts/browser/benchmend');
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const report={url:base,checkedAt:new Date().toISOString(),anonymous:true,versions:{},videos:[],legacyLinks:[],errors:[]};
  page.on('pageerror',error=>report.errors.push({type:'javascript',message:error.message}));
  page.on('response',response=>{if(response.status()>=400){const url=new URL(response.url());report.errors.push({type:'http',status:response.status(),url:url.origin+url.pathname});}});
  try {
    await page.goto(base,{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForSelector('.sample-dot',{timeout:60000});
    assert.equal(await page.locator('.sample-dot').count(),400);
    const episodes=await page.evaluate(async()=>{const response=await fetch('episodes.json');return response.json();});
    assert.equal(episodes.length,490);
    assert.equal(await page.locator('#version-tabs button').count(),2);
    assert.doesNotMatch(await page.locator('body').innerText(),/Revision [12]|Final evaluation|\bR[12]\b/);
    const expectedMediaBase=fs.readFileSync(path.join(__dirname,'../media-hosting.js'),'utf8').match(/https:\/\/huggingface\.co\/datasets\/benchmend\/libero\/resolve\/[a-f0-9]{40}\//)?.[0];
    assert.ok(expectedMediaBase,'Local source must pin an immutable dataset revision');
    assert.equal(await page.evaluate(()=>window.GALLERY_MEDIA_BASE),expectedMediaBase);
    for(const [stage,count] of [['original',400],['revision',90]]){
      await page.locator(`[data-version="${stage}"]`).click();
      report.versions[stage]=await page.locator('.sample-dot').count();
      assert.equal(report.versions[stage],count);
    }
    for(const [id,sourceSuffix] of [
      ['original/libero_10_t05_r00',null],
      ['revision/libero_10_t05_r00','_r2'],
      ['revision/libero_goal_t05_r00','_r2'],
      ['revision/libero_10_t06_r00','_r1']
    ]){
      const episode=episodes.find(item=>item.id===id);
      const stage=episode.stage;
      if(sourceSuffix)assert.ok(episode.sourceRun.endsWith(sourceSuffix));
      const url=new URL(base);url.searchParams.set('version',stage);url.searchParams.set('episode',episode.id);
      await page.goto(url.href,{waitUntil:'domcontentloaded',timeout:60000});
      await page.waitForFunction(()=>document.querySelector('#player-dialog').open&&document.querySelector('#episode-video').readyState>=2,{},{timeout:60000});
      await page.locator('#episode-video').evaluate(async video=>{
        video.currentTime=Math.min(video.duration*0.55,video.duration-2);
        await video.play();
      });
      await page.waitForFunction(()=>{const video=document.querySelector('#episode-video');return video.currentTime>video.duration*0.55+0.15;},{},{timeout:60000});
      const probe=await page.locator('#episode-video').evaluate(video=>{video.pause();return {duration:video.duration,width:video.videoWidth,height:video.videoHeight,currentTime:video.currentTime,readyState:video.readyState,error:video.error?.message||null};});
      assert.ok(probe.width>0&&probe.height>0);
      assert.ok(Math.abs(probe.duration-episode.duration)<0.2);
      assert.equal(probe.error,null);
      assert.equal(await page.locator('#video-error').isVisible(),false);
      assert.equal(await page.locator('#player-versions button').count(),2);
      assert.equal(await page.locator('#player-version').innerText(),stage==='original'?'Original':'Revision');
      assert.ok((await page.locator('#revised-instruction strong').count())>0);
      assert.doesNotMatch(await page.locator('body').innerText(),/Revision [12]|Final evaluation|\bR[12]\b/);
      report.videos.push({id:episode.id,...probe});
    }
    await page.screenshot({path:path.join(output,'live-desktop-player.png')});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.querySelector('dialog').scrollWidth<=document.querySelector('dialog').clientWidth),true);
    await page.screenshot({path:path.join(output,'live-mobile-player.png')});
    await page.locator('#close-player').click();
    await page.waitForFunction(()=>!document.querySelector('#player-dialog').open);
    assert.equal(new URL(page.url()).searchParams.has('episode'),false);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:path.join(output,'live-mobile-gallery.png')});
    for(const legacyVersion of ['revised_r1','revised_r2','final']){
      const url=new URL(base);
      url.searchParams.set('version',legacyVersion);
      url.searchParams.set('episode',`${legacyVersion==='revised_r2'?'revised_r2':'revised_r1'}/libero_10_t05_r00`);
      await page.goto(url.href,{waitUntil:'domcontentloaded',timeout:60000});
      await page.waitForFunction(()=>document.querySelector('#player-dialog').open&&document.querySelector('#episode-video').readyState>=2,{},{timeout:60000});
      const canonical=new URL(page.url());
      assert.equal(canonical.searchParams.get('version'),'revision');
      assert.equal(canonical.searchParams.get('episode'),'revision/libero_10_t05_r00');
      assert.equal(await page.locator('#episode-video').getAttribute('src'),`${expectedMediaBase}revision/videos/libero_10_t05_r00.mp4`);
      assert.equal(await page.locator('#player-version').innerText(),'Revision');
      assert.equal(await page.locator('#player-versions button').count(),2);
      assert.equal(await page.locator('.sample-dot').count(),90);
      report.legacyLinks.push({version:legacyVersion,resolved:canonical.href});
    }
    assert.deepEqual(report.errors,[]);
    report.passed=true;
    console.log('PASS: anonymous live Space; 400/90 counts; original plus latest book/plate and retained mug videos play and seek; legacy links; mobile fit; no JavaScript or HTTP errors.');
  } catch(error){report.passed=false;report.failure=error.stack;throw error;}
  finally{fs.writeFileSync(path.join(output,'live-report.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
