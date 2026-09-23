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
  strong{color:var(--green);font-weight:800}
  .video{position:absolute;top:470px;width:864px;height:432px;background:#101713}
  .status{position:absolute;top:932px;width:864px;display:flex;align-items:center;justify-content:space-between;gap:15px}
  .badge{display:inline-flex;align-items:center;gap:12px;border:1px solid #c7cdbd;border-radius:4px;padding:13px 17px;font-size:22px;font-weight:700;letter-spacing:.6px;white-space:nowrap}
  .badge.fail{color:var(--rust);background:#f1e9df;border-color:#e1cdbb}.badge.pass{color:var(--green);background:var(--wash);border-color:#c9d6c1}
  .assessment{font-size:21px;color:var(--muted);line-height:1.2}
  .rate{font-size:24px;font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
  .rate b{font-size:33px;font-weight:700;color:var(--green)}
  .footer{position:absolute;left:72px;right:72px;top:1020px;border-top:1px solid var(--line);padding-top:15px;display:flex;justify-content:space-between;font-size:20px;color:var(--muted);line-height:24px}
  .deck{position:absolute;left:72px;right:72px;top:195px;margin:0;font-size:27px;line-height:1.3;color:var(--muted)}
  .bench-card{position:absolute;top:262px;width:864px;height:565px;background:#fbfaf6;border:1px solid var(--line);border-radius:8px;padding:28px 29px}
  .bench-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:20px}
  .bench-header h2{margin:0;font-family:Georgia,'Times New Roman',serif;font-size:42px;font-weight:400;letter-spacing:-.6px}
  .bench-header span{color:var(--muted);font-size:23px}
  table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
  th{padding:12px 0 15px;text-align:right;font-size:20px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);border-bottom:2px solid var(--line)}
  th:first-child{text-align:left;width:59%}
  td{height:65px;border-bottom:1px solid var(--line);text-align:right;font-size:28px}
  td:first-child{text-align:left;font-size:24px}
  tbody tr:nth-child(2){background:#f0ecdf}
  tbody tr:nth-child(2) td:first-child{padding-left:10px}
  tbody tr:nth-child(2) td:last-child{padding-right:10px}
  .metrics{display:flex;gap:26px;padding-top:24px}
  .metric{flex:1}.metric+ .metric{padding-left:26px;border-left:1px solid var(--line)}
  .metric-label{font-size:21px;color:var(--muted);margin-bottom:13px;white-space:nowrap}
  .metric-value{font-size:35px;font-weight:700;letter-spacing:-.9px;white-space:nowrap}
  .metric-value .arrow{font-weight:400;color:var(--muted);font-size:29px;margin:0 2px}
  .metric-gain{font-size:23px;font-weight:700;color:var(--green);margin-top:9px}
  .method-note{position:absolute;top:854px;width:864px;font-size:21px;line-height:1.45;color:var(--muted)}
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
  const left = `<section class="instruction left"><div class="label">Original instruction</div><p>${escape(item.originalInstruction)}</p></section>
    <div class="video left"></div><div class="status left"><div><span class="badge fail">BENCH FAIL</span></div><div class="assessment">Agent considers<br>the task complete</div><div class="rate">Task success &nbsp;<b>${item.beforeSuccesses}/${item.episodes}</b></div></div>`;
  const right = revealed ? `<section class="instruction right"><div class="label">Revised instruction <span>Changed words in bold</span></div><p>${highlighted}</p></section><div class="video right"></div><div class="status right"><span class="badge pass">BENCH PASS</span><div class="rate">Task success &nbsp;${item.beforeSuccesses}/${item.episodes} <span style="color:var(--muted)">→</span> <b>${item.afterSuccesses}/${item.episodes}</b></div></div>` : '';
  return frame(`${header(`LIBERO / Case ${String(index + 1).padStart(2,'0')}`, item.title, `${String(index+1).padStart(2,'0')} / 04`)}${left}${right}<div class="footer"><span>Same initial state · seed ${escape(item.seed)} · state ${escape(item.initStateId)}</span><span>${escape(manifest.playbackSpeed || 2)}× playback · task success measured over ${escape(item.episodes)} initial states</span></div>`);
}

function values(report, type) {
  if (type === 'libero') return {n:report.n, completePass:report.matrix.success.benchSuccess, completeFail:report.matrix.success.benchFailure, incompleteFail:report.matrix.failure.benchFailure, ias:report.ias, native:report.benchSuccessRate};
  return {n:report.n, completePass:report.agentSuccessBenchSuccess, completeFail:report.agentSuccessBenchFalse, incompleteFail:report.agentFalseBenchFalse, ias:report.instinctAlignment, native:report.benchSuccess / report.n};
}
function metric(label, before, after) {
  return `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${percent(before)} <span class="arrow">→</span> ${percent(after)}</div><div class="metric-gain">${points(before, after)}</div></div>`;
}
function benchCard(name, type, side) {
  const before = values(manifest[type].before, type), after = values(manifest[type].after, type);
  const rows = [['Agent complete · Bench pass','completePass'],['Agent complete · Bench fail','completeFail'],['Agent incomplete · Bench fail','incompleteFail']];
  return `<section class="bench-card ${side}"><div class="bench-header"><h2>${name}</h2><span>${before.n} → ${after.n} episodes</span></div><table><thead><tr><th>Outcome</th><th>Original</th><th>Revised</th></tr></thead><tbody>${rows.map(([label,key])=>`<tr><td>${label}</td><td>${before[key]}</td><td>${after[key]}</td></tr>`).join('')}</tbody></table><div class="metrics">${metric('Instinct-alignment score',before.ias,after.ias)}${metric('Benchmark success',before.native,after.native)}</div></section>`;
}
function resultsSlide() {
  return frame(`${header('Results / LIBERO + RoboTwin','Clearer instructions. Better-aligned outcomes.','03 / 04')}<p class="deck">Instruction-layer repairs preserve the benchmark verifier and recorded demonstrations.</p>${benchCard('LIBERO','libero','left')}${benchCard('RoboTwin','robotwin','right')}<div class="method-note left"><b>Reviewed 400-episode composite:</b> 310 original + 70 first revision + 20 final revision; one human completion correction.</div><div class="method-note right"><b>Revised run:</b> 498 terminal episodes, including 19 infrastructure errors; 2 of 500 planned episodes missing. Effective scene seeds not fully matched.</div><div class="footer"><span>IAS = 1 − (agent complete / bench fail) ÷ episodes</span><span>Agent-incomplete / Bench-pass cell omitted by reporting convention · pp = percentage points</span></div>`);
}
function takeawaysSlide() {
  const rows = [
    ['Robot benchmarks have instruction–verification gaps.','Some reasonable completions fail because the instruction leaves out conditions checked by the benchmark.'],
    ['Contact-rich precision remains difficult.','GPT-6-Astra performs well on many tasks, but success remains low on some contact-rich tasks requiring precise control. Zero-shot execution is not yet consistently reliable.'],
    ['An imperfect policy can still debug benchmarks.','GPT-6-Astra is not a ground-truth policy, but can expose gaps and guide instruction repairs while preserving demonstrations.']
  ];
  return frame(`${header('Takeaways','What these rollouts reveal.','04 / 04')}${rows.map(([title,body],index)=>`<section class="takeaway" style="top:${251+index*195}px"><div class="takeaway-number">0${index+1}</div><div class="takeaway-copy"><h2>${title}</h2><p>${body}</p></div></section>`).join('')}<div class="closing">Small instruction edits. Better-aligned benchmarks.</div><div class="footer"><span>Agent as Policy</span><span>tianqi-zh.github.io/robot-agent-gallery</span></div>`);
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
      const overflow = await page.evaluate(() => Array.from(document.querySelectorAll('.instruction p,.takeaway-copy,.metric,.footer')).flatMap(element => {
        const rect = element.getBoundingClientRect();
        return element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1 || rect.bottom > 1080 || rect.right > 1920 ? [element.className || element.tagName] : [];
      }));
      if (overflow.length) throw new Error(`Slide ${relative} has overflowing text: ${overflow.join(', ')}`);
      await page.screenshot({path:path.join(output,relative),fullPage:false});
      fs.writeFileSync(path.join(output,relative.replace(/\.png$/,'.html')),html);
      process.stdout.write(`Rendered ${relative}\n`);
    }
    for (const [index,item] of manifest.cases.entries()) {
      if (!/^[a-z0-9-]+$/.test(item.id)) throw new Error(`Unsafe case ID: ${item.id}`);
      await render(`cases/${item.id}-before.png`,caseSlide(item,index,false));
      await render(`cases/${item.id}-after.png`,caseSlide(item,index,true));
    }
    await render('results.png',resultsSlide());
    await render('takeaways.png',takeawaysSlide());
    fs.writeFileSync(path.join(output,'slide-layout.json'),JSON.stringify({width,height,videoBoxes:boxes},null,2)+'\n');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exitCode = 1;});
