#!/usr/bin/env python3
"""Validate published LIBERO analysis, paired selections and media (no raw runs).

Default checks use the standard library and hash the 18 referenced clips/posters,
fetching missing assets from Hugging Face into .gallery-cache/blog-media/.
--media-root uses a local gallery export without network access.
--probe additionally decodes every video with ffprobe. Public hashes bind the
published assets; this does not replace the separate audit of private raw runs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from fractions import Fraction
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from blog_validation import MediaResolver, ValidationError, local_asset, public_metadata, read_json, require, sha256

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('libero_spatial', 'libero_goal', 'libero_object', 'libero_10')
R1_TASKS = {('libero_spatial', 4), ('libero_goal', 0), ('libero_goal', 5), ('libero_goal', 9),
            ('libero_object', 0), ('libero_object', 4), ('libero_10', 5), ('libero_10', 6), ('libero_10', 7)}
R2_TASKS = {('libero_goal', 5), ('libero_10', 5)}
RUNS = {
    'baseline': ('astra_libero_v5_calibrated_parallel10_r4', 'df08694520ff7ea3e9bfee061a29223e46c4db76bc54a07e637cbfcbe93f42f8', 400),
    'round1': ('astra_libero_v5_instruction_refined_parallel8_r1', '1fe4a3d8fadb450d032d237c5e77f0da1e5275f7452de9988b8fa5c9f28ce269', 90),
    'round2': ('astra_libero_v5_instruction_minimal_parallel4_r2', '08e43c9fb96ffebf033f0e93fd5371a8ef36b41566eadfa89db80b4958381847', 20),
}
MEDIA_STAGES = {'baseline': ('baseline', 'before'), 'r1': ('round1', 'round1'), 'r2': ('round2', 'after')}
PREFIXES = ('before', 'round1', 'after')
SUFFIXES = ('Stage', 'RunName', 'Attempt', 'BenchSuccess', 'AgentLabel', 'AgentOutcome', 'Instruction',
            'Steps', 'HostReason', 'ResultSha256', 'FinishSha256', 'TrajectorySha256')
CSV_FIELDS = {'episodeKey', 'suite', 'taskId', 'seed', 'initStateId'} | {p+s for p in PREFIXES for s in SUFFIXES}


def check_public(value, location='data'):
    public_metadata(value, location)
    if isinstance(value, dict):
        for key, child in value.items():
            require(re.sub('[^a-z]', '', key.lower()) not in {
                'agentmessages', 'visualchecks', 'rawreasoning', 'rawmodelmessages', 'finishreason',
                'privatekey', 'clientsecret', 'credentialspath', 'credentialfile'}, f'Private field at {location}')
            check_public(child, f'{location}.{key}')
    elif isinstance(value, list):
        for i, child in enumerate(value):
            check_public(child, f'{location}[{i}]')
    elif isinstance(value, str):
        require(not re.search(r'''(?:^|[\s"'=])/(?:home|playpen(?:-ssd)?|tmp|Users|root|mnt|private)/''', value),
                f'Private absolute path at {location}')
        require(not re.search(r'(?i)\bBearer\s+[A-Za-z0-9._-]{16,}|-----BEGIN .*PRIVATE KEY-----', value),
                f'Possible credential at {location}')


def exact(actual, expected, label):
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual)==set(expected), f'{label}: unexpected fields')
        for key, value in expected.items():
            exact(actual[key], value, f'{label}.{key}')
    elif isinstance(expected, float):
        require(type(actual) in (int, float) and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12), f'{label}: incorrect rate')
    else:
        require(type(actual) is type(expected) and actual==expected, f'{label}: mismatch')


def digest_string(value, label, optional=False):
    require(optional and value=='' or isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value),
            f'{label}: invalid SHA-256')


def boolean(value, label):
    require(value in ('True', 'False'), f'{label}: expected True or False')
    return value=='True'


def statistics(rows, prefix):
    n=len(rows)
    require(n>0, 'Empty statistics subset')
    matrix={a:{'benchSuccess':0, 'benchFailure':0} for a in ('success','failure','unknown')}
    for row in rows:
        matrix[row[prefix+'AgentLabel']]['benchSuccess' if boolean(row[prefix+'BenchSuccess'],prefix) else 'benchFailure']+=1
    successes=sum(v['benchSuccess'] for v in matrix.values())
    agents={k:sum(v.values()) for k,v in matrix.items()}
    mismatch=matrix['success']['benchFailure']
    return {'n':n, 'benchSuccess':successes, 'benchFailure':n-successes, 'benchSuccessRate':successes/n,
            'mismatchCount':mismatch, 'ias':1-mismatch/n, 'matrix':matrix, 'agentCounts':agents,
            'selfAssessmentCoverage':(agents['success']+agents['failure'])/n,
            'sourceStageCounts':dict(Counter(row[prefix+'Stage'] for row in rows))}


def transitions(rows, before, after):
    result={k:0 for k in ('successToSuccess','successToFailure','failureToSuccess','failureToFailure')}
    for row in rows:
        a='success' if boolean(row[before+'BenchSuccess'],before) else 'failure'
        b='Success' if boolean(row[after+'BenchSuccess'],after) else 'Failure'
        result[a+'To'+b]+=1
    return {**result,'n':len(rows),'netAdditionalSuccesses':result['failureToSuccess']-result['successToFailure']}


def validate_alignment(alignment, rows):
    require(set(alignment)==set('schemaVersion generatedAt before round1 after rerunSubset finalRoundSubset tasks provenance method transitions'.split()),
            'Unexpected alignment fields')
    require(alignment['schemaVersion']==1, 'Unsupported alignment schema')
    require(len(rows)==400 and len({r['episodeKey'] for r in rows})==400, 'Expected 400 unique episode slots')
    tasks={t['id']:t for t in alignment['tasks']}
    expected_tasks={f'{s}_t{i:02d}' for s in SUITES for i in range(10)}
    require(len(alignment['tasks'])==40 and set(tasks)==expected_tasks, 'Expected exact 40-task catalog')
    by_task={task:[] for task in tasks}
    for row in rows:
        require(set(row)==CSV_FIELDS, 'Unexpected episode CSV columns')
        key=row['episodeKey']
        match=re.fullmatch(r'(libero_spatial|libero_goal|libero_object|libero_10)_t(\d{2})_r(\d{2})',key)
        require(match is not None, 'Invalid episode key')
        suite, tid, rid=match.group(1),int(match.group(2)),int(match.group(3))
        require(tid in range(10) and rid in range(10), f'{key}: task/rollout outside catalog')
        require(row['suite']==suite and row['taskId']==str(tid), f'{key}: task identity mismatch')
        require(row['seed']==row['initStateId']==str(rid), f'{key}: seed/init pairing mismatch')
        task_id=f'{suite}_t{tid:02d}'; by_task[task_id].append(row)
        pair=(suite,tid)
        stages={'before':'baseline','round1':'round1' if pair in R1_TASKS else 'baseline',
                'after':'round2' if pair in R2_TASKS else 'round1' if pair in R1_TASKS else 'baseline'}
        for prefix in PREFIXES:
            require(row[prefix+'Stage']==stages[prefix], f'{key}: entire-task stage selection violated')
            require(row[prefix+'RunName']==RUNS[stages[prefix]][0], f'{key}: source run mismatch')
            require(re.fullmatch(r'attempt_\d{3}',row[prefix+'Attempt']) is not None, f'{key}: invalid attempt')
            boolean(row[prefix+'BenchSuccess'],key)
            outcome=row[prefix+'AgentOutcome'];label=row[prefix+'AgentLabel']
            require(outcome in ('','visually_complete','unable_to_continue'), f'{key}: invalid explicit outcome')
            require(label=={'':'unknown','visually_complete':'success','unable_to_continue':'failure'}[outcome],
                    f'{key}: missing explicit self-assessment must remain unknown')
            require(bool(row[prefix+'FinishSha256'])==bool(outcome), f'{key}: finish evidence mismatch')
            require(row[prefix+'Instruction'].strip(), f'{key}: missing instruction')
            require(row[prefix+'Steps'].isdigit() and 0<=int(row[prefix+'Steps'])<=500, f'{key}: invalid control steps')
            require(row[prefix+'HostReason'] in ('libero_success','agent_finished','step_budget'), f'{key}: invalid stop reason')
            require((row[prefix+'HostReason']=='libero_success')==boolean(row[prefix+'BenchSuccess'],key),
                    f'{key}: native stop reason disagrees with score')
            for suffix in ('ResultSha256','TrajectorySha256','FinishSha256'):
                digest_string(row[prefix+suffix],f'{key}.{prefix}{suffix}',optional=suffix=='FinishSha256')
        for a,b in (('before','round1'),('round1','after')):
            if stages[a]==stages[b]:
                require(all(row[a+s]==row[b+s] for s in SUFFIXES), f'{key}: unchanged stage was rewritten')
    for key, group in by_task.items():
        require(len(group)==10, f'{key}: expected all ten initial states')
        task=tasks[key];suite=group[0]['suite'];tid=int(group[0]['taskId'])
        require(set(task)==set('id suite taskId taskName instructionBefore instructionRound1 instructionAfter sourceStage changed before round1 after transitions episodeKeys'.split()),
                f'{key}: unexpected task fields')
        require(task['suite']==suite and task['taskId']==tid, f'{key}: task identity mismatch')
        require(task['episodeKeys']==sorted(r['episodeKey'] for r in group), f'{key}: episode list mismatch')
        require(task['sourceStage']==group[0]['afterStage'], f'{key}: final task stage mismatch')
        require(task['changed'] is ((suite,tid) in R1_TASKS), f'{key}: changed task marker mismatch')
        for prefix, instruction_field in [('before','instructionBefore'),('round1','instructionRound1'),('after','instructionAfter')]:
            exact(task[prefix],statistics(group,prefix),f'{key}.{prefix}')
            require({r[prefix+'Instruction'] for r in group}=={task[instruction_field]}, f'{key}: instructions vary within a task')
        exact(task['transitions'],transitions(group,'before','after'),f'{key}.transitions')
    for prefix in PREFIXES:
        exact(alignment[prefix],statistics(rows,prefix),prefix)
    for label, selection in [('rerunSubset',R1_TASKS),('finalRoundSubset',R2_TASKS)]:
        group=[r for r in rows if (r['suite'],int(r['taskId'])) in selection]
        require(alignment[label]['n']==len(group),f'{label}: subset size mismatch')
        for prefix in PREFIXES:
            exact(alignment[label][prefix],statistics(group,prefix),f'{label}.{prefix}')
    for key,a,b in [('beforeToRound1','before','round1'),('beforeToAfter','before','after'),('round1ToAfter','round1','after')]:
        exact(alignment['transitions'][key],transitions(rows,a,b),f'transitions.{key}')
    provenance={r['stage']:r for r in alignment['provenance']}
    require(len(alignment['provenance'])==3 and set(provenance)==set(RUNS),'Expected three source runs')
    for stage,(name,manifest,n) in RUNS.items():
        source=provenance[stage]
        require((source['runName'],source['manifestSha256'],source['episodeCount'])==(name,manifest,n),'Frozen source provenance mismatch')
        require(source['taskCount']==n//10,'Provenance task count mismatch')
        prefix={'baseline':'before','round1':'round1','round2':'after'}[stage]
        group=[r for r in rows if r[prefix+'Stage']==stage]
        exact(source['statistics'],statistics(group,prefix),f'provenance.{stage}')
        require(source['finalGatePassed'] is True,'Raw source completion audit did not pass')
        require(source['requestedModel']=='gpt-6-astra' and source['reasoningEffort']=='high','Model settings changed')
        for field in ('maxSteps','maxToolCalls','imageSize','liberoCommit','liberoTrackedDiffSha256','genericPromptTemplateSha256','nativeRuntimeCodeSha256'):
            exact(source[field],provenance['baseline'][field],f'provenance.{stage}.{field}')
        excluded=source['excludedInfrastructureAttempts']
        require(all(r['status'] in ('error','interrupted') for r in excluded),'A policy outcome was excluded')
        require(source['totalAttempts']==n+len(excluded),'Attempt count mismatch')
    require(alignment['method']['validation']['passed'] is True,'Source audit is not complete')
    require(alignment['method']['validation']['validPolicyAttemptsAudited']==510,'Expected 510 audited valid attempts')
    return by_task,provenance


def task_rate(group,prefix):
    s=statistics(group,prefix)
    return {'successes':s['benchSuccess'],'episodes':s['n'],'successRate':s['benchSuccessRate']}


def validate_probe(path,clip):
    command=['ffprobe','-v','error','-threads','1','-select_streams','v:0','-count_frames','-show_entries',
             'stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_read_frames,duration:format=duration','-of','json',str(path)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    require(result.returncode==0 and not result.stderr.strip(),f'{clip["id"]}: video decode failed')
    data=json.loads(result.stdout);require(len(data['streams'])==1,'Expected one video stream')
    stream=data['streams'][0]
    require(stream['codec_name']=='h264' and stream['pix_fmt']=='yuv420p','Unexpected codec/pixel format')
    for actual,field in [('width','width'),('height','height'),('nb_read_frames','frames')]:
        require(int(stream[actual])==clip[field],f'{clip["id"]}: {field} changed')
    require(Fraction(stream['avg_frame_rate'])==clip['fps'],'Video fps changed')
    require(abs(float(stream.get('duration',data['format']['duration']))-clip['durationSeconds'])<.001,'Video duration changed')


def validate_documents(root,alignment,rows,media,*,probe=False,media_root=None):
    resolver=MediaResolver(root,media_root=media_root)
    for label,value in [('alignment',alignment),('episodes',rows),('media',media)]:
        check_public(value,label)
    by_task,provenance=validate_alignment(alignment,rows)
    require(set(media)==set('schemaVersion generatedAt complete selectionPolicy videoNote encoding stages pairs failureCases clips validation'.split()),
            'Unexpected blog media fields')
    require(media['schemaVersion']==1 and media['complete'] is True,'Blog media export is incomplete')
    require(media['validation']['complete'] is True,'Blog media validation is incomplete')
    require(media['validation']['privatePathsIncluded'] is False and media['validation']['rawModelMessagesIncluded'] is False,'Private media export flagged')
    require(set(media['stages'])==set(MEDIA_STAGES),'Unexpected media stages')
    for alias,(stage,_) in MEDIA_STAGES.items():
        source=media['stages'][alias];p=provenance[stage]
        require(source['id']==alias and source['run']==p['runName'] and source['manifestSha256']==p['manifestSha256'],'Media source stage mismatch')
        for field,other in [('episodes','episodeCount'),('model','requestedModel'),('reasoningEffort','reasoningEffort'),('workers','workers'),('gpuIds','gpuIds'),('liberoCommit','liberoCommit')]:
            exact(source[field],p[other],f'media.stage.{alias}.{field}')
        require(source['successes']==p['statistics']['benchSuccess'],'Media stage success count mismatch')
    row_by_key={r['episodeKey']:r for r in rows};clips=media['clips'];paths=[]
    require(isinstance(clips,dict) and clips,'No blog clips')
    tasks={t['id']:t for t in alignment['tasks']}
    for clip_id,clip in clips.items():
        require(set(clip)==set('id stage stageLabel episodeId episodeKey suite taskId taskName rolloutIndex seed initStateId instruction originalInstruction status nativeSuccess agentAssessment stopReason steps maxSteps video poster width height frames fps durationSeconds reusedBaselineMedia task source media'.split()),
                'Unexpected clip fields; raw model/environment data is not public')
        alias=clip['stage'];require(alias in MEDIA_STAGES,'Invalid clip stage')
        stage,prefix=MEDIA_STAGES[alias];key=clip['episodeId']
        require(clip_id==clip['id']==f'{alias}:{key}' and key==clip['episodeKey'],'Clip identity mismatch')
        require(key in row_by_key,'Clip episode is absent from paired CSV');row=row_by_key[key]
        require(row[prefix+'Stage']==stage,'Clip references an unexecuted task stage')
        task_id=f'{row["suite"]}_t{int(row["taskId"]):02d}'
        require(clip['suite']==row['suite'] and clip['taskId']==int(row['taskId']),'Clip task mismatch')
        require(clip['taskName']==tasks[task_id]['taskName'],'Clip native task name mismatch')
        require(clip['seed']==int(row['seed']) and clip['initStateId']==int(row['initStateId'])
                and clip['rolloutIndex']==int(key.rsplit('_r',1)[1]),'Clip seed/init mismatch')
        require(clip['instruction']==row[prefix+'Instruction'] and clip['originalInstruction']==row['beforeInstruction'],'Clip instruction mismatch')
        success=boolean(row[prefix+'BenchSuccess'],key)
        require(clip['nativeSuccess'] is success and clip['status']==('success' if success else 'failure'),'Clip native result mismatch')
        require(clip['agentAssessment']==(row[prefix+'AgentOutcome'] or 'unknown'),'Clip agent assessment mismatch')
        require(clip['steps']==int(row[prefix+'Steps']) and clip['maxSteps']==500,'Clip control budget mismatch')
        require(clip['stopReason']==row[prefix+'HostReason'],'Clip stop reason mismatch')
        source=clip['source'];p=provenance[stage]
        require(set(source)==set('run manifestSha256 resultSha256 videoSha256 selectedAttempt bddlSha256 initFileSha256'.split()),
                'Unexpected clip source fields')
        require(source['run']==p['runName'] and source['manifestSha256']==p['manifestSha256'],'Clip provenance mismatch')
        require(source['resultSha256']==row[prefix+'ResultSha256'] and source['selectedAttempt']==row[prefix+'Attempt'],'Clip result source mismatch')
        for field in ('manifestSha256','resultSha256','videoSha256','bddlSha256','initFileSha256'):
            digest_string(source[field],f'clip.source.{field}')
        exact(clip['task'],task_rate(by_task[task_id],prefix),f'clip.{clip_id}.task')
        require(clip['frames']==clip['steps']+11 and clip['fps']==20 and clip['width']==1024 and clip['height']==512,'Clip frame layout mismatch')
        exact(clip['durationSeconds'],clip['frames']/20,'Clip duration')
        require(clip['reusedBaselineMedia'] is (alias=='baseline'),'Baseline reuse marker mismatch')
        expected_root='media/libero' if alias=='baseline' else f'media/blog/libero/{alias}'
        meta=clip['media'];require(meta['verified'] is True and meta['fastStart'] is True,'Clip encoding is unverified')
        require(set(meta)==set('videoSha256 videoBytes posterSha256 posterBytes posterFrame codec pixelFormat fastStart verified'.split()),
                'Unexpected clip encoding fields')
        require(meta['codec']=='h264' and meta['pixelFormat']=='yuv420p','Wrong browser encoding')
        require(meta['posterFrame']==clip['frames']//2,'Poster frame differs from export contract')
        resolved={}
        for kind,extension in [('video','mp4'),('poster','jpg')]:
            local_asset(resolver.media_root or resolver.root,clip[kind],kind,allow_missing=True)
            require(clip[kind]==f'{expected_root}/{key}.{extension}','Clip path does not identify its frozen episode')
            digest_string(meta[kind+'Sha256'],f'clip.{kind}.sha256')
            path=resolver.resolve(clip[kind],kind,meta[kind+'Bytes'],meta[kind+'Sha256'],label=f'{clip_id}: {kind}')
            resolved[kind]=path
            paths.append(path)
        if probe:validate_probe(resolved['video'],clip)
    references=[];case_ids=[]
    require(6<=len(media['pairs'])<=8,'Expected six to eight paired examples')
    for pair in media['pairs']:
        case_ids.append(pair['id']);references.extend([pair['before'],pair['after']])
        require(pair['before'] in clips and pair['after'] in clips,'Broken paired clip reference')
        before,after=clips[pair['before']],clips[pair['after']]
        require(before['stage']=='baseline' and after['stage'] in ('r1','r2'),'Pair must compare baseline with an executed revision')
        for field in ('suite','taskId','rolloutIndex','seed','initStateId'):
            exact(pair[field],before[field],f'pair.{field}');exact(before[field],after[field],f'paired.{field}')
        require(before['episodeId']==after['episodeId'],'Pair is not the same episode slot')
        for field in ('bddlSha256','initFileSha256'):
            require(before['source'][field]==after['source'][field],'Pair changed native benchmark inputs')
        task_id=f'{pair["suite"]}_t{pair["taskId"]:02d}';group=by_task[task_id];prefix=MEDIA_STAGES[after['stage']][1]
        exact(pair['beforeTask'],task_rate(group,'before'),'pair.beforeTask');exact(pair['afterTask'],task_rate(group,prefix),'pair.afterTask')
        transition=transitions(group,'before',prefix)
        exact(pair['pairedMatrix'],{k:transition[v] for k,v in [('S→S','successToSuccess'),('S→F','successToFailure'),('F→S','failureToSuccess'),('F→F','failureToFailure')]},'pair.pairedMatrix')
        eligible=[r for r in group if boolean(r['beforeBenchSuccess'],'pair')==before['nativeSuccess'] and boolean(r[prefix+'BenchSuccess'],'pair')==after['nativeSuccess']]
        require(pair['rolloutIndex']==min(int(r['initStateId']) for r in eligible),'Pair violates declared lowest-index selection')
        require(pair.get('selectionRule') and pair.get('note'),'Missing case selection disclosure')
    for failure in media['failureCases']:
        case_ids.append(failure['id']);references.append(failure['clip'])
        require(failure['clip'] in clips and clips[failure['clip']]['status']=='failure','Failure case references a nonfailure')
        exact(failure['task'],clips[failure['clip']]['task'],'failure.task')
        require(failure.get('selectionRule') and failure.get('note'),'Missing failure selection disclosure')
    require(len(set(case_ids))==len(case_ids),'Duplicate case IDs')
    require(set(references)==set(clips),'Unreferenced or missing clips')
    reused=sum(c['reusedBaselineMedia'] for c in clips.values());validation=media['validation']
    require(validation['verifiedClips']==len(clips) and validation['reusedClips']==reused
            and validation['newClips']==len(clips)-reused,'Media validation counts mismatch')
    require(validation['newMediaBytes']==sum(c['media']['videoBytes']+c['media']['posterBytes'] for c in clips.values() if not c['reusedBaselineMedia']),'New-media byte total mismatch')
    return {'passed':True,'episodeSlots':400,'auditedExecutedEpisodes':510,'tasks':40,
            'afterStageCounts':statistics(rows,'after')['sourceStageCounts'],
            'before':{k:alignment['before'][k] for k in ('benchSuccess','mismatchCount','ias')},
            'after':{k:alignment['after'][k] for k in ('benchSuccess','mismatchCount','ias')},
            'pairedCases':len(media['pairs']),'failureCases':len(media['failureCases']),
            'verifiedClips':len(clips),'hashedAssets':len(paths),'fullVideoProbe':probe}


def load_documents(root):
    alignment=read_json(root/'data/libero-alignment.json')
    media=read_json(root/'data/libero-blog-media.json')
    with (root/'data/libero-alignment-episodes.csv').open(newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream)
        require(reader.fieldnames is not None and len(reader.fieldnames)==len(set(reader.fieldnames)),'Duplicate/missing CSV columns')
        rows=list(reader)
    return alignment,rows,media


def validate_libero_blog(root=ROOT,*,probe=False,media_root=None):
    root=Path(root).resolve()
    return validate_documents(root,*load_documents(root),probe=probe,media_root=media_root)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--media-root',type=Path,help='Local gallery export root; use only these media assets without downloading')
    parser.add_argument('--probe',action='store_true',help='Decode all referenced videos with ffprobe')
    args=parser.parse_args()
    try:
        result=validate_libero_blog(args.root,probe=args.probe,media_root=args.media_root)
    except (ValidationError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f'LIBERO blog validation failed: {exc}',file=sys.stderr)
        return 1
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
