'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  const versions = ['original', 'revised_r1', 'revised_r2', 'final'];
  const versionNames = {original:'Original', revised_r1:'Revision 1', revised_r2:'Revision 2', final:'Final evaluation'};
  const suiteNames = {libero_spatial:'LIBERO Spatial', libero_object:'LIBERO Object', libero_goal:'LIBERO Goal', libero_10:'LIBERO Long'};
  const suiteOrder = Object.keys(suiteNames);
  const notes = {
    original:'Original task instructions, evaluated across all 40 tasks.',
    revised_r1:'90 new episodes across nine tasks, using the first instruction revision.',
    revised_r2:'20 new episodes across two tasks, using the second instruction revision.',
    final:'400 evaluations: 310 unchanged original + 70 revision-1 + 20 revision-2 episodes. This composite is not 400 new rollouts.'
  };
  const state = {episodes:[], byId:new Map(), version:'original', suite:'all', outcome:'all', search:'', active:null, pushed:false, opener:null};
  const dialog = $('#player-dialog');
  const video = $('#episode-video');
  const html = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const pairKey = episode => episode.pairKey || `${episode.suite}/${episode.taskId}/${episode.initStateIndex}`;
  const taskKey = episode => `${episode.suite}/${episode.taskId}`;
  const status = episode => episode.nativeSuccess === true ? 'success' : episode.nativeSuccess === false ? 'failure' : 'unknown';
  const outcomeName = episode => episode.nativeSuccess === true ? 'Benchmark success' : episode.nativeSuccess === false ? 'Benchmark failure' : 'Outcome unavailable';
  const mediaURL = path => new URL(path, window.GALLERY_MEDIA_BASE).href;
  const episodeLabel = episode => String(Number(episode.initStateIndex) + 1).padStart(2,'0');
  const taskLabel = episode => `Task ${String(episode.taskId).padStart(2,'0')}`;
  const duration = seconds => Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2,'0')}` : '—';
  const cleanTitle = episode => episode.originalInstruction || episode.instruction || `${suiteNames[episode.suite]} · ${taskLabel(episode)}`;

  function highlightChanges(original, revised) {
    const before = String(original || '').match(/\S+/g) || [];
    const after = String(revised || '').match(/\S+/g) || [];
    const dp = Array.from({length:before.length+1}, () => new Uint16Array(after.length+1));
    for (let i=before.length-1; i>=0; i--) for (let j=after.length-1; j>=0; j--) dp[i][j] = before[i] === after[j] ? dp[i+1][j+1]+1 : Math.max(dp[i+1][j],dp[i][j+1]);
    const unchanged = new Set();
    let i=0,j=0;
    while (i<before.length && j<after.length) {
      if (before[i] === after[j]) {unchanged.add(j); i++; j++;}
      else if (dp[i+1][j] >= dp[i][j+1]) i++;
      else j++;
    }
    return after.map((word,index) => unchanged.has(index) ? html(word) : `<strong>${html(word)}</strong>`).join(' ');
  }

  function versionEpisodes() {
    return state.episodes.filter(episode => state.version === 'final' ? episode.final === true : episode.stage === state.version);
  }

  function writeURL(push=false, episodeId=state.active?.id) {
    const url = new URL(location.href);
    for (const key of ['version','suite','outcome','q','episode']) url.searchParams.delete(key);
    if (state.version !== 'original') url.searchParams.set('version', state.version);
    if (state.suite !== 'all') url.searchParams.set('suite',state.suite);
    if (state.outcome !== 'all') url.searchParams.set('outcome',state.outcome);
    if (state.search) url.searchParams.set('q',state.search);
    if (episodeId) url.searchParams.set('episode',episodeId);
    history[push ? 'pushState' : 'replaceState']({},'',url);
  }

  function readURL() {
    const params = new URL(location.href).searchParams;
    state.version = versions.includes(params.get('version')) ? params.get('version') : 'original';
    state.suite = suiteOrder.includes(params.get('suite')) ? params.get('suite') : 'all';
    state.outcome = ['success','failure'].includes(params.get('outcome')) ? params.get('outcome') : 'all';
    state.search = params.get('q') || '';
    $('#search').value = state.search;
    $('#suite').value = state.suite;
    $('#outcome').value = state.outcome;
    renderCollection();
    const episode = state.byId.get(params.get('episode'));
    if (episode) showEpisode(episode,false);
    else hidePlayer();
  }

  function renderCollection() {
    document.querySelectorAll('[data-version]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.version === state.version)));
    $('#version-note').textContent = notes[state.version];
    const all = versionEpisodes();
    const successes = all.filter(episode => episode.nativeSuccess === true).length;
    $('#version-score').textContent = all.length ? `${successes} / ${all.length} benchmark successes · ${(100*successes/all.length).toFixed(1)}%` : '';
    const query = state.search.trim().toLowerCase();
    const filtered = all.filter(episode => (state.suite === 'all' || episode.suite === state.suite) && (state.outcome === 'all' || status(episode) === state.outcome) && (!query || `${episode.taskName} ${episode.instruction} ${episode.originalInstruction} ${suiteNames[episode.suite]} ${taskLabel(episode)}`.toLowerCase().includes(query)));
    const groups = new Map();
    for (const episode of filtered) {
      const key = taskKey(episode);
      if (!groups.has(key)) groups.set(key,[]);
      groups.get(key).push(episode);
    }
    const tasks = [...groups.values()].sort((a,b) => suiteOrder.indexOf(a[0].suite)-suiteOrder.indexOf(b[0].suite) || Number(a[0].taskId)-Number(b[0].taskId));
    $('#task-grid').innerHTML = tasks.map(episodes => {
      episodes.sort((a,b) => Number(a.initStateIndex)-Number(b.initStateIndex));
      const episode = episodes[0];
      const passed = episodes.filter(item => item.nativeSuccess === true).length;
      const image = episode.poster ? `<img src="${html(mediaURL(episode.poster))}" loading="lazy" decoding="async" alt="${html(cleanTitle(episode))}" width="640" height="320">` : '<span class="poster-unavailable">LIBERO evaluation</span>';
      return `<article class="task-card" data-task="${html(taskKey(episode))}"><button class="media-thumb" data-episode="${html(episode.id)}" aria-label="Watch ${html(cleanTitle(episode))}, episode ${episodeLabel(episode)}">${image}<span class="thumb-version">${html(versionNames[episode.stage])}</span><span class="thumb-play" aria-hidden="true">▶</span></button><div class="task-body"><div class="task-meta"><span>${html(suiteNames[episode.suite] || episode.suite)} · ${taskLabel(episode)}</span><span class="task-rate ${passed !== episodes.length ? 'imperfect' : ''}">${passed}/${episodes.length} successful</span></div><button class="task-title" data-episode="${html(episode.id)}">${html(episode.instruction)}</button><div class="sample-row" aria-label="Episodes">${episodes.map(item => `<button class="sample-dot ${status(item)}" data-episode="${html(item.id)}" aria-label="Episode ${episodeLabel(item)}: ${outcomeName(item)}" title="Initial state ${item.initStateIndex} · ${outcomeName(item)}">${episodeLabel(item)}</button>`).join('')}</div></div></article>`;
    }).join('');
    $('#result-count').textContent = `${filtered.length} episode${filtered.length===1?'':'s'} across ${tasks.length} task${tasks.length===1?'':'s'} · ${versionNames[state.version]}`;
    $('#empty-state').hidden = filtered.length > 0;
  }

  function showEpisode(episode,push=false) {
    if (!episode) return;
    const wasOpen = dialog.open;
    const changed = state.active?.id !== episode.id;
    state.active = episode;
    $('#player-eyebrow').textContent = `${suiteNames[episode.suite] || episode.suite} · ${taskLabel(episode)} · EPISODE ${episodeLabel(episode)}`;
    $('#player-heading').textContent = cleanTitle(episode);
    const outcome = $('#player-outcome');
    outcome.textContent = outcomeName(episode);
    outcome.className = `outcome-badge ${status(episode)}`;
    const related = state.episodes.filter(item => pairKey(item) === pairKey(episode)).sort((a,b) => versions.indexOf(a.stage)-versions.indexOf(b.stage));
    $('#player-versions').innerHTML = related.map(item => `<button data-player-episode="${html(item.id)}" aria-pressed="${item.id===episode.id}">${versionNames[item.stage]}</button>`).join('');
    $('#pair-note').textContent = related.length > 1 ? 'Switch versions to compare the same initial state.' : 'The instruction for this task was unchanged; no revised rollout is included.';
    const taskEpisodes = state.episodes.filter(item => taskKey(item) === taskKey(episode) && item.stage === episode.stage).sort((a,b) => Number(a.initStateIndex)-Number(b.initStateIndex));
    $('#episode-buttons').innerHTML = taskEpisodes.map(item => `<button class="episode-button ${status(item)}" data-player-episode="${html(item.id)}" aria-pressed="${item.id===episode.id}" aria-label="Episode ${episodeLabel(item)}: ${outcomeName(item)}">${episodeLabel(item)}</button>`).join('');
    $('#player-init').textContent = String(episode.initStateIndex);
    $('#player-seed').textContent = episode.seed ?? '—';
    $('#player-duration').textContent = duration(episode.duration);
    $('#player-version').textContent = versionNames[episode.stage];
    const original = episode.originalInstruction || related.find(item => item.stage === 'original')?.instruction || episode.instruction;
    const revised = episode.stage === 'original' ? related.filter(item => item.stage !== 'original').at(-1) : episode;
    $('#original-label').textContent = `ORIGINAL INSTRUCTION${episode.stage === 'original' ? ' · PLAYING' : ''}`;
    $('#original-instruction').textContent = original;
    $('#revised-instruction-panel').hidden = !revised;
    if (revised) {
      $('#revised-label').textContent = `${versionNames[revised.stage].toUpperCase()} · ${episode.stage !== 'original' ? 'PLAYING · ' : ''}EDITS IN BOLD`;
      $('#revised-instruction').innerHTML = highlightChanges(original,revised.instruction);
    }
    const download = new URL(mediaURL(episode.video));
    download.searchParams.set('download','true');
    $('#download-video').href = download.href;
    $('#download-video').download = `${episode.id}.mp4`;
    $('#copy-status').textContent = '';
    if (changed || !video.getAttribute('src')) {
      video.pause();
      $('#video-error').hidden = true;
      video.src = mediaURL(episode.video);
      if (episode.poster) video.poster = mediaURL(episode.poster); else video.removeAttribute('poster');
      video.load();
      video.playbackRate = Number($('#playback-speed').value);
    }
    if (!wasOpen) {
      state.opener = document.activeElement;
      dialog.showModal();
    }
    if (push) {writeURL(true,episode.id); state.pushed=true;}
    else if (wasOpen) writeURL(false,episode.id);
  }

  function hidePlayer() {
    video.pause();
    video.removeAttribute('src');
    video.load();
    state.active = null;
    if (dialog.open) dialog.close();
    if (state.opener?.isConnected) state.opener.focus({preventScroll:true});
  }

  function closePlayer() {
    if (state.pushed) {state.pushed=false; history.back();}
    else {hidePlayer(); writeURL(false,null);}
  }

  async function load() {
    $('#load-error').hidden = true;
    try {
      const response = await fetch('episodes.json');
      if (!response.ok) throw new Error(`Episode metadata: HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data) || !data.length) throw new Error('Episode metadata is empty');
      state.episodes = data;
      state.byId = new Map(data.map(episode => [episode.id,episode]));
      readURL();
    } catch (error) {
      $('#load-error').hidden = false;
      $('#result-count').textContent = 'Collection unavailable';
      console.error(error);
    }
  }

  $('#version-tabs').addEventListener('click',event => {
    const button = event.target.closest('[data-version]');
    if (!button) return;
    state.version = button.dataset.version;
    renderCollection(); writeURL();
  });
  for (const [selector,key,eventType] of [['#search','search','input'],['#suite','suite','change'],['#outcome','outcome','change']]) $(selector).addEventListener(eventType,event => {state[key]=event.target.value; renderCollection(); writeURL();});
  $('#task-grid').addEventListener('click',event => {
    const button = event.target.closest('[data-episode]');
    if (button) showEpisode(state.byId.get(button.dataset.episode),true);
  });
  dialog.addEventListener('click',event => {
    const button = event.target.closest('[data-player-episode]');
    if (button) showEpisode(state.byId.get(button.dataset.playerEpisode),false);
    else if (event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom) closePlayer();
    }
  });
  dialog.addEventListener('cancel',event => {event.preventDefault(); closePlayer();});
  $('#close-player').addEventListener('click',closePlayer);
  $('#playback-speed').addEventListener('change',event => {video.playbackRate=Number(event.target.value);});
  video.addEventListener('error',() => {if (video.getAttribute('src')) $('#video-error').hidden=false;});
  $('#copy-link').addEventListener('click',async () => {
    try {await navigator.clipboard.writeText(location.href); $('#copy-status').textContent='Episode link copied.';}
    catch {$('#copy-status').textContent='Copy the episode URL from your browser’s address bar.';}
  });
  $('#reset-filters').addEventListener('click',() => {state.suite='all'; state.outcome='all'; state.search=''; $('#suite').value='all'; $('#outcome').value='all'; $('#search').value=''; renderCollection(); writeURL();});
  $('#retry-load').addEventListener('click',load);
  window.addEventListener('popstate',readURL);
  load();
})();
