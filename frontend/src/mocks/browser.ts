import { setupWorker } from 'msw/browser';
import { http, HttpResponse, delay } from 'msw';
import { createSnapshot } from './data';
import type { ReviewAction } from '../domain';
import { scenarioSnapshot } from './scenarios';
import { caseDetails } from './detail-data';
import { RuntimeJournal } from './runtime-journal';

const state = createSnapshot();
const runtimeJournal=new RuntimeJournal(state.mails);
let serial = 1043;
let stalePending=false;
let uncertainIntent=false;
const error = (detail:string,status=400)=>HttpResponse.json({detail},{status});
export const worker=setupWorker(
  http.get('/api/v1/releases/:id/evidence',({params})=>{
    const release=state.releases.find(r=>r.id===params.id);if(!release)return error('릴리스가 없습니다.',404);
    const baseline=release.id==='r0.2.0';const hold=release.id==='r0.2.2';
    const experiment=structuredClone(state.experiments.find(e=>e.releaseId===release.id)??null);
    if(experiment&&baseline)experiment.metrics=state.experiments[0].metrics.map(m=>({...m,candidate:m.baseline}));
    return HttpResponse.json({releaseId:release.id,window:hold?'미완료 shadow · 합성 80건':baseline?'기준 버전 · 합성 staging 240건':'후보 버전 · 합성 staging 248건',experiment,metrics:{executions:hold?80:baseline?240:248,successes:hold?78:baseline?238:245,p95:hold?null:baseline?22.8:24.6,tokens:hold?null:baseline?1310000:1420000,cost:hold?null:baseline?3.37:3.64,coverage:hold?null:state.demoScenario==='missing-events'?.92:1},diagnosis:{quality:hold?null:baseline?.89:.81,status:hold?'UNKNOWN':baseline?'HEALTHY':release.decision==='DEBUG_REQUIRED'?'UNHEALTHY':'DEGRADED',hypothesis:hold?'평가와 이벤트 대사가 완료되지 않아 원인 및 출시 판단을 보류합니다.':baseline?'기준 버전 검증 요약이 통과했습니다.':state.incidents[0].cause,evidence:hold?['shadow 완료 80/200','평가 진행 중','Outbox 대사 미완료']:baseline?['holdout 300개 기준 통과','staging 240개 관측 완료']:state.incidents[0].evidence,nextAction:hold?'평가·관측·이벤트 대사 증거를 완결하세요.':baseline?'manifest를 확인한 뒤 사람이 canary 승격 여부를 결정합니다.':state.incidents[0].action}});
  }),
  http.get('/api/v1/runs/:id/runtime',({params,request})=>{
    const run=state.runs.find(r=>r.id===params.id);if(!run)return error('실행을 찾을 수 없습니다.',404);
    const mail=state.mails.find(m=>m.runId===run.id)??{...state.mails[0],runId:run.id,subject:run.subject,status:run.status==='success'?'draft_saved' as const:'waiting' as const};
    const mode=new URL(request.url).searchParams.get('mode');
    return HttpResponse.json(runtimeJournal.read(mail,mode==='rework'?'rework':mode==='timeout'||run.status==='failed'?'timeout':'normal'));
  }),
  http.get('/api/v1/evaluations/cases/:id',({params})=>{
    const detail=caseDetails.find(c=>c.id===params.id);return detail?HttpResponse.json(detail):error('평가 사례가 없습니다.',404);
  }),
  http.get('/api/v1/releases/:id/manifest',({params})=>{
    const release=state.releases.find(r=>r.id===params.id);if(!release)return error('릴리스가 없습니다.',404);
    return HttpResponse.json({releaseId:release.id,graph:'gmail-supervised@1.0',policy:'draft-only@1.0',priceSnapshot:'price.mock.2026-10-05',agents:state.agents.map(a=>({id:a.id,version:release.id==='r0.2.0'&&a.id==='draft'?'1.0.0':a.version,prompt:release.id==='r0.2.0'&&a.id==='draft'?'draft@41a82c':a.prompt,model:a.model}))});
  }),
  http.post('/api/v1/mock/scenario',async({request})=>{
    const body=await request.json() as {id:string};const fresh=scenarioSnapshot(body.id);
    if(!fresh)return error('지원하지 않는 합성 시나리오입니다.',404);
    Object.assign(state,fresh);serial=1043;stalePending=body.id==='stale-review';uncertainIntent=false;
    runtimeJournal.reset(state.mails);
    return HttpResponse.json(state);
  }),
  http.get('/api/v1/snapshot',async({request})=>{
    await delay(180);
    const scenario=new URL(request.url).searchParams.get('scenario');
    if(scenario==='error')return error('합성 네트워크 오류입니다. 다시 시도해 주세요.',503);
    return HttpResponse.json(state);
  }),
  http.put('/api/v1/reviews/:id/draft',async({params,request})=>{
    const mail=state.mails.find(m=>m.id===params.id);
    if(!mail)return error('메일을 찾을 수 없습니다.',404);
    const body=await request.json() as {revision:number;body:string};
    if(mail.status!=='waiting')return error('이미 처리된 검토입니다.',409);
    if(mail.id==='m-101'&&uncertainIntent)return error('저장 결과 대사 전에는 초안을 편집할 수 없습니다.',409);
    if(mail.revision!==body.revision)return error('초안 버전이 변경되었습니다. 새로고침 후 다시 검토해 주세요.',409);
    if(typeof body.body!=='string'||!body.body.trim())return error('초안 내용을 입력해 주세요.');
    mail.draftBody=body.body;mail.revision++;
    runtimeJournal.append(mail.runId,{nodeId:'human',status:'waiting',type:'draft.edited',summary:`사람 수정 · 검토 revision ${mail.revision}`,input:mail.draftBody,memory:{reviewRevision:String(mail.revision)}});
    const run=state.runs.find(r=>r.id===mail.runId);
    if(run){const sequence=run.events.length+1;run.events.push({id:`${run.id}-edited-${sequence}`,sequence,time:'검토 시점',type:'draft.edited',actor:'human',detail:`합성 초안 수정 · revision ${mail.revision}`,status:'success',spanId:'sp-review'});}
    return HttpResponse.json(mail);
  }),
  http.post('/api/v1/reviews/:id/decision',async({params,request})=>{
    const mail=state.mails.find(m=>m.id===params.id);
    if(!mail)return error('메일을 찾을 수 없습니다.',404);
    const body=await request.json() as {revision:number;action:ReviewAction};
    if(!['approve','reject'].includes(body.action))return error('허용되지 않은 결정입니다.');
    if(mail.status!=='waiting'||mail.revision!==body.revision)return error('검토 상태나 초안 버전이 변경되었습니다.',409);
    if(mail.id==='m-101'&&uncertainIntent)return error('저장 결과가 불확실합니다. 승인·거절 대신 결과 대사를 진행해 주세요.',409);
    if(body.action==='approve'&&(mail.category==='NO_REPLY'||!mail.draftBody.trim()))return error('승인할 초안이 없습니다.');
    if(body.action==='approve'&&mail.id==='m-101'&&stalePending){
      stalePending=false;mail.revision++;mail.latestMessageId='msg-101-new';mail.originalBody+='\n\n[새 메시지] 미팅 시간이 화요일 오후 3시로 변경되었습니다. 참석 가능 여부 확인 부탁드립니다.';mail.draftBody='안녕하세요. 변경된 화요일 오후 3시 참석 가능 여부를 확인한 뒤 회신드리겠습니다. 감사합니다.';mail.flags=['새 메시지가 도착해 이전 승인을 차단했습니다. 변경된 일정과 초안을 다시 검토하세요.'];
      mail.preview='미팅 시간이 화요일 오후 3시로 변경되었습니다. 참석 가능 여부를 확인해 주세요.';
      runtimeJournal.append(mail.runId,{nodeId:'human',status:'waiting',type:'review.invalidated',summary:'새 메시지로 이전 승인 차단 · 최신 fixture 초안 재검토',input:mail.draftBody,memory:{latestMessageId:mail.latestMessageId,reviewRevision:String(mail.revision)}});
      const run=state.runs.find(r=>r.id===mail.runId)!;run.events.push({id:`${run.id}-invalidated`,sequence:run.events.length+1,time:'합성 검토 시점',type:'review.invalidated',actor:'policy',detail:'최신 message 변경 · 이전 승인 차단 · revision 2 재검토',status:'waiting',spanId:'sp-review'});
      return error('새 메시지가 도착했습니다. 이전 초안을 저장하지 않았습니다. 최신 데이터 조회 후 다시 검토하세요.',409);
    }
    if(body.action==='approve'&&mail.id==='m-101'&&state.demoScenario==='draft-uncertain'){
      runtimeJournal.append(mail.runId,{nodeId:'human',status:'done',type:'review.approved',summary:'사람 승인 · 쓰기 intent 생성',input:mail.draftBody,memory:{approvedRevision:String(mail.revision)},edgeId:'approval'});
      runtimeJournal.append(mail.runId,{nodeId:'broker',status:'running',type:'draft.write.started',summary:'승인된 intent 검증 · 합성 저장 시도'});
      runtimeJournal.append(mail.runId,{nodeId:'broker',status:'uncertain',type:'draft.write.uncertain',summary:'응답 유실 · 재저장 금지 · 대사 필요',memory:{intent:'mock-intent-m-101',outcome:'unknown'}});
      if(!uncertainIntent){uncertainIntent=true;mail.flags.push('Draft 저장 응답 유실 · 결과 대사 전 재저장 금지');const run=state.runs.find(r=>r.id===mail.runId)!;run.events.push({id:'uncertain-save',sequence:run.events.length+1,time:'합성 저장 시점',type:'draft.write.uncertain',actor:'broker',detail:'intent mock-intent-m-101 · 응답 유실 · 자동 재시도 금지',status:'error',spanId:'sp-review'});}
      return error('Draft 저장 결과가 불확실합니다. 재승인 대신 상세 화면의 저장 결과 대사를 사용하세요.',503);
    }
    mail.status=body.action==='approve'?'draft_saved':'rejected';
    runtimeJournal.append(mail.runId,{nodeId:'human',status:'done',type:body.action==='approve'?'review.approved':'review.rejected',summary:body.action==='approve'?'사람 승인':'사람 거절 · 외부 쓰기 없음',input:mail.draftBody,memory:{reviewRevision:String(mail.revision),decision:body.action},edgeId:body.action==='approve'?'approval':undefined});
    if(body.action==='approve'){
      runtimeJournal.append(mail.runId,{nodeId:'broker',status:'running',type:'draft.write.started',summary:'승인 intent 검증'});
      runtimeJournal.append(mail.runId,{nodeId:'broker',status:'done',type:'draft.saved',summary:'합성 Draft 저장 · 실제 발송 없음',output:`mock-draft-${mail.id}`,memory:{draftId:`mock-draft-${mail.id}`,outcome:'confirmed'}});
    }
    runtimeJournal.append(mail.runId,{nodeId:'checkpoint',status:'done',type:'checkpoint.saved',summary:'사람 결정과 저장 결과 기록',checkpoint:`cp-${mail.runId}-result`,memory:{approval:body.action,reviewRevision:String(mail.revision)}});
    const run=state.runs.find(r=>r.id===mail.runId);
    if(run){
      run.status='success';
      run.spans.forEach(s=>{if(s.status==='waiting'){s.status='success';s.output=body.action==='approve'?'사용자 승인 · 합성 Draft 저장':'사용자 거절 · 외부 쓰기 없음';}});
      const seq=run.events.length+1;
      run.events.push({id:`${run.id}-decision-${seq}`,sequence:seq,time:'검토 시점',type:body.action==='approve'?'draft.saved':'review.rejected',actor:'human',detail:`revision ${mail.revision} · ${body.action==='approve'?'합성 Draft 저장 · 발송 없음':'거절 완료'}`,status:'success',spanId:'sp-review'});
    }
    return HttpResponse.json({id:mail.id,status:mail.status,draftId:body.action==='approve'?`mock-draft-${mail.id}`:null});
  }),
  http.post('/api/v1/reviews/:id/reconcile',({params})=>{
    const mail=state.mails.find(m=>m.id===params.id);
    if(!mail)return error('메일을 찾을 수 없습니다.',404);
    if(mail.id!=='m-101'||!uncertainIntent)return error('대사할 불확실한 저장 intent가 없습니다.',409);
    mail.status='draft_saved';mail.flags=['동일 intent의 합성 Draft 확인 · 중복 저장 없이 대사 완료'];uncertainIntent=false;
    runtimeJournal.append(mail.runId,{nodeId:'broker',status:'done',type:'draft.reconciled',summary:'동일 intent의 Draft 확인 · 중복 생성 없음',output:'mock-draft-m-101',memory:{draftId:'mock-draft-m-101',outcome:'confirmed'}});
    runtimeJournal.append(mail.runId,{nodeId:'checkpoint',status:'done',type:'checkpoint.saved',summary:'대사 결과 기록',checkpoint:`cp-${mail.runId}-reconciled`,memory:{approval:'approved',write:'reconciled'}});
    const run=state.runs.find(r=>r.id===mail.runId)!;run.status='success';run.spans.forEach(s=>{if(s.status==='waiting'){s.status='success';s.output='동일 intent Draft 대사 완료';}});run.events.push({id:'reconciled-save',sequence:run.events.length+1,time:'합성 대사 시점',type:'draft.reconciled',actor:'broker',detail:'mock-draft-m-101 · 중복 생성 없음',status:'success',spanId:'sp-review'});
    return HttpResponse.json({id:mail.id,status:mail.status,draftId:'mock-draft-m-101'});
  }),
  http.post('/api/v1/runs/:id/retry',({params})=>{
    const source=state.runs.find(r=>r.id===params.id);
    if(!source)return error('실행을 찾을 수 없습니다.',404);
    if(source.status!=='failed')return error('실패한 실행만 수동 재실행할 수 있습니다.',409);
    state.dependencies[0].status='ready';state.dependencies[0].description='합성 수동 복구 완료 · 실제 Gmail probe 아님';
    state.health.find(h=>h.id==='dependencies')!.status='HEALTHY';
    const run=createSnapshot().runs[0];run.id=`ex-${serial++}`;run.subject=`복구 재실행 · ${source.subject}`;
    run.spans[0].input=`합성 재실행 · parent ${source.id} · execution ${run.id}`;
    run.events=run.events.map(e=>({...e,id:`${run.id}-${e.sequence}`}));run.events[0].detail=`사람 승인 재실행 · source ${source.id}`;state.runs.unshift(run);
    const mail=createSnapshot().mails[0];mail.id=`m-${run.id}`;mail.runId=run.id;mail.subject=run.subject;state.mails.unshift(mail);
    runtimeJournal.register(mail);
    return HttpResponse.json({id:run.id},{status:201});
  }),
  http.post('/api/v1/runs',async()=>{
    const run=createSnapshot().runs[0];run.id=`ex-${serial++}`;run.subject='새 합성 실행 · 테스트 메일 분석';run.startedAt='목업 실행 시점';
    run.spans[0].input=`검색 범위: label:agent-test\nexecution: ${run.id}\nrelease: ${run.releaseId}`;
    run.events=run.events.map(e=>({...e,id:`${run.id}-${e.sequence}`}));
    state.runs.unshift(run);
    const mail=createSnapshot().mails[0];mail.id=`m-${run.id}`;mail.runId=run.id;mail.subject=run.subject;mail.latestMessageId=`msg-${run.id}`;
    state.mails.unshift(mail);
    runtimeJournal.register(mail);
    return HttpResponse.json({id:run.id},{status:201});
  }),
  http.post('/api/v1/releases/:id/promote',({params})=>{
    const release=state.releases.find(r=>r.id===params.id);
    if(!release)return error('릴리스를 찾을 수 없습니다.',404);
    if(release.decision!=='READY_FOR_APPROVAL'||release.gates.some(g=>g.status!=='PASS')||release.state==='promoted')return error('모든 게이트를 통과한 미승격 릴리스만 승인할 수 있습니다.',409);
    release.state='promoted';return HttpResponse.json(release);
  }),
);
