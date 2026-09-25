(() => {
  'use strict';
  const siteRoot = new URL('./', document.currentScript.src);
  let hosting;
  function redirectLegacyHash() {
    const old = new URLSearchParams(location.hash.slice(1));
    if (!['benchmark', 'task', 'episode', 'view'].some(key => old.has(key))) return false;
    const names = {libero:'libero',robotwin:'robotwin',robotwin_nvidia10:'robotwin',robocasa:'robocasa',robodojo:'robodojo'};
    const benchmark = old.get('benchmark') || (old.get('task') || old.get('episode') || '').split('_')[0];
    const target = new URL(`gallery/${names[benchmark] ? names[benchmark] + '/' : ''}index.html`, hosting.galleryUrl);
    target.search = location.search;
    target.hash = location.hash;
    location.replace(target.href);
    return true;
  }
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct = value => (100 * value).toFixed(2);
  // The essay's selected recordings ship with this site; the full gallery stays on HF.
  const url = path => new URL(path, siteRoot).href;
  const downloadUrl = url;
  const suiteNames = {libero_10:'Long',libero_goal:'Goal',libero_object:'Object',libero_spatial:'Spatial'};
  const taskLabel = (suite,id) => `${suiteNames[suite]} t${String(id).padStart(2,'0')}`;
  const liberoEpisodeLabel = item => `LIBERO ${suiteNames[item.suite]} · Task ${String(item.taskId).padStart(2,'0')} · EPISODE ${String(item.rolloutIndex+1).padStart(2,'0')}`;
  const liberoExamples = {
    'wine-rack': {taskId:'libero_goal_t09',title:'A failure becomes a success',detail:'At initial state 3, the original rollout is judged complete by the agent but rejected by the benchmark; the revised rollout passes. Across all ten initial states, native successes increase from 7/10 to 10/10.'},
    'book-compartment': {taskId:'libero_10_t05',title:'A failure becomes a success',detail:'At initial state 0, the original rollout is judged complete by the agent but rejected by the benchmark; the revised rollout passes. Across all ten initial states, native successes increase from 0/10 to 10/10.'}
  };
  // Emphasize the added goal information in these two editorial examples.
  const robotwinInstructionHighlights = {
    adjust_bottle_r01: ['keep it upright', 'move it to the right side of the table.'],
    place_object_basket_r01: ['and then lift the basket with the toy car inside.']
  };
  const liberoFailureDetails = {
    'plate-control-budget': ['Sustained contact while pushing a plate', 'The plate must slide into a small region near the stove. The policy repeatedly repositions the gripper but does not finish within 500 control steps: sustained contact and small positional corrections remain difficult.'],
    'bottom-drawer-sequence': ['Placement followed by drawer closure', 'The bowl reaches the drawer, but the drawer remains open after 500 control steps. The task requires a change of contact after placement, followed by a controlled push to complete the closure.']
  };
  const robotwinFailureDetails = {
    dump_bin_bigbin_r01: {title:'Emptying a bin onto the tabletop',detail:'The instruction asks the robot to lift and tip the bin so its balls pour onto the tabletop. This motion requires control of the bin while its contents move.'},
    scan_object_r02: {title:'Holding and aiming two objects',detail:'The two arms must hold the tea box and scanner at the same time, then aim the scanner face at the box. This requires coordinating the positions and orientations of both objects.'}
  };
  let reviewCorrections = new Map();
  function highlightInstructionChanges(original, improved, phrases) {
    if (phrases?.length) {
      let cursor = 0;
      const spans = [];
      for (const phrase of phrases) {
        const start = improved.indexOf(phrase, cursor);
        // If an instruction is edited later, fall back to the word comparison.
        if (start < 0) return highlightInstructionChanges(original, improved);
        spans.push(esc(improved.slice(cursor, start)), `<strong>${esc(phrase)}</strong>`);
        cursor = start + phrase.length;
      }
      return spans.join('') + esc(improved.slice(cursor));
    }
    // Match words case-insensitively; retain the improved sentence's exact
    // whitespace and punctuation, and escape every span before adding markup.
    const wordPattern = /[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)*/gu;
    const before = Array.from(original.matchAll(wordPattern), match => match[0].toLowerCase());
    const after = Array.from(improved.matchAll(wordPattern));
    const lengths = Array.from({length:before.length + 1}, () => new Uint16Array(after.length + 1));
    for (let i = before.length - 1; i >= 0; i--) {
      for (let j = after.length - 1; j >= 0; j--) {
        lengths[i][j] = before[i] === after[j][0].toLowerCase()
          ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
      }
    }
    const unchanged = new Set();
    let i = 0, j = 0;
    while (i < before.length && j < after.length) {
      if (before[i] === after[j][0].toLowerCase()) { unchanged.add(j); i++; j++; }
      else if (lengths[i + 1][j] >= lengths[i][j + 1]) i++;
      else j++;
    }
    let cursor = 0;
    const spans = after.map((match,index) => {
      const prefix = esc(improved.slice(cursor, match.index));
      cursor = match.index + match[0].length;
      return prefix + (unchanged.has(index) ? esc(match[0]) : `<strong>${esc(match[0])}</strong>`);
    });
    return spans.join('') + esc(improved.slice(cursor));
  }
  function scoreCard(stats, after) {
    // Recomputed from the source records and documented human adjudications.
    const accepted = stats.matrix.success.benchSuccess;
    const disagreement = stats.matrix.success.benchFailure;
    const incomplete = stats.matrix.failure.benchFailure;
    return `<div class="score-card ${after ? 'after' : 'before'}"><div class="score-top"><h3>${after ? 'After · revised composite' : 'Before · original instructions'}</h3><span>n = ${stats.n}</span></div><p class="score-value">${pct(stats.ias)}<span>%</span></p><p class="score-label">Instinct-alignment score</p><p class="score-equation">1 − ${disagreement} / ${stats.n} = ${pct(stats.ias)}%</p><table class="cross-table"><caption>Agent’s completion judgment × benchmark’s verdict</caption><thead><tr><th scope="col">Agent’s completion judgment</th><th scope="col">Bench judges success</th><th scope="col">Bench judges failure</th></tr></thead><tbody><tr class="success"><th scope="row">Agent considers complete</th><td>${accepted}</td><td class="mismatch">${disagreement}</td></tr><tr class="failure"><th scope="row">Agent does not consider complete</th><td class="not-applicable" aria-label="Not applicable under the reporting convention">&#92;</td><td>${incomplete}</td></tr></tbody></table><p class="native-score">Bench judges success: <strong>${stats.benchSuccess}/${stats.n} · ${pct(stats.benchSuccess / stats.n)}%</strong></p></div>`;
  }
  function robotwinScoreCard(stats, title, after) {
    const accepted = stats.agentSuccessBenchSuccess;
    const disagreement = stats.agentSuccessBenchFalse;
    const incomplete = stats.agentFalseBenchFalse;
    const unavailable = stats.agentUnknownBenchFalse || 0;
    const alignment = unavailable ? `${pct(stats.instinctAlignmentBounds.min)}–${pct(stats.instinctAlignmentBounds.max)}` : pct(stats.instinctAlignment);
    const equation = unavailable ? `Exact IAS awaits ${unavailable} unpublished agent judgments.` : `1 − ${disagreement} / ${stats.n} = ${alignment}%`;
    const unavailableRow = unavailable ? `<tr class="unclassified"><th scope="row">Agent judgment not published</th><td class="not-applicable" aria-label="Not applicable under the reporting convention">&#92;</td><td>${unavailable}</td></tr>` : '';
    return `<div class="score-card ${after ? 'after' : 'before'}"><div class="score-top"><h3>${esc(title)}</h3><span>n = ${stats.n}</span></div><p class="score-value${unavailable ? ' score-range' : ''}">${alignment}<span>%</span></p><p class="score-label">Instinct-alignment score${unavailable ? ' · possible range' : ''}</p><p class="score-equation">${equation}</p><table class="cross-table"><caption>Agent’s completion judgment × benchmark’s verdict</caption><thead><tr><th scope="col">Agent’s completion judgment</th><th scope="col">Bench judges success</th><th scope="col">Bench judges failure</th></tr></thead><tbody><tr class="success"><th scope="row">Agent considers complete</th><td>${accepted}</td><td class="mismatch">${disagreement}${unavailable ? ' confirmed' : ''}</td></tr><tr class="failure"><th scope="row">Agent does not consider complete</th><td class="not-applicable" aria-label="Not applicable under the reporting convention">&#92;</td><td>${incomplete}</td></tr>${unavailableRow}</tbody></table><p class="native-score">Bench judges success: <strong>${stats.benchSuccess}/${stats.n} · ${pct(stats.benchSuccess / stats.n)}%</strong></p></div>`;
  }
  function renderComparison(data) {
    if (data.before.n !== 400 || data.after.n !== 400) throw new Error('The comparison requires all 400 episodes');
    document.querySelector('#comparison').innerHTML = scoreCard(data.before, false) + scoreCard(data.after, true);
    document.querySelector('#scope-note').textContent = 'All 40 tasks: 400 original episodes versus a composite preserving 310 original episodes and replacing all 90 episodes from the nine revised tasks.';
  }
  function renderInstructions(data) {
    const taskIds = Object.values(liberoExamples).map(example => example.taskId);
    document.querySelector('#instruction-rows').innerHTML = taskIds.map(id => data.tasks.find(task => task.id === id)).map(task => {
      const delta = task.after.benchSuccess - task.before.benchSuccess;
      return `<tr data-task="${esc(task.id)}"><th scope="row" class="task-ref"><span>${esc(taskLabel(task.suite,task.taskId))}</span></th><td class="instruction-original">${esc(task.instructionBefore)}</td><td class="instruction-improved">${highlightInstructionChanges(task.instructionBefore,task.instructionAfter)}</td><td>${task.before.benchSuccess}/10 → <strong>${task.after.benchSuccess}/10</strong><span class="delta ${delta < 0 ? 'negative' : ''}">${delta > 0 ? '+' : ''}${delta} successes</span></td></tr>`;
    }).join('');
  }
  function clipMarkup(clip,label) {
    const stage = {baseline:'baseline',r1:'round1',r2:'round2'}[clip.stage];
    const correction = reviewCorrections.get(`${stage}:${clip.episodeKey}`);
    const assessment = correction ? 'Agent claimed completion · corrected to incomplete' : clip.nativeSuccess ? 'Bench judges success' : clip.agentAssessment === 'visually_complete' ? 'Agent considers the task complete' : clip.agentAssessment === 'unable_to_continue' ? 'Agent reports unable to continue' : 'No completion claim · control budget exhausted';
    return `<figure class="clip"><div class="clip-header"><span>${esc(label)}</span><span class="status ${clip.status}">Bench judges ${clip.nativeSuccess ? 'success' : 'failure'}</span></div><video controls playsinline preload="none" poster="${esc(url(clip.poster))}" src="${esc(url(clip.video))}" aria-label="${esc(label + ': ' + liberoEpisodeLabel(clip))}"></video><figcaption><p class="clip-instruction">“${esc(clip.instruction)}”</p><p class="clip-meta">${esc(clip.stageLabel)} · seed ${clip.seed} · init ${clip.initStateId} · ${clip.steps} steps<br>${esc(assessment)} · <a href="${esc(downloadUrl(clip.video))}" download>Download MP4 ↓</a></p></figcaption></figure>`;
  }
  function failureClipMarkup(clip, label, instruction, metadata, instructionLabel = '') {
    return `<figure class="clip"><div class="clip-header"><span>${esc(label)}</span><span class="status failure">Failed episode</span></div><video controls playsinline preload="none" poster="${esc(url(clip.poster))}" src="${esc(url(clip.video))}" aria-label="${esc(label + ': ' + clip.episodeKey)}"></video><figcaption><p class="clip-instruction">${instructionLabel ? `<span class="instruction-label">${esc(instructionLabel)}</span>` : ''}<span class="instruction-text">“${esc(instruction)}”</span></p><p class="clip-meta">${esc(metadata)} · <a href="${esc(downloadUrl(clip.video))}" download>Download MP4 ↓</a></p></figcaption></figure>`;
  }
  function failureTaskRate(before, after) {
    return `<div class="task-rate negative"><span>Task success · before → after</span><strong>${Math.round(100 * before.successes / before.episodes)}% → ${Math.round(100 * after.successes / after.episodes)}%</strong><span>${before.successes}/${before.episodes} → ${after.successes}/${after.episodes} episodes</span></div>`;
  }
  function renderMedia(media, alignment) {
    document.querySelector('#paired-cases').innerHTML = Object.entries(liberoExamples).map(([id,example]) => {
      const pair = media.pairs.find(item => item.id === id);
      const before = media.clips[pair.before], after = media.clips[pair.after];
      const sources = (pair.sourceLinks || []).filter(link => link.label === 'Task BDDL');
      return `<section class="case" id="case-${esc(pair.id)}"><div class="case-head"><div><p class="eyebrow">${esc(liberoEpisodeLabel(pair))}</p><h3>${esc(example.title)}</h3></div><div class="task-rate ${pair.afterTask.successes < pair.beforeTask.successes ? 'negative' : ''}"><span>Task native successes</span><strong>${pair.beforeTask.successes}/10 → ${pair.afterTask.successes}/10</strong></div></div><div class="paired-videos">${clipMarkup(before,'Before')}${clipMarkup(after,'After')}</div><div class="case-foot"><p class="case-detail">${esc(example.detail)}</p><div class="case-actions"><button class="play-pair" type="button">Play both from start</button><span class="case-source">Same initial state ${pair.initStateId} · ${sources.map(link => `<a href="${esc(link.url)}">Native task definition ↗</a>`).join(' · ')}</span><span class="play-status" role="status"></span></div></div></section>`;
    }).join('');
    document.querySelector('#failure-cases').innerHTML = Object.entries(liberoFailureDetails).map(([id,[title,detail]]) => {
      const item = media.failureCases.find(record => record.id === id);
      const clip = media.clips[item.clip];
      if (clip.nativeSuccess) throw new Error(`Expected a failed LIBERO episode: ${item.clip}`);
      const label = clip.stage === 'baseline' ? 'Unchanged instruction · baseline recording' : `Revised instruction · revision ${clip.stage.slice(1)}`;
      const metadata = `seed ${clip.seed} · init ${clip.initStateId} · ${clip.steps} control steps`;
      const task = alignment.tasks.find(task => task.suite === clip.suite && task.taskId === clip.taskId);
      const rates = ['before','after'].map(phase => ({successes:task[phase].benchSuccess,episodes:task[phase].n}));
      return `<section class="failure-case" id="failure-${esc(item.id)}"><div class="failure-description"><p class="eyebrow">${esc(taskLabel(clip.suite,clip.taskId))}</p><h3>${esc(title)}</h3>${failureTaskRate(...rates)}<p>${esc(detail)}</p></div>${failureClipMarkup(clip,label,clip.instruction,metadata)}</section>`;
    }).join('');
  }
  function bindVideoControls() {
    document.querySelectorAll('.play-pair').forEach(button => {
      const section = button.closest('.case');
      const videos = Array.from(section.querySelectorAll('video'));
      button.addEventListener('click', async () => {
        if (videos.some(video => !video.paused)) {
          videos.forEach(video => video.pause());
          button.textContent = 'Play both from start';
          return;
        }
        document.querySelectorAll('video').forEach(video => video.pause());
        document.querySelectorAll('.play-pair').forEach(other => { other.textContent = 'Play both from start'; });
        videos.forEach(video => { video.currentTime = 0; });
        button.disabled = true;
        const outcomes = await Promise.allSettled(videos.map(video => video.play()));
        button.disabled = false;
        const failed = outcomes.some(outcome => outcome.status === 'rejected');
        if (failed) videos.forEach(video => video.pause());
        section.querySelector('.play-status').textContent = failed ? 'Use each video’s play control to start playback.' : '';
        button.textContent = failed ? 'Play both from start' : 'Pause both';
      });
      videos.forEach(video => video.addEventListener('ended', () => {
        if (videos.every(item => item.paused || item.ended)) button.textContent = 'Play both from start';
      }));
    });
    // Posters load immediately; full recordings load only when the reader chooses to play.
    document.querySelectorAll('.clip video').forEach(video => video.addEventListener('error', () => {
      const meta = video.closest('figure').querySelector('.clip-meta');
      if (!meta.querySelector('.media-error')) meta.insertAdjacentHTML('beforeend','<br><span class="media-error" role="alert">Playback unavailable. Try the MP4 download link.</span>');
    }));
  }
  function outcomeText(record) {
    const bench = record.benchSuccess ? 'bench judges success' : 'bench judges failure';
    if (!record.agentOutcome) return bench;
    const agent = record.agentOutcome === 'visually_complete' ? 'agent considers complete' : 'agent does not consider complete';
    return `${agent} / ${bench}`;
  }
  const robotwinEpisodeLabel = item => `RoboTwin · Task ${String(item.taskId).padStart(2,'0')} · EPISODE ${String(item.episodeNumber).padStart(2,'0')}`;
  const benchOutcome = record => record.benchSuccess ? 'success' : 'failure';
  function robotwinClipMarkup(item, stage) {
    const clip = item[stage];
    const label = stage === 'before' ? 'Before' : 'After';
    return `<figure class="clip"><div class="clip-header"><span>${label}</span><span class="status ${benchOutcome(clip)}">Bench judges ${benchOutcome(clip)}</span></div><video controls playsinline preload="none" poster="${esc(url(clip.poster))}" src="${esc(url(clip.video))}" aria-label="${esc(`${label}: ${robotwinEpisodeLabel(item)}`)}"></video><figcaption><p class="clip-instruction">“${esc(clip.instruction)}”</p><p class="clip-meta">seed ${esc(clip.seed)} · ${esc(clip.steps)} actions · ${esc(clip.toolCalls)} tool calls · ${Math.round(clip.wallSeconds)} s wall time<br>${esc(outcomeText(clip))} · <a href="${esc(downloadUrl(clip.video))}" download>Download MP4 ↓</a></p></figcaption></figure>`;
  }
  function robotwinCaseMarkup(item) {
    return `<section class="case robotwin-case" data-episode="${esc(item.episodeKey)}" id="robotwin-case-${esc(item.episodeKey)}"><div class="case-head"><div><p class="eyebrow">${esc(robotwinEpisodeLabel(item))}</p><h3>${esc(item.title)}</h3></div><div class="task-rate ${item.after.benchSuccess ? '' : 'negative'}"><span>Bench outcome</span><strong>${benchOutcome(item.before)} → ${benchOutcome(item.after)}</strong></div></div><div class="paired-videos">${robotwinClipMarkup(item,'before')}${robotwinClipMarkup(item,'after')}</div><div class="case-foot"><div class="case-actions"><button class="play-pair" type="button">Play both from start</button><span class="case-source">Same scene seed ${esc(item.before.seed)} · <a href="${esc(item.galleryUrl)}">View episode in gallery ↗</a></span><span class="play-status" role="status"></span></div></div></section>`;
  }
  function renderRobotwin(data) {
    const {before, after, rerunsOnly} = data;
    document.querySelector('#robotwin-results-note').innerHTML = `In the latest gallery results, native success rises from <strong>${before.benchSuccess}/${before.n} to ${after.benchSuccess}/${after.n}</strong> (${pct(before.benchmarkSuccessRate)}% → ${pct(after.benchmarkSuccessRate)}%). Of the ${rerunsOnly.episodes} revised episodes, <strong>${rerunsOnly.nativeSuccesses} now pass the benchmark</strong>; ${rerunsOnly.nativeFailuresIncludingTimeout} remain unsuccessful, including ${rerunsOnly.timeouts} timeout${rerunsOnly.timeouts === 1 ? '' : 's'}.`;
    document.querySelector('#robotwin-comparison').innerHTML =
      robotwinScoreCard(data.before, 'Before · original RoboTwin instructions', false) +
      robotwinScoreCard(data.after, 'After · revised composite', true);
    document.querySelector('#robotwin-alignment-note').textContent = data.after.agentUnknownBenchFalse
      ? `Original agent–benchmark disagreements total ${data.before.agentSuccessBenchFalse}, giving IAS ${pct(data.before.instinctAlignment)}%. The revised composite has ${data.after.agentUnknownBenchFalse} failed reruns with unpublished agent completion judgments. Its IAS is between ${pct(data.after.instinctAlignmentBounds.min)}% and ${pct(data.after.instinctAlignmentBounds.max)}%; these records remain unclassified in the table.`
      : `Agent–benchmark disagreements fall from ${data.before.agentSuccessBenchFalse} to ${data.after.agentSuccessBenchFalse}, raising IAS from ${pct(data.before.instinctAlignment)}% to ${pct(data.after.instinctAlignment)}%.`;
    document.querySelector('#robotwin-instruction-rows').innerHTML = data.selectedExamples.map(item => `<tr data-episode="${esc(item.episodeKey)}"><th scope="row" class="task-ref"><span>Task ${String(item.taskId).padStart(2,'0')}</span><span>EPISODE ${String(item.episodeNumber).padStart(2,'0')}</span></th><td class="instruction-original">${esc(item.before.instruction)}</td><td class="instruction-improved">${highlightInstructionChanges(item.before.instruction,item.after.instruction,robotwinInstructionHighlights[item.episodeKey])}</td><td>${benchOutcome(item.before)} → <strong>${benchOutcome(item.after)}</strong></td></tr>`).join('');
    document.querySelector('#robotwin-cases').innerHTML = data.selectedExamples.map(item => {
      if (item.before.seed !== item.after.seed) throw new Error(`RoboTwin example scene mismatch: ${item.episodeKey}`);
      return robotwinCaseMarkup(item);
    }).join('');
    document.querySelector('#robotwin-failure-cases').innerHTML = Object.entries(robotwinFailureDetails).map(([episodeKey,detail]) => {
      const item = data.cases.find(record => record.episodeKey === episodeKey);
      if (!item || item.benchSuccess !== false || item.phase !== 'revision') throw new Error(`Expected a failed RoboTwin revision: ${episodeKey}`);
      const metadata = `seed ${item.seed} · ${item.steps} actions · ${item.toolCalls} tool calls · ${Math.round(item.wallSeconds)} s wall time`;
      return `<section class="failure-case robotwin-case" data-episode="${esc(item.episodeKey)}" id="robotwin-case-${esc(item.episodeKey)}"><div class="failure-description"><p class="eyebrow">${esc(robotwinEpisodeLabel(item))}</p><h3>${esc(detail.title)}</h3>${failureTaskRate(item.task.before,item.task.after)}<p>${esc(detail.detail)}</p><p class="small"><a href="${esc(item.galleryUrl)}">View episode in gallery ↗</a></p></div>${failureClipMarkup(item,'Revision',item.instruction,metadata,'Task instruction')}</section>`;
    }).join('');
  }
  window.galleryHosting.then(async config => {
    hosting = config;
    if (redirectLegacyHash()) return;
    addEventListener('hashchange', redirectLegacyHash);
    document.querySelectorAll('[data-gallery-path]').forEach(link => {
      link.href = new URL(link.dataset.galleryPath, hosting.galleryUrl).href;
    });
    const [data,media,review,robotwin] = await Promise.all(['data/libero-alignment.json','data/libero-blog-media.json','data/libero-human-review.json','data/robotwin-alignment-summary.json'].map(async path => {
      const response = await fetch(url(path), {cache:'no-cache'});
      if (!response.ok) throw new Error(`Cannot load ${path}: ${response.status}`);
      return response.json();
    }));
    if (!media.complete) throw new Error('Media export is incomplete');
    if (review.reviewCoverageStatus !== 'complete' || !review.unchangedDisagreementsConfirmed) throw new Error('Human review coverage is not confirmed');
    reviewCorrections = new Map(review.corrections.map(item => [`${item.stage}:${item.episodeKey}`,item]));
    renderComparison(review);
    renderInstructions(data);
    renderMedia(media,data);
    renderRobotwin(robotwin);
    bindVideoControls();
    document.documentElement.dataset.blogReady = 'true';
  }).catch(error => {
    document.querySelector('#load-error').hidden = false;
    document.documentElement.dataset.blogReady = 'error';
    console.error(error);
  });
})();
