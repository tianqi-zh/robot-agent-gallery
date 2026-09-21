'use strict';
// Resolve from the shared script, not from the current (possibly nested) page.
const siteRoot = new URL('.', document.currentScript.src);
const assetUrl = path => new URL(path, siteRoot).href;
const normalizeBenchmark = id => id === 'robotwin' ? 'robotwin_nvidia10' : id;
const benchmarkPath = id => `gallery/${id === 'robotwin_nvidia10' ? 'robotwin' : id}/`;
const pageBenchmark = document.body.dataset.benchmark || null;
const benchmarkUrl = id => assetUrl(benchmarkPath(normalizeBenchmark(id)));
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const pad = value => String(value).padStart(2, '0');
const statusName = status => ({success:'Success',failure:'Failure',timeout:'Timeout'}[status] || status);
const state = {data:null,demos:{tasks:{}},benchmark:pageBenchmark || 'libero',suite:'all',search:'',outcome:'all',sort:'default',task:null,episode:null,view:'episode',returnTask:null,returnView:'episode'};
const dialog = $('episode-dialog');
const video = $('episode-video');
let routeRendering = false;
let lastRenderedUrl = null;

function benchmark(id = state.benchmark) { return state.data.benchmarks.find(item => item.id === id); }
function prettySuite(suite) { return ({libero_spatial:'Spatial',libero_goal:'Goal',libero_object:'Object',libero_10:'LIBERO-10',robotwin:'All tasks',robocasa_atomic:'Atomic',robocasa_composite:'Composite'}[suite] || benchmark()?.suites.find(item => item.id === suite)?.name || suite); }
function elapsed(seconds) { return seconds < 60 ? `${Math.round(seconds)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`; }
function duration(seconds) { return `${Math.floor(seconds / 60)}:${pad(Math.floor(seconds % 60))}`; }
function trainingDemoNote(b = benchmark()) {
  const coverage = state.demos.coverage?.[b.id];
  if (b.id === 'robodojo' && coverage) return `${coverage.available} of ${coverage.tasks} tasks have a released training demonstration. ${coverage.unavailable} tasks have no matching demonstration in the source dataset.`;
  return b.protocol.trainingDemoNote || (b.id === 'robodojo' ? 'RoboDojo training demonstrations have not been imported into this gallery.' : '');
}
function taskDemo(task) {
  const demo = state.demos.tasks[task.id], note = trainingDemoNote();
  if (demo) return demo;
  return {status:'unavailable',notImported:Boolean(note) && !state.demos.coverage?.[state.benchmark],reason:state.demos.unavailableReason || note || 'A training demonstration is not available for this task yet.'};
}
function demoAvailable(demo) { return demo.status === 'available' && Boolean(demo.video); }
function resolveVideoSource(episode) {
  return window.GALLERY_REMOTE_VIDEOS === true && typeof episode.remoteVideo === 'string' && episode.remoteVideo
    ? episode.remoteVideo : episode.video;
}
function episodeCount(b) { return b.tasks.reduce((total,task) => total + task.episodes.length, 0); }
function sampling(b) {
  const incomplete = b.tasks.some(task => task.episodes.length < b.protocol.episodesPerTask);
  return `${incomplete ? 'Up to ' : ''}${b.protocol.episodesPerTask} ${b.protocol.episodesPerTask === 1 ? 'episode' : 'episodes'} per task`;
}
function list(values) { return new Intl.ListFormat('en', {style:'long',type:'conjunction'}).format(values); }
function renderOverview() {
  const benchmarks = pageBenchmark ? [benchmark(pageBenchmark)] : state.data.benchmarks;
  const tasks = benchmarks.reduce((total,b) => total + b.tasks.length, 0);
  const episodes = benchmarks.reduce((total,b) => total + episodeCount(b), 0);
  $('total-tasks').textContent = tasks;
  $('total-episodes').textContent = episodes;
  $('nav-count').textContent = episodes;
  const description = `Watch GPT-6-Astra control robots across ${tasks} tasks. Browse ${episodes} recorded episodes from ${list(benchmarks.map(b => b.name))}, including successes and failures.`;
  document.querySelector('meta[name="description"]').content = description;
  document.querySelector('meta[property="og:description"]').content = description;
  $('hero-description').textContent = `A coding agent controlling robots through visual feedback. Browse recorded rollouts from ${list(benchmarks.map(b => b.name))}, from the first move to the final result.`;
  if (pageBenchmark) {
    const title = `${benchmark(pageBenchmark).name} — Robot Evaluation Gallery`;
    document.title = title;
    document.querySelector('meta[property="og:title"]').content = title;
    $('hero-title').textContent = benchmark(pageBenchmark).name;
    $('collection-heading').textContent = `${benchmark(pageBenchmark).name} rollouts`;
    document.querySelector('.comparison-note').textContent = 'Native benchmark outcomes. Training demonstrations are provided separately for reference.';
  }
  const overview = $('benchmark-overview');
  overview.dataset.count = benchmarks.length;
  overview.style.setProperty('--benchmark-columns', benchmarks.length === 4 ? 2 : Math.min(3, benchmarks.length));
  overview.innerHTML = benchmarks.map((b,index) => {
    const rate = (b.summary.successRate * 100).toFixed(1);
    const groups = b.suites.length > 1 ? ` across ${b.suites.length} task groups` : '';
    return `<a class="benchmark-summary" href="${benchmarkUrl(b.id)}" data-benchmark="${escapeHtml(b.id)}"><div class="summary-heading"><span class="eyebrow">${pad(index+1)} / ${escapeHtml(b.name.toUpperCase())}</span><span class="summary-tag">${escapeHtml(sampling(b))}</span></div><div class="summary-main"><strong>${rate}<span>%</span></strong><span class="summary-detail">${b.summary.successes} / ${episodeCount(b)} successful<br><small>${b.tasks.length} tasks${groups}</small></span><span class="summary-arrow" aria-hidden="true">↗</span></div><div class="score-track"><span style="width:${rate}%"></span></div></a>`;
  }).join('');
  $('benchmark-tabs').dataset.count = state.data.benchmarks.length;
  $('benchmark-tabs').innerHTML = state.data.benchmarks.map(b => `<a href="${benchmarkUrl(b.id)}" data-benchmark="${escapeHtml(b.id)}">${escapeHtml(b.name)} <span>${episodeCount(b)}</span></a>`).join('');
  $('published-episodes-note').textContent = `${list(benchmarks.map(b => `${episodeCount(b)} ${b.name} videos`))}, including every selected success, failure and timeout. Infrastructure retries and source selection are documented in the evaluation protocol.`;
  $('playback-protocol').innerHTML = benchmarks.map(b => `<p><strong>${escapeHtml(b.name)}.</strong> ${escapeHtml(b.protocol.videoNote)}</p>`).join('');
  $('sampling-protocol').textContent = `${benchmarks.map(b => `${b.name}: ${sampling(b)}.`).join(' ')} Different tasks and protocols prevent direct comparison or pooling across benchmarks.`;
  const dates = [...new Set(benchmarks.map(b => b.evaluationDate || state.data.evaluationDate).filter(Boolean))]
    .map(value => new Date(`${value}T00:00:00Z`)).filter(value => Number.isFinite(value.getTime())).sort((a,b) => a-b);
  const formatter = new Intl.DateTimeFormat('en-US', {year:'numeric',month:'long',day:'numeric',timeZone:'UTC'});
  $('recorded-dates').textContent = dates.length ? `Recorded ${dates.length === 1 ? formatter.format(dates[0]) : formatter.formatRange(dates[0], dates.at(-1))}` : 'Recorded evaluation episodes';
}
function route(values, replace = false) {
  const target = normalizeBenchmark(values.benchmark || state.benchmark);
  if (pageBenchmark && target !== pageBenchmark && benchmark(target)) {
    const params = new URLSearchParams({...values, benchmark:target});
    location[replace ? 'replace' : 'assign'](`${benchmarkUrl(target)}${location.search}#${params}`);
    return;
  }
  const returnUrl = values.task ? (dialog.open ? history.state?.gallery?.returnUrl : `${location.pathname}${location.search}${location.hash}`) : null;
  if (!replace && !dialog.open) history.replaceState({gallery:{benchmark:state.benchmark}}, '', location.href);
  const params = new URLSearchParams({benchmark:values.benchmark || state.benchmark});
  if (values.task) params.set('task', values.task);
  if (values.episode) params.set('episode', values.episode);
  if (values.view === 'demo') params.set('view', 'demo');
  history[replace ? 'replaceState' : 'pushState']({gallery:{benchmark:values.benchmark || state.benchmark,returnUrl}}, '', `${location.pathname}${location.search}#${params}`);
  applyRoute();
}
function openEpisode(benchmarkId, taskId, episodeId) {
  if (!dialog.open) { state.returnTask = taskId; state.returnView = 'episode'; }
  route({benchmark:benchmarkId,task:taskId,episode:episodeId}, dialog.open);
}
function openDemo(benchmarkId, taskId) {
  if (!dialog.open) { state.returnTask = taskId; state.returnView = 'demo'; }
  route({benchmark:benchmarkId,task:taskId,view:'demo'}, dialog.open);
}
function switchPlayerView(view) {
  if (view === 'demo') openDemo(state.benchmark,state.task.id);
  else openEpisode(state.benchmark,state.task.id,state.episode.id);
  dialog.scrollTop = 0;
  $(`view-${view}`).focus({preventScroll:true});
}
function clearVideo() {
  video.pause(); video.removeAttribute('src'); video.removeAttribute('poster');
  delete video.dataset.episode; delete video.dataset.media; video.load();
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
function applyRoute(event) {
  // Back/forward can emit both popstate and hashchange for the same URL.
  // Render once so a second event does not replace the restored focus target.
  if (!state.data || routeRendering || (event && lastRenderedUrl === location.href)) return;
  lastRenderedUrl = location.href;
  routeRendering = true;
  const params = new URLSearchParams(location.hash.slice(1));
  const incoming = normalizeBenchmark(params.get('benchmark') || history.state?.gallery?.benchmark || pageBenchmark || (location.hash === '' ? 'libero' : state.benchmark));
  if (pageBenchmark && incoming !== pageBenchmark && benchmark(incoming)) {
    location.replace(`${benchmarkUrl(incoming)}${location.search}${location.hash}`);
    return;
  }
  if (incoming && benchmark(incoming)) {
    if (state.benchmark !== incoming) {
      state.suite='all'; state.search=''; state.outcome='all'; state.sort='default';
      $('task-search').value=''; $('outcome-filter').value='all'; $('sort-order').value='default';
    }
    state.benchmark = incoming;
  }
  renderCollection();
  const selectedTask = benchmark().tasks.find(task => task.id === params.get('task'));
  const requestedEpisode = params.get('episode');
  const missingRecording = Boolean(params.get('task') && !selectedTask) || Boolean(requestedEpisode && !selectedTask?.episodes.some(episode => episode.id === requestedEpisode));
  $('route-notice').hidden = !missingRecording;
  $('route-notice').textContent = missingRecording ? 'The requested recording is not part of this collection. Browse the current evaluation below.' : '';
  if (selectedTask && !missingRecording) {
    const previousEpisode = state.task?.id === selectedTask.id ? state.episode : null;
    state.task = selectedTask;
    state.episode = selectedTask.episodes.find(episode => episode.id === params.get('episode')) || previousEpisode || selectedTask.episodes[0];
    state.view = params.get('view') === 'demo' ? 'demo' : 'episode';
    renderPlayer();
    if (!dialog.open) { dialog.showModal(); dialog.scrollTop = 0; document.body.classList.add('modal-open'); $('close-dialog').focus(); }
  } else {
    if (dialog.open) {
      clearVideo(); dialog.close(); document.body.classList.remove('modal-open');
      const target = document.querySelector(`.task-card [data-task="${CSS.escape(state.returnTask || '')}"]${state.returnView === 'demo' ? '[data-open-demo]' : '[data-episode]'}`);
      if (target) target.focus({preventScroll:true});
    }
    state.task = null; state.episode = null; state.view = 'episode';
  }
  routeRendering = false;
}
function renderFeatured() {
  const preferred = {libero:{task:'libero_spatial_t00',label:'Spatial reasoning'},robotwin_nvidia10:{task:'robotwin_nvidia10_stack_blocks_three',label:'Building with two arms'},robocasa:{label:'Around the kitchen'},robodojo:{label:'Three views of every action'}};
  const available = pageBenchmark ? [benchmark(pageBenchmark)] : state.data.benchmarks;
  const selections = [available[0], ...(available.length > 1 ? [available.at(-1)] : [])].map((b,index) => ({benchmark:b.id,...preferred[b.id],secondary:index > 0}));
  $('hero-visual').innerHTML = selections.map(item => {
    const b = benchmark(item.benchmark), task = b.tasks.find(t => t.id === item.task) || b.tasks[0], episode = task.episodes[0];
    return `<button class="featured ${item.secondary ? 'featured-secondary' : ''}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" aria-label="Watch ${escapeHtml(item.label || task.name)} on ${escapeHtml(b.name)}"><div class="featured-image"><img src="${assetUrl(episode.poster)}" alt="${escapeHtml(task.name)} — recorded camera views" width="${episode.width}" height="${episode.height}" fetchpriority="${item.secondary ? 'auto' : 'high'}"><span class="featured-play" aria-hidden="true">▶</span></div><div class="featured-caption"><span>${escapeHtml(item.label || task.name)}</span><small>${escapeHtml(b.name)} · Episode 01 ↗</small></div></button>`;
  }).join('');
}
function filteredTasks() {
  const query = state.search.trim().toLowerCase();
  const tasks = benchmark().tasks.filter(task =>
    (state.suite === 'all' || task.suite === state.suite) &&
    (!query || `${task.name} ${task.instruction} ${task.episodes.map(episode => episode.instruction || '').join(' ')} ${task.suiteName} ${task.id}`.toLowerCase().includes(query)) &&
    (state.outcome === 'all' || (state.outcome === 'failures' ? task.failures > 0 : task.failures === 0))
  );
  if (state.sort !== 'default') tasks.sort((a,b) => state.sort === 'best' ? b.successRate - a.successRate : a.successRate - b.successRate);
  return tasks;
}
function renderCollection() {
  if (!state.data) return;
  const b = benchmark();
  document.querySelectorAll('a[data-benchmark]').forEach(button => {
    const active = button.dataset.benchmark === b.id;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  const suiteButtons = [{id:'all',name:'All tasks'}, ...(b.suites.length > 1 ? b.suites.map(suite => ({id:suite.id,name:prettySuite(suite.id),tasks:suite.tasks})) : [])];
  $('suite-tabs').innerHTML = suiteButtons.map(suite => `<button class="${state.suite === suite.id ? 'active' : ''}" data-suite="${escapeHtml(suite.id)}" aria-pressed="${state.suite === suite.id}">${escapeHtml(suite.name)}${suite.tasks !== undefined ? ` <span>${suite.tasks}</span>` : ''}</button>`).join('');
  const planned = b.tasks.length * b.protocol.episodesPerTask;
  $('collection-description').textContent = episodeCount(b) < planned
    ? `${episodeCount(b)} playable scored rollouts of ${planned} planned. ${sampling(b)}.`
    : `${sampling(b)}. All selected outcomes included.`;
  $('collection-demo-note').textContent = trainingDemoNote(b);
  $('collection-demo-note').hidden = !trainingDemoNote(b);
  const tasks = filteredTasks();
  const totalEpisodes = tasks.reduce((total,task) => total + task.episodes.length, 0);
  $('results-count').textContent = `${tasks.length} ${tasks.length === 1 ? 'task' : 'tasks'} · ${totalEpisodes} ${totalEpisodes === 1 ? 'rollout' : 'rollouts'}`;
  $('empty-state').hidden = tasks.length > 0;
  $('task-grid').innerHTML = tasks.map(task => {
    const episode = task.episodes[0], count = task.episodes.length, demo = taskDemo(task), available = demoAvailable(demo);
    return `<article class="task-card"><button class="media-thumb ${b.id}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" aria-label="Watch ${escapeHtml(task.name)}"><img src="${assetUrl(episode.poster)}" alt="Recorded views for ${escapeHtml(task.name)}" loading="lazy" decoding="async" width="${episode.width}" height="${episode.height}"><span class="thumb-count">${count} ${count === 1 ? 'rollout' : 'rollouts'}</span><span class="thumb-play" aria-hidden="true">▶</span></button><div class="task-body"><div class="task-meta"><span>${escapeHtml(`${b.name.toUpperCase()}${b.suites.length > 1 ? ` · ${prettySuite(task.suite)}` : ''}`)}</span><span class="task-rate ${task.failures ? 'imperfect' : ''}">${task.successes} / ${count} successful</span></div><button class="task-title" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${episode.id}" title="${escapeHtml(task.name)}">${escapeHtml(task.name)}</button><div class="sample-row">${task.episodes.map(ep => `<button class="sample-dot ${ep.status}" data-open-benchmark="${b.id}" data-task="${task.id}" data-episode="${ep.id}" aria-label="${escapeHtml(task.name)}, episode ${ep.index+1}: ${statusName(ep.status)}" title="Episode ${ep.index+1} · ${statusName(ep.status)}">${ep.index+1}</button>`).join('')}<span class="sample-caption">${count === 1 ? '1 episode' : 'Episodes'}</span></div><button class="task-demo ${available ? '' : 'unavailable'}" data-open-demo="${b.id}" data-task="${task.id}" aria-label="Training demo for ${escapeHtml(task.name)}${available ? '' : demo.notImported ? ', not imported' : ', unavailable'}"><span><span aria-hidden="true">${available ? '▷' : '○'}</span> Training demo</span><span class="demo-card-status">${available ? 'Watch ↗' : demo.notImported ? 'Not imported' : 'Unavailable'}</span></button></div></article>`;
  }).join('');
}
function renderPlayer() {
  const b = benchmark(), task = state.task, episode = state.episode;
  const isDemo = state.view === 'demo', demo = taskDemo(task), available = !isDemo || demoAvailable(demo);
  dialog.dataset.view = state.view;
  for (const view of ['episode','demo']) {
    const selected = state.view === view;
    $(`view-${view}`).setAttribute('aria-selected', String(selected));
    $(`view-${view}`).tabIndex = selected ? 0 : -1;
  }
  $('player-panel').setAttribute('aria-labelledby', `view-${state.view}`);
  $('episode-summary').hidden = isDemo;
  $('episode-chooser').hidden = isDemo;
  $('episode-navigation').hidden = isDemo;
  $('demo-source').hidden = !isDemo;
  $('demo-unavailable').hidden = available;
  $('demo-unavailable-title').textContent = demo.notImported ? 'Training demo not imported' : 'Training demo unavailable';
  video.hidden = !available;
  $('playback-controls').hidden = !available;
  $('camera-labels').hidden = !available;
  $('episode-facts').hidden = !available;
  $('download-video').hidden = !available;
  $('copy-link-label').textContent = isDemo ? 'Copy demo link' : 'Copy episode link';
  $('copy-status').textContent = ''; $('video-error').hidden = true;
  $('dialog-title').textContent = task.name;
  $('task-instruction-label').textContent = isDemo ? 'TRAINING TASK' : 'TASK INSTRUCTION';
  $('task-instruction').textContent = isDemo ? (demo.instruction || task.name) : (episode.instruction || task.instruction);
  if (isDemo) {
    $('dialog-eyebrow').textContent = `${b.name.toUpperCase()} / TRAINING DEMONSTRATION`;
    const source = demo.source || {};
    $('demo-dataset').textContent = source.dataset || (demo.notImported ? 'No training demonstration has been imported for this task.' : `${b.name} training dataset`);
    $('demo-source-link').hidden = !source.url;
    if (source.url) $('demo-source-link').href = source.url;
    else $('demo-source-link').removeAttribute('href');
    $('demo-source-episode').textContent = source.episode != null ? `Source episode: ${source.episode}${source.split ? ` · ${source.split}` : ''}` : '';
    $('demo-source-episode').hidden = source.episode == null;
    $('video-note').textContent = available ? 'A demonstration from the benchmark’s training dataset. Training demos are separate from the agent evaluation results.' : 'Training demonstrations are separate from the agent evaluation results.';
    if (!available) {
      $('demo-unavailable-reason').textContent = demo.reason || 'A training demonstration is not available for this task yet.';
      $('episode-facts').innerHTML = ''; $('camera-labels').innerHTML = '';
      $('download-video').removeAttribute('href'); $('download-video').removeAttribute('download');
      clearVideo();
      return;
    }
    const facts = [['Source FPS',demo.fps],['Frames',demo.frames],['Video length',duration(demo.durationSeconds)]];
    $('episode-facts').innerHTML = facts.map(([label,value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
    setCameras(demo.cameras || []);
    $('video-note').textContent += ` Playback at 1× uses the dataset’s ${demo.fps} FPS.`;
    setVideo(demo, `demo:${task.id}`, `${task.id}-training-demo`);
    return;
  }
  $('dialog-eyebrow').textContent = `${b.name.toUpperCase()} / ${b.suites.length > 1 ? prettySuite(task.suite).toUpperCase() : sampling(b).toUpperCase()} / RECORDED ROLLOUT`;
  $('episode-status').textContent = statusName(episode.status);
  $('episode-status').className = `status-badge ${episode.status}`;
  $('episode-number').textContent = `Episode ${pad(episode.index+1)} / ${pad(task.episodes.length)}`;
  $('task-score').textContent = `${task.successes}/${task.episodes.length} successful`;
  $('episode-buttons').innerHTML = task.episodes.map(ep => `<button class="episode-button ${ep.status} ${ep.id === episode.id ? 'active' : ''}" data-select-episode="${ep.id}" aria-pressed="${ep.id === episode.id}" aria-label="Episode ${ep.index+1}: ${statusName(ep.status)}">${pad(ep.index+1)}</button>`).join('');
  const facts = [['Seed',episode.seed],[b.protocol.stepsLabel,`${episode.steps} / ${episode.maxSteps}`],['Tool calls',episode.toolCalls],['Video length',duration(episode.durationSeconds)],['Episode wall time',elapsed(episode.wallSeconds)]];
  if (episode.initStateId != null) facts.splice(1,0,['Initial state',episode.initStateId]);
  if (Number.isFinite(episode.nativeScore)) facts.push(['Native score',`${(episode.nativeScore * 100).toFixed(1)}%`]);
  if (Number.isInteger(episode.layoutId)) facts.splice(1,0,['Layout',episode.layoutId]);
  $('episode-facts').innerHTML = facts.map(([label,value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
  setCameras(b.protocol.cameras);
  $('video-note').textContent = `${b.protocol.videoNote} Episode wall time includes preparation and cleanup.`;
  const index = task.episodes.findIndex(ep => ep.id === episode.id);
  $('previous-episode').disabled = index === 0; $('next-episode').disabled = index === task.episodes.length-1;
  setVideo(episode, `episode:${episode.id}`, episode.id);
  video.dataset.episode = episode.id;
}
function setCameras(cameras) {
  $('camera-labels').style.setProperty('--camera-count', cameras.length || 1);
  $('camera-labels').innerHTML = cameras.map(name => `<span>${escapeHtml(name)}</span>`).join('');
}
function setVideo(recording, key, filename) {
  const source = assetUrl(resolveVideoSource(recording));
  $('download-video').href = source; $('download-video').download = `${filename}.mp4`;
  if (video.dataset.media !== key) {
    video.pause(); video.poster = assetUrl(recording.poster); video.src = source; video.preload = 'metadata';
    video.dataset.media = key; delete video.dataset.episode;
    video.style.aspectRatio = `${recording.width}/${recording.height}`; video.load();
    video.playbackRate = Number($('playback-speed').value);
  }
}
function moveEpisode(direction) {
  if (state.view !== 'episode') return;
  const index = state.task.episodes.findIndex(ep => ep.id === state.episode.id);
  const next = state.task.episodes[index+direction];
  if (next) openEpisode(state.benchmark,state.task.id,next.id);
}
document.addEventListener('click', event => {
  const demo = event.target.closest('[data-open-demo]');
  if (demo) { openDemo(demo.dataset.openDemo,demo.dataset.task); return; }
  const opener = event.target.closest('[data-open-benchmark]');
  if (opener) { openEpisode(opener.dataset.openBenchmark,opener.dataset.task,opener.dataset.episode); return; }
  const b = event.target.closest('a[data-benchmark]');
  if (b && pageBenchmark === b.dataset.benchmark && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault(); switchBenchmark(b.dataset.benchmark,b.classList.contains('benchmark-summary')); return;
  }
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
for (const view of ['episode','demo']) $(`view-${view}`).addEventListener('click',()=>switchPlayerView(view));
$('player-views').addEventListener('keydown',event=>{
  if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
  event.preventDefault();
  switchPlayerView(event.key === 'Home' ? 'episode' : event.key === 'End' ? 'demo' : state.view === 'demo' ? 'episode' : 'demo');
});
$('playback-speed').addEventListener('change',event=>{video.playbackRate=Number(event.target.value);});
video.addEventListener('error',()=>{if(video.hasAttribute('src'))$('video-error').hidden=false;});
$('copy-link').addEventListener('click',async()=>{
  try { await navigator.clipboard.writeText(location.href); $('copy-status').textContent=state.view === 'demo' ? 'Demo link copied.' : 'Episode link copied.'; }
  catch { $('copy-status').textContent=location.href; }
});
window.addEventListener('hashchange',applyRoute);
window.addEventListener('popstate',applyRoute);
Promise.all([
  fetch(assetUrl('data/gallery.json')).then(response=>{if(!response.ok)throw new Error('Manifest unavailable');return response.json();}),
  fetch(assetUrl('data/task-demos.json')).then(response=>{if(!response.ok)throw new Error('Training demo catalog unavailable');return response.json();})
    .then(demos=>{if(!demos || !demos.tasks || typeof demos.tasks !== 'object' || Array.isArray(demos.tasks))throw new Error('Invalid training demo catalog');return demos;})
    .catch(()=>({tasks:{},unavailableReason:'The training demo catalog could not load. Reload this page to try again.'}))
]).then(([data,demos])=>{
  const available = data.benchmarks.filter(b => b.id !== 'robotwin' && b.tasks.length > 0 && b.tasks.every(task => task.episodes.length > 0))
    .map(b => b.id === 'robotwin_nvidia10' ? {...b, name:'Robotwin'} : b);
  if (!available.length) throw new Error('No published episodes available');
  state.data={...data,benchmarks:available};
  state.demos=demos && typeof demos.tasks === 'object' && demos.tasks !== null ? demos : {tasks:{}};
  if (!benchmark()) state.benchmark=available[0].id;
  renderOverview(); renderFeatured(); applyRoute();
}).catch(error=>{console.error(error);$('load-error').hidden=false;$('results-count').textContent='Collection unavailable';});
