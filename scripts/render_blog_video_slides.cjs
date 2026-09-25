#!/usr/bin/env node
// Render deterministic, offline presentation backgrounds for build_blog_video.py.
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing ${name}`);
  return process.argv[index + 1];
}
const manifest = JSON.parse(fs.readFileSync(argument('--manifest'), 'utf8'));
const output = path.resolve(argument('--output'));
const width = manifest.width || 1920;
const height = manifest.height || 1080;
if (width !== 1920 || height !== 1080) throw new Error('This slide layout requires 1920 × 1080.');
fs.mkdirSync(path.join(output, 'cases'), {recursive: true});

const escape = value => String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const percent = value => `${(Number(value) * 100).toFixed(2)}%`;
const points = (before, after) => `+${((Number(after) - Number(before)) * 100).toFixed(2)} pp`;
const boxes = {left: {x:72,y:470,width:864,height:432}, right: {x:984,y:470,width:864,height:432}};

const css = `
  :root{--paper:#f6f5f0;--ink:#203b2f;--green:#356546;--muted:#717865;--line:#d1d5c8;--wash:#e6eddf;--rust:#9a5337}
  *{box-sizing:border-box}
  html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:var(--paper);color:var(--ink)}
  body{font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased}
  .slide{position:relative;width:1920px;height:1080px}
  .topline{position:absolute;left:72px;right:72px;top:47px;height:5px;background:var(--ink)}
  .eyebrow{position:absolute;left:72px;top:78px;font-size:23px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--muted)}
  h1{position:absolute;left:72px;right:72px;top:119px;margin:0;font-family:Georgia,'Times New Roman',serif;font-size:61px;line-height:1.08;font-weight:400;letter-spacing:-1.4px}
  .page{position:absolute;right:72px;top:82px;font-size:21px;font-variant-numeric:tabular-nums;color:var(--muted)}
  .instruction{position:absolute;top:234px;width:864px;height:210px}
  .left{left:72px}.right{left:984px}
  .label{display:flex;justify-content:space-between;align-items:center;font-size:23px;line-height:29px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;border-bottom:1px solid var(--line);padding-bottom:15px}
  .label span{font-size:18px;letter-spacing:.6px;color:var(--muted);font-weight:400}
  .instruction p{font-size:34px;line-height:1.25;margin:22px 0 0;font-weight:400;letter-spacing:-.35px;max-height:159px}
  .instruction p.long{font-size:30px}
  strong{color:var(--green);font-weight:800}
  .video{position:absolute;top:470px;width:864px;height:432px;background:#101713}
  .status{position:absolute;top:932px;width:864px;display:flex;align-items:center;gap:20px}
  .badge{display:inline-flex;align-items:center;gap:12px;border:1px solid #c7cdbd;border-radius:4px;padding:13px 17px;font-size:22px;font-weight:700;letter-spacing:.6px;white-space:nowrap}
  .badge.fail{color:var(--rust);background:#f1e9df;border-color:#e1cdbb}.badge.pass{color:var(--green);background:var(--wash);border-color:#c9d6c1}
  .badge.agent{color:var(--green);background:var(--wash);border:3px solid var(--green);padding:11px 15px}
  .footer{position:absolute;left:72px;right:72px;top:1020px;border-top:1px solid var(--line);padding-top:15px;display:flex;justify-content:space-between;font-size:20px;color:var(--muted);line-height:24px}
  .deck{position:absolute;left:72px;right:72px;top:195px;margin:0;font-size:27px;line-height:1.3;color:var(--muted)}
  /* Match the blog's before/after IAS cards and 2 × 2 judgment matrices. */
  .score-card{position:absolute;top:251px;width:864px;height:615px;border:1px solid var(--line);border-radius:8px;padding:26px 30px 24px;background:#faf9f5}
  .score-card.after{background:#edf1e6;border-color:#c4d0ba}
  .score-top{display:flex;align-items:center;justify-content:space-between;gap:14px;color:var(--muted);font-size:22px;line-height:29px}
  .score-top h3{font-size:23px;font-weight:600;letter-spacing:0;line-height:29px;color:var(--ink);margin:0}
  .score-top span{white-space:nowrap;font-variant-numeric:tabular-nums}
  .score-value{font-family:Georgia,'Times New Roman',serif;font-size:89px;letter-spacing:-3px;line-height:1.1;margin:14px 0 0}
  .score-value span{font-size:48px}
  .score-label{font-size:22px;line-height:28px;color:var(--muted);margin:0 0 10px}
  .score-equation{font-size:23px;line-height:29px;font-variant-numeric:tabular-nums;padding-bottom:17px;border-bottom:1px solid var(--line);margin:0}
  .cross-table{border-collapse:collapse;width:100%;font-size:29px;margin:20px 0 14px;font-variant-numeric:tabular-nums;table-layout:fixed}
  .cross-table caption{text-align:left;font-size:21px;line-height:27px;color:var(--muted);padding-bottom:13px}
  .cross-table th,.cross-table td{padding:13px 13px;border-bottom:1px solid var(--line);text-align:right;line-height:1.25}
  .cross-table th{font-weight:500;font-size:23px}
  .cross-table th:first-child{text-align:left;padding-left:0;width:44%;line-height:1.35}
  .cross-table thead th:not(:first-child){width:28%}
  .cross-table .mismatch{background:#f0e6dc;color:var(--rust);font-weight:700;border-radius:4px}
  .cross-table .not-applicable{color:var(--muted)}
  .native-score{font-size:23px;line-height:31px;margin:14px 0 0}
  .native-score strong{font-size:26px;color:var(--ink);font-weight:600}
  .result-gains{position:absolute;left:72px;right:72px;top:889px;display:flex;gap:40px;align-items:baseline;font-size:26px;line-height:36px}
  .result-gains>span{flex:1}.result-gains strong{font-size:35px;letter-spacing:-.6px;font-weight:600;margin-left:10px}
  .method-note{position:absolute;left:72px;right:72px;top:944px;margin:0;font-size:21px;line-height:1.4;color:var(--muted)}
  .method-note b{color:var(--ink);font-weight:600}
  .takeaway{position:absolute;left:72px;right:72px;display:flex;gap:33px;padding:27px 0 29px;border-top:1px solid var(--line)}
  .takeaway-number{width:98px;flex-shrink:0;font-family:Georgia,'Times New Roman',serif;font-size:70px;line-height:1;color:var(--green);letter-spacing:-3px}
  .takeaway-copy{padding-top:2px;max-width:1620px}
  .takeaway h2{margin:0 0 15px;font-size:35px;line-height:1.18;font-weight:600;letter-spacing:-.3px}
  .takeaway p{margin:0;font-size:28px;line-height:1.45;color:var(--muted)}
  .closing{position:absolute;left:203px;right:72px;top:872px;padding-top:24px;border-top:1px solid var(--line);font-family:Georgia,'Times New Roman',serif;font-size:41px;font-weight:400;letter-spacing:-.7px}
`;

function frame(body) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><style>${css}</style></head><body><main class="slide">${body}</main></body></html>`;
}
function header(eyebrow, title, page) {
  return `<div class="topline"></div><div class="eyebrow">${escape(eyebrow)}</div><div class="page">${escape(page)}</div><h1>${escape(title)}</h1>`;
}
function caseSlide(item, index, revealed) {
  // revisionHtml is generated by the parent from the exact revised instruction;
  // permit only escaped text and the emphasis tags used for changed words.
  const highlighted = item.revisionHtml || escape(item.revisedInstruction);
  if (/<(?!\/?strong\s*>)[^>]*>/i.test(highlighted)) throw new Error(`Unexpected revision HTML for ${item.id}`);
  const left = `<section class="instruction left"><div class="label">Original instruction</div><p${item.originalInstruction.length > 110 ? ' class="long"' : ''}>${escape(item.originalInstruction)}</p></section>
    <div class="video left"></div><div class="status left"><span class="badge fail">BENCH JUDGE FAIL</span><span class="badge agent">AGENT JUDGE SUCCESS</span></div>`;
  const right = revealed ? `<section class="instruction right"><div class="label">Revised instruction <span>Changed words in bold</span></div><p${item.revisedInstruction.length > 110 ? ' class="long"' : ''}>${highlighted}</p></section><div class="video right"></div><div class="status right"><span class="badge pass">BENCH JUDGE SUCCESS</span><span class="badge agent">AGENT JUDGE SUCCESS</span></div>` : '';
  return frame(`${header(item.label, item.title, `${String(index+1).padStart(2,'0')} / 05`)}${left}${right}<div class="footer"><span>${escape(item.matchLabel)}</span><span>${escape(item.playbackSpeed)}× playback</span></div>`);
}

function values(report, type) {
  if (type === 'libero') return {n:report.n, completePass:report.matrix.success.benchSuccess, completeFail:report.matrix.success.benchFailure, incompleteFail:report.matrix.failure.benchFailure, ias:report.ias, native:report.benchSuccessRate};
  return {n:report.n, completePass:report.agentSuccessBenchSuccess, completeFail:report.agentSuccessBenchFalse, incompleteFail:report.agentFalseBenchFalse, ias:report.instinctAlignment, native:report.benchSuccess / report.n};
}
function scoreCard(report, type, after) {
  const stats = values(report, type);
  const title = type === 'libero'
    ? (after ? 'After · revised composite' : 'Before · original instructions')
    : (after ? 'After · revised composite' : 'Before · original RoboTwin instructions');
  // The matrix labels, reporting-convention cell, and arithmetic mirror blog.js.
  return `<section class="score-card ${after ? 'after right' : 'before left'}"><div class="score-top"><h3>${title}</h3><span>n = ${stats.n}</span></div><p class="score-value">${percent(stats.ias).slice(0,-1)}<span>%</span></p><p class="score-label">Instinct-alignment score</p><p class="score-equation">1 − ${stats.completeFail} / ${stats.n} = ${percent(stats.ias)}</p><table class="cross-table"><caption>Agent’s completion judgment × benchmark’s verdict</caption><thead><tr><th scope="col">Agent’s completion judgment</th><th scope="col">Bench judges success</th><th scope="col">Bench judges failure</th></tr></thead><tbody><tr class="success"><th scope="row">Agent considers complete</th><td>${stats.completePass}</td><td class="mismatch">${stats.completeFail}</td></tr><tr class="failure"><th scope="row">Agent does not consider complete</th><td class="not-applicable" aria-label="Not applicable under the reporting convention">&#92;</td><td>${stats.incompleteFail}</td></tr></tbody></table><p class="native-score">Bench judges success: <strong>${report.benchSuccess}/${stats.n} · ${percent(stats.native)}</strong></p></section>`;
}
function resultsSlide(type) {
  const before = values(manifest[type].before,type), after = values(manifest[type].after,type);
  const name = type === 'libero' ? 'LIBERO' : 'RoboTwin';
  const page = type === 'libero' ? '03 / 05' : '04 / 05';
  const scope = manifest.robotwin.comparisonScope;
  const note = type === 'libero'
    ? '<b>Reviewed 400-episode composite:</b> 310 original + 70 first revision + 20 final revision;<br>one human completion correction. Verifier and recorded demonstrations unchanged.'
    : `<b>${escape(scope.originalEpisodes)} original episodes → ${escape(scope.compositeEpisodes)}-episode composite:</b> ${escape(scope.unchangedOriginalEpisodes)} originals retained + ${escape(scope.replacedOriginalDisagreements)} selected reruns.<br>Disagreements: ${before.completeFail} → ${after.completeFail}. Verifier and recorded demonstrations unchanged.`;
  return frame(`${header(`Results / ${name}`,`${name}: clearer instructions, better alignment.`,page)}<p class="deck">Instruction-layer repairs preserve the benchmark verifier and recorded demonstrations.</p>${scoreCard(manifest[type].before,type,false)}${scoreCard(manifest[type].after,type,true)}<div class="result-gains"><span>Instinct-alignment score <strong>${points(before.ias,after.ias)}</strong></span><span>Benchmark success <strong>${points(before.native,after.native)}</strong></span></div><p class="method-note">${note}</p><div class="footer"><span>Agent as Policy · ${name}</span><span>\\ = not applicable under the reporting convention · pp = percentage points</span></div>`);
}
function takeawaysSlide() {
  const rows = [
    ['Robot benchmarks have instruction–verification gaps.','Some reasonable completions fail because the instruction leaves out conditions checked by the benchmark.'],
    ['Contact-rich precision remains difficult.','GPT-6-Astra performs well on many tasks, but success remains low on some contact-rich tasks requiring precise control. Zero-shot execution is not yet consistently reliable.'],
    ['An imperfect policy can still debug benchmarks.','GPT-6-Astra is not a ground-truth policy, but can expose gaps and guide instruction repairs while preserving demonstrations.']
  ];
  return frame(`${header('Takeaways','What these rollouts reveal.','05 / 05')}${rows.map(([title,body],index)=>`<section class="takeaway" style="top:${251+index*195}px"><div class="takeaway-number">0${index+1}</div><div class="takeaway-copy"><h2>${title}</h2><p>${body}</p></div></section>`).join('')}<div class="closing">Small instruction edits. Better-aligned benchmarks.</div><div class="footer"><span>Agent as Policy</span><span>tianqi-zh.github.io/robot-agent-gallery</span></div>`);
}

(async () => {
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width,height},deviceScaleFactor:1,reducedMotion:'reduce'});
    // No remote fonts, scripts, or other network resources are needed to render.
    await page.route('**/*', route => route.abort());
    async function render(relative, html) {
      await page.setContent(html, {waitUntil:'load'});
      await page.evaluate(() => document.fonts.ready);
      const overflow = await page.evaluate(() => Array.from(document.querySelectorAll('.instruction p,.status,.badge,.takeaway-copy,.score-card,.score-top,.cross-table,.native-score,.result-gains,.method-note,.footer')).flatMap(element => {
        const rect = element.getBoundingClientRect();
        return element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1 || rect.bottom > 1080 || rect.right > 1920 ? [element.className || element.tagName] : [];
      }));
      if (overflow.length) throw new Error(`Slide ${relative} has overflowing text: ${overflow.join(', ')}`);
      if (/^results-(libero|robotwin)\.png$/.test(relative)) {
        const type = relative.slice('results-'.length,-'.png'.length);
        const actual = await page.locator('.score-card').evaluateAll(cards => cards.map(card => ({
          headers:Array.from(card.querySelectorAll('thead th'),cell=>cell.textContent),
          rows:Array.from(card.querySelectorAll('tbody th'),cell=>cell.textContent),
          cells:Array.from(card.querySelectorAll('tbody td'),cell=>cell.textContent),
          ias:card.querySelector('.score-value').textContent,
          equation:card.querySelector('.score-equation').textContent,
          count:card.querySelector('.score-top span').textContent,
          native:card.querySelector('.native-score').textContent
        })));
        const expected = ['before','after'].map(stage => {
          const report = manifest[type][stage], stats = values(report,type);
          return {
            headers:['Agent’s completion judgment','Bench judges success','Bench judges failure'],
            rows:['Agent considers complete','Agent does not consider complete'],
            cells:[String(stats.completePass),String(stats.completeFail),'\\',String(stats.incompleteFail)],
            ias:percent(stats.ias),equation:`1 − ${stats.completeFail} / ${stats.n} = ${percent(stats.ias)}`,
            count:`n = ${stats.n}`,
            native:`Bench judges success: ${report.benchSuccess}/${stats.n} · ${percent(stats.native)}`
          };
        });
        if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`Slide ${relative} does not match the blog's judgment matrices.`);
      }
      await page.screenshot({path:path.join(output,relative),fullPage:false});
      fs.writeFileSync(path.join(output,relative.replace(/\.png$/,'.html')),html);
      process.stdout.write(`Rendered ${relative}\n`);
    }
    for (const [index,item] of manifest.cases.entries()) {
      if (!/^[a-z0-9-]+$/.test(item.id)) throw new Error(`Unsafe case ID: ${item.id}`);
      await render(`cases/${item.id}-before.png`,caseSlide(item,index,false));
      await render(`cases/${item.id}-after.png`,caseSlide(item,index,true));
    }
    await render('results-libero.png',resultsSlide('libero'));
    await render('results-robotwin.png',resultsSlide('robotwin'));
    await render('takeaways.png',takeawaysSlide());
    fs.writeFileSync(path.join(output,'slide-layout.json'),JSON.stringify({width,height,videoBoxes:boxes},null,2)+'\n');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exitCode = 1;});
