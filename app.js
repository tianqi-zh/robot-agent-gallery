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
function prettySuite(suite) { return ({libero_spatial:'Spatial',libero_goal:'Goal',libero_object:'Object',libero_10:'LIBERO-10',robotwin:'All tasks'}[suite] || suite); }
function elapsed(seconds) { return seconds < 60 ? `${Math.round(seconds)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`; }
function duration(seconds) { return `${Math.floor(seconds / 60)}:${pad(Math.floor(seconds % 60))}`; }
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
  const selections = [
    {benchmark:'libero',task:'libero_spatial_t00',label:'Spatial reasoning',secondary:false},
    {benchmark:'robotwin',task:'robotwin_stack_blocks_three',label:'Building with two arms',secondary:true},
  ];
  $('hero-visual').innerHTML = selections.map(item => {
    const b = benchmark(item.benchmark), task = b.tasks.find(t => t.id === item.task) || b.tasks[0], episode = task.episodes[0];
    return `<button class="featured ${item.secondary ? 'featured-secondary' : ''}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" aria-label="Watch ${escapeHtml(item.label)} on ${b.name}"><div class="featured-image"><img src="${episode.poster}" alt="${escapeHtml(task.name)} — recorded camera views" width="${episode.width}" height="${episode.height}" fetchpriority="${item.secondary ? 'auto' : 'high'}"><span class="featured-play" aria-hidden="true">▶</span></div><div class="featured-caption"><span>${escapeHtml(item.label)}</span><small>${b.name} · Episode 01 ↗</small></div></button>`;
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
  const suiteButtons = [{id:'all',name:'All tasks'}, ...(b.id === 'libero' ? b.suites.map(suite => ({id:suite.id,name:prettySuite(suite.id)})) : [])];
  $('suite-tabs').innerHTML = suiteButtons.map(suite => `<button class="${state.suite === suite.id ? 'active' : ''}" data-suite="${suite.id}" aria-pressed="${state.suite === suite.id}">${suite.name}</button>`).join('');
  $('collection-description').textContent = b.id === 'libero' ? '10 recorded episodes for every task.' : 'First pass. One recorded episode per task.';
  const tasks = filteredTasks();
  const totalEpisodes = tasks.reduce((total,task) => total + task.episodes.length, 0);
  $('results-count').textContent = `${tasks.length} ${tasks.length === 1 ? 'task' : 'tasks'} · ${totalEpisodes} ${totalEpisodes === 1 ? 'rollout' : 'rollouts'}`;
  $('empty-state').hidden = tasks.length > 0;
  $('task-grid').innerHTML = tasks.map(task => {
    const episode = task.episodes[0], count = task.episodes.length;
    return `<article class="task-card"><button class="media-thumb ${b.id}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" aria-label="Watch ${escapeHtml(task.name)}"><img src="${episode.poster}" alt="Recorded views for ${escapeHtml(task.name)}" loading="lazy" decoding="async" width="${episode.width}" height="${episode.height}"><span class="thumb-count">${count} ${count === 1 ? 'rollout' : 'rollouts'}</span><span class="thumb-play" aria-hidden="true">▶</span></button><div class="task-body"><div class="task-meta"><span>${escapeHtml(b.id === 'libero' ? `LIBERO · ${prettySuite(task.suite)}` : 'ROBOTWIN · FIRST PASS')}</span><span class="task-rate ${task.failures ? 'imperfect' : ''}">${task.successes} / ${count} successful</span></div><button class="task-title" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" title="${escapeHtml(task.name)}">${escapeHtml(task.name)}</button><div class="sample-row">${task.episodes.map(ep => `<button class="sample-dot ${ep.status}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${ep.id}" aria-label="${escapeHtml(task.name)}, episode ${ep.index+1}: ${statusName(ep.status)}" title="Episode ${ep.index+1} · ${statusName(ep.status)}">${ep.index+1}</button>`).join('')}<span class="sample-caption">${count === 1 ? '1 episode' : 'Episodes'}</span></div></div></article>`;
  }).join('');
}
function renderPlayer() {
  const b = benchmark(), task = state.task, episode = state.episode;
  $('dialog-eyebrow').textContent = `${b.name.toUpperCase()} / ${b.id === 'libero' ? prettySuite(task.suite).toUpperCase() : 'FIRST PASS'} / RECORDED ROLLOUT`;
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
  $('camera-labels').innerHTML = b.protocol.cameras.map(name => `<span>${escapeHtml(name)}</span>`).join('');
  $('video-note').textContent = `${b.protocol.videoNote} Episode wall time includes preparation and cleanup.`;
  $('download-video').href = episode.video; $('download-video').download = `${episode.id}.mp4`;
  $('copy-status').textContent = ''; $('video-error').hidden = true;
  const index = task.episodes.findIndex(ep => ep.id === episode.id);
  $('previous-episode').disabled = index === 0; $('next-episode').disabled = index === task.episodes.length-1;
  if (video.dataset.episode !== episode.id) {
    video.pause(); video.poster = episode.poster; video.src = episode.video; video.preload = 'metadata'; video.dataset.episode = episode.id;
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
  state.data=data; renderFeatured(); applyRoute();
}).catch(error=>{console.error(error);$('load-error').hidden=false;$('results-count').textContent='Collection unavailable';});
