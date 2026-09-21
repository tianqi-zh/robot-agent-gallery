(() => {
  'use strict';
  const siteRoot = new URL('./', document.currentScript.src);
  function redirectLegacyHash() {
    const old = new URLSearchParams(location.hash.slice(1));
    if (!['benchmark', 'task', 'episode', 'view'].some(key => old.has(key))) return false;
    const names = {libero:'libero',robotwin:'robotwin',robotwin_nvidia10:'robotwin',robocasa:'robocasa',robodojo:'robodojo'};
    const benchmark = old.get('benchmark') || (old.get('task') || old.get('episode') || '').split('_')[0];
    const target = new URL(`gallery/${names[benchmark] ? names[benchmark] + '/' : ''}`, siteRoot);
    target.search = location.search;
    target.hash = location.hash;
    location.replace(target.href);
    return true;
  }
  if (redirectLegacyHash()) return;
  addEventListener('hashchange', redirectLegacyHash);
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct = value => (100 * value).toFixed(2);
  const url = path => new URL(path, siteRoot).href;
  const suiteNames = {libero_10:'LIBERO-10',libero_goal:'Goal',libero_object:'Object',libero_spatial:'Spatial'};
  const taskLabel = (suite,id) => `${suiteNames[suite]} t${String(id).padStart(2,'0')}`;
  const descriptions = {
    'book-compartment': 'The intended target is the rear of the two small central compartments, between the large side bins. The original phrase leaves that distinction implicit. The native check tests the book’s body origin against a target volume; it does not require release or a particular orientation. The earlier “narrow back compartment” revision also scored 0/10.',
    'alphabet-soup': 'In the eight original failures, the policy moved the tomato-sauce can instead of the alphabet-soup can. Adding the blue-and-yellow appearance gives the policy a visible cue for the benchmark’s asset identity.',
    'middle-drawer': 'The native open condition requires more than 14 cm of extension. The two original failures stopped at roughly 12.8 and 13.7 cm: visibly open, but below that threshold. “Fully” gives a stronger observable stopping cue without exposing the numeric joint limit.',
    'wine-rack': 'The original failures placed the bottle on the upper tier, outside the target region. The added phrase identifies where its base should sit. The native check combines rack contact with a body-origin region; it does not directly enforce the orientation described by the revised instruction.',
    'mug-and-pudding': 'Two spatial requirements interact: the mug must be centered on the plate, and the pudding must lie inside a fixed tabletop region to its right; that region does not move with the plate. A broad reading of “to the right” can miss that region. The revision adds centering and proximity cues.',
    'plate-near-stove': '“In front” maps to a fixed 8 × 8 cm tabletop region. The final phrase adds proximity to the stove’s front edge, while leaving manipulation to the policy. Only two of ten episodes succeed: this remains a difficult pushing task, even with the clarified goal.',
    'spatial-regression': 'This is a success → failure pair, included deliberately. The native on-plate check combines contact, height, and a center-distance threshold below 3 cm. Explicitly asking for the center did not improve this task in these ten runs.'
  };
  const failureDetails = {
    'plate-wrong-object':'This is an object-grounding error. The task names the stove, but the policy acts on its mistaken identification of another fixture and then reports completion. More specific spatial language cannot repair a wrong referent on its own.',
    'plate-control-budget':'Small errors accumulate during pushing: the gripper can ride onto the rim or lose contact, and nearby clutter restricts the approach. Repeated repositioning consumes the control budget before the plate reaches the target.',
    'bottom-drawer-sequence':'The final closure remains incomplete. Placing an object inside a drawer is only part of the goal; the policy must then move to an effective pushing contact and verify the articulated state within the remaining budget.',
    'microwave-sequence':'The final door closure remains incomplete. Placement and door motion require different contacts and viewpoints; succeeding at an earlier substep does not ensure that the full conjunction of native goals is satisfied.'
  };
  function scoreCard(stats, after) {
    const row = (key, label, detail) => `<tr class="${key}"><th scope="row">${label}<small>${detail}</small></th><td>${stats.matrix[key].benchSuccess}</td><td class="${key === 'success' ? 'mismatch' : ''}">${stats.matrix[key].benchFailure}</td></tr>`;
    return `<div class="score-card ${after ? 'after' : 'before'}"><div class="score-top"><h3>${after ? 'After · revised composite' : 'Before · original instructions'}</h3><span>n = ${stats.n}</span></div><p class="score-value">${pct(stats.ias)}<span>%</span></p><p class="score-label">Instinct-alignment score</p><p class="score-equation">1 − ${stats.mismatchCount} / ${stats.n} = ${pct(stats.ias)}%</p><table class="cross-table"><caption>Agent assessment × native benchmark result</caption><thead><tr><th scope="col">Agent assessment</th><th scope="col">Bench success</th><th scope="col">Bench failure</th></tr></thead><tbody>${row('success','Success','Explicit visually complete')}${row('failure','Failure','Explicit unable to continue')}${row('unknown','Unknown','No explicit finish assessment')}</tbody></table><p class="native-score">Native success: <strong>${stats.benchSuccess}/${stats.n} · ${pct(stats.benchSuccess / stats.n)}%</strong></p><p class="coverage">Explicit assessment: ${stats.n - stats.agentCounts.unknown}/${stats.n} episodes (${pct(stats.selfAssessmentCoverage)}%).<br>Unknown assessments among native failures: ${stats.matrix.unknown.benchFailure}.</p></div>`;
  }
  function renderComparison(data, scope) {
    const selected = scope === 'revised' ? data.rerunSubset : data;
    document.querySelector('#comparison').innerHTML = scoreCard(selected.before, false) + scoreCard(selected.after, true);
    document.querySelector('#scope-note').textContent = scope === 'revised' ? 'Only the nine revised tasks: 90 original episodes versus 70 first-revision + 20 final-revision episodes. This subset was selected after observing baseline disagreements.' : 'All 40 tasks: 400 original episodes versus a composite preserving 310 original episodes and replacing all 90 episodes from the nine revised tasks.';
    document.querySelectorAll('[data-scope]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.scope === scope)));
  }
  function renderInstructions(data) {
    const order = ['libero_goal','libero_object','libero_10','libero_spatial'];
    document.querySelector('#instruction-rows').innerHTML = data.tasks.filter(task => task.changed).sort((a,b) => order.indexOf(a.suite) - order.indexOf(b.suite) || a.taskId - b.taskId).map(task => {
      const delta = task.after.benchSuccess - task.before.benchSuccess;
      return `<tr data-task="${esc(task.id)}"><th scope="row" class="task-ref"><span>${esc(taskLabel(task.suite,task.taskId))}</span></th><td>${esc(task.instructionBefore)}</td><td>${esc(task.instructionAfter)}<span class="revision-label">${task.sourceStage === 'round2' ? 'Final minimal revision' : 'First revision'}</span></td><td>${task.before.benchSuccess}/10 → <strong>${task.after.benchSuccess}/10</strong><span class="delta ${delta < 0 ? 'negative' : ''}">${delta > 0 ? '+' : ''}${delta} successes</span></td></tr>`;
    }).join('');
  }
  function clipMarkup(clip,label) {
    const assessment = {visually_complete:'Agent: visually complete',unable_to_continue:'Agent: unable to continue',unknown:'Agent assessment: unknown',null:'Agent assessment: unknown'}[clip.agentAssessment] || 'Agent assessment: unknown';
    return `<figure class="clip"><div class="clip-header"><span>${esc(label)}</span><span class="status ${clip.status}">Bench ${esc(clip.status)}</span></div><video controls playsinline preload="none" poster="${esc(url(clip.poster))}" src="${esc(url(clip.video))}" aria-label="${esc(label + ': ' + taskLabel(clip.suite,clip.taskId) + ', rollout ' + clip.rolloutIndex)}"></video><figcaption><p class="clip-instruction">“${esc(clip.instruction)}”</p><p class="clip-meta">${esc(clip.stageLabel)} · seed ${clip.seed} · init ${clip.initStateId} · ${clip.steps} steps<br>${esc(assessment)} · <a href="${esc(url(clip.video))}" download>Download MP4 ↓</a></p></figcaption></figure>`;
  }
  function renderMedia(media) {
    document.querySelector('#paired-cases').innerHTML = media.pairs.map((pair,index) => {
      const before = media.clips[pair.before], after = media.clips[pair.after];
      const sources = (pair.sourceLinks || []).filter(link => link.label === 'Task BDDL');
      return `<section class="case" id="case-${esc(pair.id)}"><div class="case-head"><div><p class="eyebrow">CASE ${String(index+1).padStart(2,'0')} / ${esc(taskLabel(pair.suite,pair.taskId))}</p><h3>${esc(pair.title)}</h3></div><div class="task-rate ${pair.afterTask.successes < pair.beforeTask.successes ? 'negative' : ''}"><span>Task native successes</span><strong>${pair.beforeTask.successes}/10 → ${pair.afterTask.successes}/10</strong></div></div><div class="paired-videos">${clipMarkup(before,'Before')}${clipMarkup(after,'After')}</div><div class="case-foot"><p class="case-detail">${esc(descriptions[pair.id] || pair.note)}</p><div class="case-actions"><button class="play-pair" type="button">Play both from start</button><span class="case-source">Same initial state ${pair.initStateId} · ${sources.map(link => `<a href="${esc(link.url)}">Native task definition ↗</a>`).join(' · ')}</span><span class="play-status" role="status"></span></div></div></section>`;
    }).join('');
    document.querySelector('#failure-cases').innerHTML = media.failureCases.map(item => {
      const clip = media.clips[item.clip];
      return `<section class="failure-case" id="failure-${esc(item.id)}"><div class="failure-description"><p class="eyebrow">${esc(taskLabel(clip.suite,clip.taskId))} / ${item.task.successes}/${item.task.episodes} TASK SUCCESSES</p><h3>${esc(item.title)}</h3><p>${esc(item.note)}</p></div>${clipMarkup(clip,'Failure example')}<div class="failure-description"><p>${esc(failureDetails[item.id] || '')}</p></div></section>`;
    }).join('');
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
    document.querySelectorAll('video').forEach(video => video.addEventListener('error', () => {
      const meta = video.closest('figure').querySelector('.clip-meta');
      if (!meta.querySelector('.media-error')) meta.insertAdjacentHTML('beforeend','<br><span class="media-error" role="alert">Playback unavailable. Try the MP4 download link.</span>');
    }));
  }
  Promise.all(['data/libero-alignment.json','data/libero-blog-media.json'].map(async path => {
    const response = await fetch(url(path));
    if (!response.ok) throw new Error(`Cannot load ${path}: ${response.status}`);
    return response.json();
  })).then(([data,media]) => {
    if (!media.complete) throw new Error('Media export is incomplete');
    renderComparison(data,'all');
    renderInstructions(data);
    renderMedia(media);
    document.querySelectorAll('[data-scope]').forEach(button => button.addEventListener('click', () => renderComparison(data,button.dataset.scope)));
    document.documentElement.dataset.blogReady = 'true';
  }).catch(error => {
    document.querySelector('#load-error').hidden = false;
    document.documentElement.dataset.blogReady = 'error';
    console.error(error);
  });
})();
