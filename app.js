'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const pad = value => String(value).padStart(2, '0');
const statusName = status => ({success:'Success',failure:'Failure',timeout:'Timeout'}[status] || status);
const state = {data:null,benchmark:'libero',suite:'all',search:'',outcome:'all',sort:'default',task:null,episode:null,returnTask:null};
const dialog = $('episode-dialog');
const video = $('episode-video');
let routeRendering = false;

function benchmark(id = state.benchmark) { return state.data.benchmarks.find(item => item.id === id); }
function prettySuite(suite) { return ({libero_spatial:'Spatial',libero_goal:'Goal',libero_object:'Object',libero_10:'LIBERO-10',robotwin:'All tasks',robocasa_atomic:'Atomic',robocasa_composite:'Composite'}[suite] || suite); }
function elapsed(seconds) { return seconds < 60 ? `${Math.round(seconds)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`; }
function duration(seconds) { return `${Math.floor(seconds / 60)}:${pad(Math.floor(seconds % 60))}`; }
function resolveVideoSource(episode) {
  return window.GALLERY_REMOTE_VIDEOS === true && typeof episode.remoteVideo === 'string' && episode.remoteVideo
    ? episode.remoteVideo : episode.video;
}
function episodeCount(b) { return b.tasks.reduce((total,task) => total + task.episodes.length, 0); }
function sampling(b) { return `${b.protocol.episodesPerTask} ${b.protocol.episodesPerTask === 1 ? 'episode' : 'episodes'} per task`; }
function list(values) { return new Intl.ListFormat('en', {style:'long',type:'conjunction'}).format(values); }
function renderOverview() {
  const benchmarks = state.data.benchmarks;
  const tasks = benchmarks.reduce((total,b) => total + b.tasks.length, 0);
  const episodes = benchmarks.reduce((total,b) => total + episodeCount(b), 0);
  $('total-tasks').textContent = tasks;
  $('total-episodes').textContent = episodes;
  $('nav-count').textContent = episodes;
  const description = `Watch GPT-6-Astra control robots across ${tasks} tasks. Browse ${episodes} recorded episodes from ${list(benchmarks.map(b => b.name))}, including successes and failures.`;
  document.querySelector('meta[name="description"]').content = description;
  document.querySelector('meta[property="og:description"]').content = description;
  $('hero-description').textContent = `A coding agent controlling robots through visual feedback. Browse recorded rollouts from ${list(benchmarks.map(b => b.name))}, from the first move to the final result.`;
  const overview = $('benchmark-overview');
  overview.dataset.count = benchmarks.length;
  overview.style.setProperty('--benchmark-columns', Math.min(3, benchmarks.length));
  overview.innerHTML = benchmarks.map((b,index) => {
    const rate = (b.summary.successRate * 100).toFixed(1);
    const groups = b.suites.length > 1 ? ` across ${b.suites.length} task groups` : '';
    return `<button class="benchmark-summary" data-benchmark="${escapeHtml(b.id)}" aria-pressed="false"><div class="summary-heading"><span class="eyebrow">${pad(index+1)} / ${escapeHtml(b.name.toUpperCase())}</span><span class="summary-tag">${escapeHtml(sampling(b))}</span></div><div class="summary-main"><strong>${rate}<span>%</span></strong><span class="summary-detail">${b.summary.successes} / ${episodeCount(b)} successful<br><small>${b.tasks.length} tasks${groups}</small></span><span class="summary-arrow" aria-hidden="true">↗</span></div><div class="score-track"><span style="width:${rate}%"></span></div></button>`;
  }).join('');
  $('benchmark-tabs').innerHTML = benchmarks.map(b => `<button data-benchmark="${escapeHtml(b.id)}" aria-pressed="false">${escapeHtml(b.name)} <span>${episodeCount(b)}</span></button>`).join('');
  $('published-episodes-note').textContent = `${list(benchmarks.map(b => `${episodeCount(b)} ${b.name} videos`))}, including every selected success, failure and timeout. Infrastructure retries and source selection are documented in the evaluation protocol.`;
  $('playback-protocol').innerHTML = benchmarks.map(b => `<p><strong>${escapeHtml(b.name)}.</strong> ${escapeHtml(b.protocol.videoNote)}</p>`).join('');
  $('sampling-protocol').textContent = `${benchmarks.map(b => `${b.name}: ${sampling(b)}.`).join(' ')} Different tasks and protocols prevent direct comparison or pooling across benchmarks.`;
  const dates = [...new Set(benchmarks.map(b => b.evaluationDate || state.data.evaluationDate).filter(Boolean))]
    .map(value => new Date(`${value}T00:00:00Z`)).filter(value => Number.isFinite(value.getTime())).sort((a,b) => a-b);
  const formatter = new Intl.DateTimeFormat('en-US', {year:'numeric',month:'long',day:'numeric',timeZone:'UTC'});
  $('recorded-dates').textContent = dates.length ? `Recorded ${dates.length === 1 ? formatter.format(dates[0]) : formatter.formatRange(dates[0], dates.at(-1))}` : 'Recorded evaluation episodes';
}
function route(values, replace = false) {
  const returnUrl = values.task ? (dialog.open ? history.state?.gallery?.returnUrl : `${location.pathname}${location.search}${location.hash}`) : null;
  if (!replace && !dialog.open) history.replaceState({gallery:{benchmark:state.benchmark}}, '', location.href);
  const params = new URLSearchParams({benchmark:values.benchmark || state.benchmark});
  if (values.task) params.set('task', values.task);
  if (values.episode) params.set('episode', values.episode);
  history[replace ? 'replaceState' : 'pushState']({gallery:{benchmark:values.benchmark || state.benchmark,returnUrl}}, '', `${location.pathname}${location.search}#${params}`);
  applyRoute();
}
function openEpisode(benchmarkId, taskId, episodeId) {
  state.returnTask = taskId;
  route({benchmark:benchmarkId,task:taskId,episode:episodeId}, dialog.open);
}
function closeEpisode() {
  if (history.state?.gallery?.returnUrl) history.back();
  else route({benchmark:state.benchmark}, true);
}
function switchBenchmark(id, scroll = false) {
  if (!state.data) return;
  state.suite = 'all'; state.search = ''; state.outcome = 'all'; state.sort = 'default';
  $('task-search').value = ''; $('outcome-filter').value = 'all'; $('sort-order').value = 'default';
  route({benchmark:id});
  if (scroll) $('collection').scrollIntoView({behavior:'smooth'});
}
function applyRoute() {
  if (!state.data || routeRendering) return;
  routeRendering = true;
  const params = new URLSearchParams(location.hash.slice(1));
  const incoming = params.get('benchmark') || history.state?.gallery?.benchmark || (location.hash === '' ? 'libero' : state.benchmark);
  if (incoming && benchmark(incoming)) {
    if (state.benchmark !== incoming) {
      state.suite='all'; state.search=''; state.outcome='all'; state.sort='default';
      $('task-search').value=''; $('outcome-filter').value='all'; $('sort-order').value='default';
    }
    state.benchmark = incoming;
  }
  renderCollection();
  const selectedTask = benchmark().tasks.find(task => task.id === params.get('task'));
  if (selectedTask) {
    state.task = selectedTask;
    state.episode = selectedTask.episodes.find(episode => episode.id === params.get('episode')) || selectedTask.episodes[0];
    renderPlayer();
    if (!dialog.open) { dialog.showModal(); document.body.classList.add('modal-open'); $('close-dialog').focus(); }
  } else {
    if (dialog.open) {
      video.pause(); video.removeAttribute('src'); delete video.dataset.episode; video.load(); dialog.close(); document.body.classList.remove('modal-open');
      const target = document.querySelector(`[data-task="${CSS.escape(state.returnTask || '')}"]`);
      if (target) target.focus({preventScroll:true});
    }
    state.task = null; state.episode = null;
  }
  routeRendering = false;
}
function renderFeatured() {
  const preferred = {libero:{task:'libero_spatial_t00',label:'Spatial reasoning'},robotwin:{task:'robotwin_stack_blocks_three',label:'Building with two arms'},robocasa:{label:'Around the kitchen'}};
  const available = state.data.benchmarks;
  const selections = [available[0], ...(available.length > 1 ? [available.at(-1)] : [])].map((b,index) => ({benchmark:b.id,...preferred[b.id],secondary:index > 0}));
  $('hero-visual').innerHTML = selections.map(item => {
    const b = benchmark(item.benchmark), task = b.tasks.find(t => t.id === item.task) || b.tasks[0], episode = task.episodes[0];
    return `<button class="featured ${item.secondary ? 'featured-secondary' : ''}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" aria-label="Watch ${escapeHtml(item.label || task.name)} on ${escapeHtml(b.name)}"><div class="featured-image"><img src="${episode.poster}" alt="${escapeHtml(task.name)} — recorded camera views" width="${episode.width}" height="${episode.height}" fetchpriority="${item.secondary ? 'auto' : 'high'}"><span class="featured-play" aria-hidden="true">▶</span></div><div class="featured-caption"><span>${escapeHtml(item.label || task.name)}</span><small>${escapeHtml(b.name)} · Episode 01 ↗</small></div></button>`;
  }).join('');
}
function filteredTasks() {
  const query = state.search.trim().toLowerCase();
  const tasks = benchmark().tasks.filter(task =>
    (state.suite === 'all' || task.suite === state.suite) &&
    (!query || `${task.name} ${task.instruction} ${task.suiteName} ${task.id}`.toLowerCase().includes(query)) &&
    (state.outcome === 'all' || (state.outcome === 'failures' ? task.failures > 0 : task.failures === 0))
  );
  if (state.sort !== 'default') tasks.sort((a,b) => state.sort === 'best' ? b.successRate - a.successRate : a.successRate - b.successRate);
  return tasks;
}
function renderCollection() {
  if (!state.data) return;
  const b = benchmark();
  document.querySelectorAll('[data-benchmark]').forEach(button => {
    const active = button.dataset.benchmark === b.id;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  });
  const suiteButtons = [{id:'all',name:'All tasks'}, ...(b.suites.length > 1 ? b.suites.map(suite => ({id:suite.id,name:prettySuite(suite.id),tasks:suite.tasks})) : [])];
  $('suite-tabs').innerHTML = suiteButtons.map(suite => `<button class="${state.suite === suite.id ? 'active' : ''}" data-suite="${escapeHtml(suite.id)}" aria-pressed="${state.suite === suite.id}">${escapeHtml(suite.name)}${suite.tasks !== undefined ? ` <span>${suite.tasks}</span>` : ''}</button>`).join('');
  $('collection-description').textContent = `${sampling(b)}. All selected outcomes included.`;
  const tasks = filteredTasks();
  const totalEpisodes = tasks.reduce((total,task) => total + task.episodes.length, 0);
  $('results-count').textContent = `${tasks.length} ${tasks.length === 1 ? 'task' : 'tasks'} · ${totalEpisodes} ${totalEpisodes === 1 ? 'rollout' : 'rollouts'}`;
  $('empty-state').hidden = tasks.length > 0;
  $('task-grid').innerHTML = tasks.map(task => {
    const episode = task.episodes[0], count = task.episodes.length;
    return `<article class="task-card"><button class="media-thumb ${b.id}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" aria-label="Watch ${escapeHtml(task.name)}"><img src="${episode.poster}" alt="Recorded views for ${escapeHtml(task.name)}" loading="lazy" decoding="async" width="${episode.width}" height="${episode.height}"><span class="thumb-count">${count} ${count === 1 ? 'rollout' : 'rollouts'}</span><span class="thumb-play" aria-hidden="true">▶</span></button><div class="task-body"><div class="task-meta"><span>${escapeHtml(`${b.name.toUpperCase()}${b.suites.length > 1 ? ` · ${prettySuite(task.suite)}` : ''}`)}</span><span class="task-rate ${task.failures ? 'imperfect' : ''}">${task.successes} / ${count} successful</span></div><button class="task-title" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" title="${escapeHtml(task.name)}">${escapeHtml(task.name)}</button><div class="sample-row">${task.episodes.map(ep => `<button class="sample-dot ${ep.status}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${ep.id}" aria-label="${escapeHtml(task.name)}, episode ${ep.index+1}: ${statusName(ep.status)}" title="Episode ${ep.index+1} · ${statusName(ep.status)}">${ep.index+1}</button>`).join('')}<span class="sample-caption">${count === 1 ? '1 episode' : 'Episodes'}</span></div></div></article>`;
  }).join('');
}
function renderPlayer() {
  const b = benchmark(), task = state.task, episode = state.episode;
  $('dialog-eyebrow').textContent = `${b.name.toUpperCase()} / ${b.suites.length > 1 ? prettySuite(task.suite).toUpperCase() : sampling(b).toUpperCase()} / RECORDED ROLLOUT`;
  $('dialog-title').textContent = task.name;
  $('task-instruction').textContent = task.instruction;
  $('episode-status').textContent = statusName(episode.status);
  $('episode-status').className = `status-badge ${episode.status}`;
  $('episode-number').textContent = `Episode ${pad(episode.index+1)} / ${pad(task.episodes.length)}`;
  $('task-score').textContent = `${task.successes}/${task.episodes.length} successful`;
  $('episode-buttons').innerHTML = task.episodes.map(ep => `<button class="episode-button ${ep.status} ${ep.id === episode.id ? 'active' : ''}" data-select-episode="${ep.id}" aria-pressed="${ep.id === episode.id}" aria-label="Episode ${ep.index+1}: ${statusName(ep.status)}">${pad(ep.index+1)}</button>`).join('');
  const facts = [['Seed',episode.seed],[b.protocol.stepsLabel,`${episode.steps} / ${episode.maxSteps}`],['Tool calls',episode.toolCalls],['Video length',duration(episode.durationSeconds)],['Episode wall time',elapsed(episode.wallSeconds)]];
  if (episode.initStateId !== null) facts.splice(1,0,['Initial state',episode.initStateId]);
  $('episode-facts').innerHTML = facts.map(([label,value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
  $('camera-labels').style.setProperty('--camera-count', b.protocol.cameras.length);
  $('camera-labels').innerHTML = b.protocol.cameras.map(name => `<span>${escapeHtml(name)}</span>`).join('');
  $('video-note').textContent = `${b.protocol.videoNote} Episode wall time includes preparation and cleanup.`;
  const source = resolveVideoSource(episode);
  $('download-video').href = source; $('download-video').download = `${episode.id}.mp4`;
  $('copy-status').textContent = ''; $('video-error').hidden = true;
  const index = task.episodes.findIndex(ep => ep.id === episode.id);
  $('previous-episode').disabled = index === 0; $('next-episode').disabled = index === task.episodes.length-1;
  if (video.dataset.episode !== episode.id) {
    video.pause(); video.poster = episode.poster; video.src = source; video.preload = 'metadata'; video.dataset.episode = episode.id;
    video.style.aspectRatio = `${episode.width}/${episode.height}`; video.load();
    video.playbackRate = Number($('playback-speed').value);
  }
}
function moveEpisode(direction) {
  const index = state.task.episodes.findIndex(ep => ep.id === state.episode.id);
  const next = state.task.episodes[index+direction];
  if (next) openEpisode(state.benchmark,state.task.id,next.id);
}
document.addEventListener('click', event => {
  const opener = event.target.closest('[data-open-benchmark]');
  if (opener) { openEpisode(opener.dataset.openBenchmark,opener.dataset.task,opener.dataset.episode); return; }
  const b = event.target.closest('[data-benchmark]');
  if (b) { switchBenchmark(b.dataset.benchmark,b.classList.contains('benchmark-summary')); return; }
  const suite = event.target.closest('[data-suite]');
  if (suite) { state.suite = suite.dataset.suite; renderCollection(); document.querySelector(`[data-suite="${CSS.escape(state.suite)}"]`)?.focus({preventScroll:true}); return; }
  const ep = event.target.closest('[data-select-episode]');
  if (ep) { const id=ep.dataset.selectEpisode; openEpisode(state.benchmark,state.task.id,id); document.querySelector(`[data-select-episode="${CSS.escape(id)}"]`)?.focus({preventScroll:true}); }
});
$('task-search').addEventListener('input',event => {state.search = event.target.value; renderCollection();});
$('outcome-filter').addEventListener('change',event => {state.outcome = event.target.value; renderCollection();});
$('sort-order').addEventListener('change',event => {state.sort = event.target.value; renderCollection();});
$('clear-filters').addEventListener('click',()=>switchBenchmark(state.benchmark));
$('close-dialog').addEventListener('click',closeEpisode);
dialog.addEventListener('cancel',event=>{event.preventDefault();closeEpisode();});
dialog.addEventListener('click',event=>{if(event.target === dialog){const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeEpisode();}});
$('previous-episode').addEventListener('click',()=>moveEpisode(-1));
$('next-episode').addEventListener('click',()=>moveEpisode(1));
$('playback-speed').addEventListener('change',event=>{video.playbackRate=Number(event.target.value);});
video.addEventListener('error',()=>{if(video.hasAttribute('src'))$('video-error').hidden=false;});
$('copy-link').addEventListener('click',async()=>{
  try { await navigator.clipboard.writeText(location.href); $('copy-status').textContent='Episode link copied.'; }
  catch { $('copy-status').textContent=location.href; }
});
window.addEventListener('hashchange',applyRoute);
window.addEventListener('popstate',applyRoute);
fetch('data/gallery.json').then(response=>{if(!response.ok)throw new Error('Manifest unavailable');return response.json();}).then(data=>{
  const available = data.benchmarks.filter(b => b.tasks.length > 0 && b.tasks.every(task => task.episodes.length > 0));
  if (!available.length) throw new Error('No published episodes available');
  state.data={...data,benchmarks:available};
  if (!benchmark()) state.benchmark=available[0].id;
  renderOverview(); renderFeatured(); applyRoute();
}).catch(error=>{console.error(error);$('load-error').hidden=false;$('results-count').textContent='Collection unavailable';});
