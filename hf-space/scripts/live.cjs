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
  const report={url:base,checkedAt:new Date().toISOString(),anonymous:true,versions:{},videos:[],errors:[]};
  page.on('pageerror',error=>report.errors.push({type:'javascript',message:error.message}));
  page.on('response',response=>{if(response.status()>=400){const url=new URL(response.url());report.errors.push({type:'http',status:response.status(),url:url.origin+url.pathname});}});
  try {
    await page.goto(base,{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForSelector('.sample-dot',{timeout:60000});
    assert.equal(await page.locator('.sample-dot').count(),400);
    const episodes=await page.evaluate(async()=>{const response=await fetch('episodes.json');return response.json();});
    assert.equal(episodes.length,510);
    assert.equal(await page.evaluate(()=>window.GALLERY_MEDIA_BASE),'https://huggingface.co/datasets/benchmend/libero/resolve/779ffbf66acdb6620e421937d3053f4cca4c0cef/');
    for(const [stage,count] of [['original',400],['revised_r1',90],['revised_r2',20],['final',400]]){
      await page.locator(`[data-version="${stage}"]`).click();
      report.versions[stage]=await page.locator('.sample-dot').count();
      assert.equal(report.versions[stage],count);
    }
    const revised=episodes.find(item=>item.stage==='revised_r2');
    for(const stage of ['original','revised_r1','revised_r2']){
      const episode=episodes.find(item=>item.stage===stage&&item.pairKey===revised.pairKey);
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
    assert.deepEqual(report.errors,[]);
    report.passed=true;
    console.log('PASS: anonymous live Space; 400/90/20/400 counts; actual original/R1/R2 videos play and seek; deep links; mobile fit; no JavaScript or HTTP errors.');
  } catch(error){report.passed=false;report.failure=error.stack;throw error;}
  finally{fs.writeFileSync(path.join(output,'live-report.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
