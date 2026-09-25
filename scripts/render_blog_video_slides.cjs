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
  .results-heading{top:88px}
  .results-benchmark{position:absolute;left:72px;top:179px;margin:0;font-size:31px;line-height:1.3;font-weight:600;letter-spacing:1px;color:var(--green)}
  .score-card{position:absolute;top:267px;width:864px;height:717px;border:1px solid var(--line);border-radius:8px;padding:32px;display:flex;flex-direction:column;background:#faf9f5}
  .score-card.after{background:#edf1e6;border-color:#c4d0ba}
  .score-top h3{font-size:26px;font-weight:600;line-height:32px;color:var(--ink);margin:0}
  .cross-table{border-collapse:collapse;width:100%;font-size:34px;margin:24px 0 0;font-variant-numeric:tabular-nums;table-layout:fixed}
  .cross-table caption{text-align:center;font-size:24px;line-height:31px;color:var(--muted);padding-bottom:24px}
  .cross-table th,.cross-table td{padding:18px 14px;border-bottom:1px solid var(--line);text-align:center;line-height:1.3}
  .cross-table th{font-weight:500;font-size:24px}
  .cross-table th:first-child{text-align:left;padding-left:0;width:44%;line-height:1.35}
  .cross-table thead th:not(:first-child){width:28%}
  .cross-table tbody tr:last-child th,.cross-table tbody tr:last-child td{border-bottom:0}
  .cross-table .mismatch{background:#f0e6dc;color:var(--rust);font-weight:700;border-radius:4px}
  .cross-table .not-applicable{color:var(--muted)}
  .metric-summary{margin-top:auto;border-top:1px solid var(--line);padding-top:28px}
  .metrics-table{width:100%;table-layout:fixed;border-collapse:collapse;text-align:center;font-variant-numeric:tabular-nums}
  .metrics-table th{font-size:24px;line-height:1.35;font-weight:500;padding:0 8px 18px;color:var(--muted)}
  .metrics-table td{font-family:Georgia,'Times New Roman',serif;font-size:73px;line-height:1.2;letter-spacing:-2px;padding:0 8px 10px;color:var(--ink)}
  .score-card.after .metrics-table td{color:var(--green)}
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
  // Keep the published judgment matrix and report its two metrics underneath.
  return `<section class="score-card ${after ? 'after right' : 'before left'}"><div class="score-top"><h3>${after ? 'After' : 'Before'}</h3></div><table class="cross-table"><caption>Agent’s completion judgment × benchmark’s verdict</caption><thead><tr><th scope="col">Agent’s completion judgment</th><th scope="col">Bench judges success</th><th scope="col">Bench judges failure</th></tr></thead><tbody><tr class="success"><th scope="row">Agent considers complete</th><td>${stats.completePass}</td><td class="mismatch">${stats.completeFail}</td></tr><tr class="failure"><th scope="row">Agent does not consider complete</th><td class="not-applicable" aria-label="Not applicable under the reporting convention">&#92;</td><td>${stats.incompleteFail}</td></tr></tbody></table><div class="metric-summary"><table class="metrics-table" aria-label="Summary metrics"><thead><tr><th scope="col">Instinct-alignment score</th><th scope="col">Bench success rate</th></tr></thead><tbody><tr><td>${percent(stats.ias)}</td><td>${percent(stats.native)}</td></tr></tbody></table></div></section>`;
}
function resultsSlide(type) {
  const name = type === 'libero' ? 'LIBERO' : 'RoboTwin';
  const page = type === 'libero' ? '03 / 05' : '04 / 05';
  return frame(`<div class="topline"></div><div class="page">${page}</div><h1 class="results-heading">Clearer instructions, better alignment.</h1><h2 class="results-benchmark">${name}</h2>${scoreCard(manifest[type].before,type,false)}${scoreCard(manifest[type].after,type,true)}`);
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
      const overflow = await page.evaluate(() => Array.from(document.querySelectorAll('.instruction p,.status,.badge,.takeaway-copy,.results-heading,.results-benchmark,.score-card,.score-top,.cross-table,.metric-summary,.metrics-table,.footer')).flatMap(element => {
        const rect = element.getBoundingClientRect();
        return element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1 || rect.bottom > 1080 || rect.right > 1920 ? [element.className || element.tagName] : [];
      }));
      if (overflow.length) throw new Error(`Slide ${relative} has overflowing text: ${overflow.join(', ')}`);
      if (/^results-(libero|robotwin)\.png$/.test(relative)) {
        const type = relative.slice('results-'.length,-'.png'.length);
        const actual = await page.locator('.score-card').evaluateAll(cards => cards.map(card => ({
          headers:Array.from(card.querySelectorAll('.cross-table thead th'),cell=>cell.textContent),
          rows:Array.from(card.querySelectorAll('.cross-table tbody th'),cell=>cell.textContent),
          cells:Array.from(card.querySelectorAll('.cross-table tbody td'),cell=>cell.textContent),
          metrics:Array.from(card.querySelectorAll('.metrics-table th'),cell=>cell.textContent),
          scores:Array.from(card.querySelectorAll('.metrics-table td'),cell=>cell.textContent)
        })));
        const expected = ['before','after'].map(stage => {
          const stats = values(manifest[type][stage],type);
          return {
            headers:['Agent’s completion judgment','Bench judges success','Bench judges failure'],
            rows:['Agent considers complete','Agent does not consider complete'],
            cells:[String(stats.completePass),String(stats.completeFail),'\\',String(stats.incompleteFail)],
            metrics:['Instinct-alignment score','Bench success rate'],
            scores:[percent(stats.ias),percent(stats.native)]
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
