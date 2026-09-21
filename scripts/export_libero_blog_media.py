#!/usr/bin/env python3
"""Export audited LIBERO instruction examples without copying raw recordings.

Requires the three named runs under --source-root, the existing gallery baseline
export, Python 3.10+, ffmpeg and ffprobe. Source runs are read-only. The output
contains only allowlisted metadata, hashes and encoded RGB videos, never private
paths, model messages, credentials or raw environment dumps.

    python scripts/export_libero_blog_media.py --source-root /path/to/eval_runs

--metadata-only publishes a marked-incomplete manifest for page development.
Every normal run verifies all media before marking the manifest complete.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from export_gallery import ENCODING, encode, is_faststart, probe, read_json, sha256, write_json


RUNS = {
    'baseline': 'astra_libero_v5_calibrated_parallel10_r4',
    'r1': 'astra_libero_v5_instruction_refined_parallel8_r1',
    'r2': 'astra_libero_v5_instruction_minimal_parallel4_r2',
}
LABELS = {'baseline': 'Original instructions', 'r1': 'First instruction revision',
          'r2': 'Minimal instruction revision'}
PAIRS = [
    ('book-compartment', 'Which compartment is “back”?', 'libero_10', 5, 'r2', 'failure', 'success',
     'The latest revision identifies the back compartment between the two large side compartments. The earlier “narrow back compartment” revision remained at 0/10.'),
    ('alphabet-soup', 'Identify the intended can', 'libero_object', 0, 'r1', 'failure', 'success',
     'Color words distinguish the blue-and-yellow alphabet soup can from the other cans.'),
    ('middle-drawer', 'How far is “open”?', 'libero_goal', 0, 'r1', 'failure', 'success',
     'Adding “fully” makes the intended amount of drawer opening more explicit.'),
    ('wine-rack', 'Specify the rack and bottle orientation', 'libero_goal', 9, 'r1', 'failure', 'success',
     'The revision names the upper rack and places the bottle base against its lower retaining rail.'),
    ('mug-and-pudding', 'Make both placements more specific', 'libero_10', 6, 'r1', 'failure', 'success',
     'The mug goes in the center of the plate; the pudding goes immediately to its right.'),
    ('plate-near-stove', 'A closer plate placement', 'libero_goal', 5, 'r2', 'failure', 'success',
     'The latest instruction adds “close to its front edge.” Only 2/10 passed. The intervening 35 cm revision used the wrong stove reference point and remained at 0/10.'),
    ('spatial-regression', 'Clearer wording can still regress', 'libero_spatial', 4, 'r1', 'success', 'failure',
     'Adding “in the center” did not consistently improve this task: 5/10 became 4/10, with both improvements and regressions across paired initial states.'),
]
FAILURES = [
    ('plate-wrong-object', 'Mistaking the cabinet for the stove', 'r2', 'libero_goal', 5, 5, 'object-identification',
     'The plate is pushed beside the wooden cabinet on the left; the actual single-burner stove is on the right. The agent declared visual completion at 259 steps, but the native predicate failed.'),
    ('plate-control-budget', 'The plate remains short of the goal', 'r2', 'libero_goal', 5, 7, 'execution-budget',
     'The agent used all 500 control steps and acknowledged the remaining gap. Offline replay places the plate center 1.82 cm beyond the goal’s front boundary.'),
    ('bottom-drawer-sequence', 'Place the bowl, then close the drawer', 'baseline', 'libero_10', 3, 0, 'multi-step-manipulation',
     'A baseline failure on a two-part task. This task scored 0/10 and was not included in either instruction-revision batch.'),
    ('microwave-sequence', 'Place the mug, then close the microwave', 'baseline', 'libero_10', 9, 0, 'multi-step-manipulation',
     'A baseline failure on placement followed by door closure. This task scored 0/10 and was not included in either instruction-revision batch.'),
]
PREDICATE_URL = 'https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/predicates/base_predicates.py'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_runs(source_root):
    runs={}
    for stage, name in RUNS.items():
        root=(source_root/name).resolve(); manifest=read_json(root/'manifest.json')
        assert canonical_hash({k:v for k,v in manifest.items() if k!='manifest_sha256'})==manifest['manifest_sha256']
        assert manifest['config']['model']=='gpt-6-astra' and manifest['config']['reasoning_effort']=='high'
        rows={}
        for spec in manifest['episodes']:
            key=spec['episode_key']; attempts=sorted((root/'episodes'/key).glob('attempt_[0-9][0-9][0-9]'))
            assert attempts, key
            attempt=attempts[-1]; result=read_json(attempt/'result.json')
            assert result['episode_key']==key and result['manifest_sha256']==manifest['manifest_sha256']
            assert result['status'] in {'success','failure'}, (stage,key,result['status'])
            assert result['success']==result['environment']['success']==(result['status']=='success')
            assert not result['audit'].get('isolation_violation')
            for previous in attempts[:-1]:
                assert read_json(previous/'result.json')['status'] in {'error','interrupted'}, 'Policy outcome was retried'
            rows[key]={'spec':spec,'result':result,'attempt':attempt}
        runs[stage]={'root':root,'manifest':manifest,'episodes':rows}
    assert [len(runs[s]['episodes']) for s in RUNS]==[400,90,20]
    base=runs['baseline']['manifest']
    for stage in ('r1','r2'):
        m=runs[stage]['manifest']
        assert m['instruction_rerun']['baseline_manifest_sha256']==base['manifest_sha256']
        assert m['prompt_template']==base['prompt_template']
    return runs


def task_stats(run, suite, task_id):
    rows=[r for r in run['episodes'].values() if (r['spec']['suite'],r['spec']['task_id'])==(suite,task_id)]
    assert len(rows)==10 and sorted(r['spec']['rollout_id'] for r in rows)==list(range(10))
    successes=sum(r['result']['success'] for r in rows)
    return {'successes':successes,'episodes':10,'successRate':successes/10}


def public_stage(stage, run):
    m=run['manifest']; c=m['config']; n=len(run['episodes']); successes=sum(r['result']['success'] for r in run['episodes'].values())
    return {'id':stage,'label':LABELS[stage],'run':RUNS[stage],'manifestSha256':m['manifest_sha256'],
            'episodes':n,'successes':successes,'model':c['model'],'reasoningEffort':c['reasoning_effort'],
            'workers':c['workers'],'gpuIds':c['gpu_ids'],'controlSteps':500,'initStateIds':c['init_state_ids'],
            'liberoCommit':m['provenance']['libero_commit']}


def build_plan(runs, output):
    gallery_report=read_json(output/'data/export-report.json')
    baseline_run=next(r for r in gallery_report['runs'] if r['benchmark']=='libero')
    assert baseline_run['manifestSha256']==runs['baseline']['manifest']['manifest_sha256']
    baseline_selections={r['episode']:r for r in baseline_run['attemptSelection']}
    old_media={r['episode']:r for r in gallery_report['media'] if r['benchmark']=='libero'}
    clips={};jobs={};pairs=[];failures=[]

    def clip(stage, key):
        clip_id=f'{stage}:{key}'
        if clip_id in clips:return clip_id
        row=runs[stage]['episodes'][key];spec=row['spec'];result=row['result'];attempt=row['attempt']
        video_info=result['environment']['video'];source=Path(video_info['path']).resolve()
        assert source.is_file() and source.is_relative_to(attempt.resolve())
        assert video_info['closed'] and not video_info.get('error')
        assert video_info['frames']==result['steps']+11 and video_info['fps']==20
        assert sha256(Path(spec['bddl_file']))==spec['bddl_sha256']
        assert sha256(Path(spec['init_file']))==spec['init_sha256']
        result_sha=sha256(attempt/'result.json');source_sha=sha256(source)
        root='media/libero' if stage=='baseline' else f'media/blog/libero/{stage}'
        finish_file=attempt/'finish_assessment.json'
        finish=read_json(finish_file).get('outcome') if finish_file.exists() else None
        assert finish in {None,'visually_complete','unable_to_continue'}
        record={'id':clip_id,'stage':stage,'stageLabel':LABELS[stage],'episodeId':key,'episodeKey':key,
                'suite':spec['suite'],'taskId':spec['task_id'],'taskName':spec['task_name'],
                'rolloutIndex':spec['rollout_id'],'seed':spec['seed'],'initStateId':spec['init_state_id'],
                'instruction':spec['language'],'originalInstruction':spec.get('original_language',spec['language']),
                'status':result['status'],'nativeSuccess':result['success'],'agentAssessment':finish or 'unknown',
                'stopReason':result['reason'],'steps':result['steps'],'maxSteps':spec['max_steps'],
                'video':f'{root}/{key}.mp4','poster':f'{root}/{key}.jpg',
                'width':video_info['width'],'height':video_info['height'],'frames':video_info['frames'],
                'fps':20,'durationSeconds':video_info['frames']/20,'reusedBaselineMedia':stage=='baseline',
                'task':task_stats(runs[stage],spec['suite'],spec['task_id']),
                'source':{'run':RUNS[stage],'manifestSha256':runs[stage]['manifest']['manifest_sha256'],
                          'resultSha256':result_sha,'videoSha256':source_sha,'selectedAttempt':attempt.name,
                          'bddlSha256':spec['bddl_sha256'],'initFileSha256':spec['init_sha256']}}
        if stage=='baseline':
            prior=old_media[key];selection=baseline_selections[key]
            assert selection['resultSha256']==result_sha and selection['selectedAttempt']==attempt.name
            assert prior['sourceSha256']==source_sha
            assert prior['video']==record['video'] and prior['poster']==record['poster']
            assert sha256(output/record['video'])==prior['videoSha256']
            assert sha256(output/record['poster'])==prior['posterSha256']
            record['media']={k:prior[k] for k in ('videoSha256','videoBytes','posterSha256','posterBytes','posterFrame','codec','pixelFormat','fastStart','verified')}
        else:
            jobs[clip_id]={'source':source,'episode':{**record,'id':key},'benchmark':'libero',
                          'expectedFps':'20','selection':{'sourceVideoSha256':source_sha},'outputRoot':output,
                          'encoding':ENCODING}
        clips[clip_id]=record
        return clip_id

    for case_id,title,suite,task_id,after_stage,before_status,after_status,note in PAIRS:
        candidates=[]
        matrix={'S→S':0,'S→F':0,'F→S':0,'F→F':0}
        for index in range(10):
            key=f'{suite}_t{task_id:02d}_r{index:02d}'
            before=runs['baseline']['episodes'][key];after=runs[after_stage]['episodes'][key]
            for field in ('seed','init_state_id','bddl_sha256','init_sha256','max_steps','max_tool_calls','image_size','task_name'):
                assert before['spec'][field]==after['spec'][field],(key,field)
            assert before['spec']['language']==after['spec']['original_language']
            statuses=(before['result']['status'],after['result']['status'])
            matrix['→'.join('S' if s=='success' else 'F' for s in statuses)]+=1
            if statuses==(before_status,after_status):candidates.append(index)
        assert candidates,case_id
        index=min(candidates);key=f'{suite}_t{task_id:02d}_r{index:02d}'
        pairs.append({'id':case_id,'title':title,'suite':suite,'taskId':task_id,'rolloutIndex':index,
                      'seed':runs['baseline']['episodes'][key]['spec']['seed'],
                      'initStateId':runs['baseline']['episodes'][key]['spec']['init_state_id'],
                      'before':clip('baseline',key),'after':clip(after_stage,key),
                      'beforeTask':task_stats(runs['baseline'],suite,task_id),
                      'afterTask':task_stats(runs[after_stage],suite,task_id),'pairedMatrix':matrix,
                      'selectionRule':f'Lowest rollout index with {before_status} → {after_status} in these two frozen runs.',
                      'note':note,'sourceLinks':[{'label':'Native predicate implementation','url':PREDICATE_URL},
                           {'label':'Task BDDL','url':f'https://github.com/Lifelong-Robot-Learning/LIBERO/blob/{runs[after_stage]["manifest"]["provenance"]["libero_commit"]}/libero/libero/bddl_files/{suite}/{runs[after_stage]["episodes"][key]["spec"]["task_name"]}.bddl'}]})
    for case_id,title,stage,suite,task_id,index,category,note in FAILURES:
        key=f'{suite}_t{task_id:02d}_r{index:02d}';clip_id=clip(stage,key)
        assert clips[clip_id]['status']=='failure'
        failures.append({'id':case_id,'title':title,'clip':clip_id,'category':category,'note':note,
                         'task':task_stats(runs[stage],suite,task_id),
                         'selectionRule':'Named diagnostic episode chosen after review; not a random sample.'})
    document={'schemaVersion':1,'generatedAt':datetime.now(timezone.utc).isoformat(),'complete':False,
              'selectionPolicy':'Purposefully chosen explanatory cases, not a random sample or an estimate from the displayed clips. Paired examples use the lowest rollout index showing the stated transition, without rerunning a policy failure. Every task rate includes all ten frozen initial states for its named stage. Revisions were developed after source/demo inspection; these are diagnostic reruns, not held-out causal estimates.',
              'videoNote':'Original full episode frames at 20 fps, including the initial frame and ten warmup steps. Agent view is left and wrist view is right. Inference waiting time is omitted. Success is the native environment predicate; automatic success termination does not imply an independent agent completion judgment.',
              'encoding':ENCODING,'stages':{s:public_stage(s,r) for s,r in runs.items()},
              'pairs':pairs,'failureCases':failures,'clips':clips,
              'validation':{'complete':False,'privatePathsIncluded':False,'rawModelMessagesIncluded':False}}
    return document,jobs


def prior_encoding(record):
    if not record or not record.get('media'):return None
    return {'episode':record['episodeId'],'benchmark':'libero',
            'sourceSha256':record['source']['videoSha256'],
            'video':record['video'],'poster':record['poster'],
            'width':record['width'],'height':record['height'],'frames':record['frames'],
            'fps':str(record['fps']),'durationSeconds':record['durationSeconds'],**record['media']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--jobs',type=int,choices=range(1,5),default=2)
    parser.add_argument('--metadata-only',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    assert not args.source_root.resolve().is_relative_to(output)
    runs=load_runs(args.source_root.resolve());document,jobs=build_plan(runs,output)
    target=output/'data/libero-blog-media.json'
    prior=read_json(target).get('clips',{}) if target.is_file() else {}
    if args.metadata_only:
        write_json(target,document)
        print(json.dumps({'complete':False,'pairs':len(document['pairs']),'failures':len(document['failureCases']),
                          'newVideos':len(jobs),'reusedVideos':len(document['clips'])-len(jobs)}))
        return
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures={pool.submit(encode,job,prior_encoding(prior.get(key))):key for key,job in jobs.items()}
        for future in as_completed(futures):
            key=futures[future];encoded=future.result()
            document['clips'][key]['media']={k:encoded[k] for k in ('videoSha256','videoBytes','posterSha256','posterBytes','posterFrame','codec','pixelFormat','fastStart','verified')}
            print(json.dumps({'encoded':key,'videoBytes':encoded['videoBytes']}),flush=True)
    for record in document['clips'].values():
        video=output/record['video'];info=probe(video)
        for field in ('width','height','frames'):assert info[field]==record[field],(record['id'],field)
        assert info['fps']==str(record['fps']) and abs(info['durationSeconds']-record['durationSeconds'])<.001
        assert info['codec']=='h264' and info['pixelFormat']=='yuv420p' and is_faststart(video)
        assert sha256(video)==record['media']['videoSha256']
        assert sha256(output/record['poster'])==record['media']['posterSha256']
    document['complete']=True
    document['validation'].update(complete=True,verifiedClips=len(document['clips']),newClips=len(jobs),
                                  reusedClips=len(document['clips'])-len(jobs),
                                  newMediaBytes=sum(r['media']['videoBytes']+r['media']['posterBytes'] for r in document['clips'].values() if not r['reusedBaselineMedia']))
    public=json.dumps(document,ensure_ascii=False)
    for private in ('/playpen/','/playpen-ssd/','/home/','auth.json','codex_events.jsonl','visual_checks'):
        assert private not in public,private
    write_json(target,document)
    print(json.dumps(document['validation'],indent=2))


if __name__=='__main__':main()
