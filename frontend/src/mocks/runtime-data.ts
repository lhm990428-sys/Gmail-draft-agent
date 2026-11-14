import type { Mail } from '../domain';
import type { RuntimeTape } from '../runtime';

export function runtimeTape(mail:Mail,mode:RuntimeTape['mode']='normal'):RuntimeTape{
  const nodes:RuntimeTape['nodes']=[
    {id:'gateway',name:'Gmail 수신',kind:'tool',role:'정규화된 스레드',x:0,y:220,taskId:'t-receive',scope:'승인된 라벨만 읽기'},
    {id:'supervisor',name:'Supervisor',kind:'agent',role:'AI 감독 · 계획/위임/합류',x:540,y:-60,taskId:'t-plan',scope:'위임만 허용 · Gmail 자격증명 없음'},
    {id:'context',name:'Context',kind:'agent',role:'요청·사실·근거 추출',x:240,y:220,taskId:'t-context',scope:'선택 스레드 읽기'},
    {id:'triage',name:'Triage',kind:'agent',role:'회신 필요 여부',x:500,y:110,taskId:'t-triage',scope:'구조화 분류 결과만 반환'},
    {id:'risk',name:'Risk',kind:'agent',role:'민감 주제·정책 판단',x:500,y:350,taskId:'t-risk',scope:'외부 쓰기 권한 없음'},
    {id:'draft',name:'Draft',kind:'agent',role:'근거 기반 회신 작성',x:770,y:240,taskId:'t-draft',scope:'초안 artifact 생성만 허용'},
    {id:'critic',name:'Critic',kind:'agent',role:'독립 검토·수정 요청',x:1030,y:240,taskId:'t-critic',scope:'정책/근거 검토 · 수정 최대 2회'},
    {id:'human',name:'사용자 승인',kind:'human',role:'최종 승인권자 · AI 아님',x:1030,y:480,taskId:'t-review',scope:'수정/승인/거절'},
    {id:'broker',name:'Draft Broker',kind:'tool',role:'승인된 내용만 저장',x:770,y:480,taskId:'t-save',scope:'Draft-only · send 차단'},
    {id:'checkpoint',name:'공유 상태 / Checkpoint',kind:'checkpoint',role:'공개 context · 버전된 상태',x:240,y:570,taskId:'t-checkpoint',scope:'agent별 최소 context 전달 · 비밀 제외'},
  ];
  const edge=(id:string,source:string,target:string,kind:RuntimeTape['edges'][number]['kind'],label:string,contract:string)=>({id,source,target,kind,label,contract});
  const edges=[
    edge('receive','gateway','context','data','Thread','threadId / latestMessageId / redacted body'),
    edge('context-triage','context','triage','data','ContextReport','facts[] / requests[] / evidenceRefs[]'),
    edge('context-risk','context','risk','data','ContextReport','redacted content / policy version'),
    edge('triage-draft','triage','draft','data','TriageReport','category / confidence / priority'),
    edge('risk-draft','risk','draft','data','RiskReport','risk / flags[] / allowed action'),
    edge('draft-critic','draft','critic','data','DraftArtifact','body / revision / evidenceRefs[]'),
    edge('critic-review','critic','human','data','ReviewSnapshot','draft revision / critique / thread hash'),
    edge('approval','human','broker','data','ApprovalIntent','actor / revision / hash / idempotency key'),
    ...['context','triage','risk','draft','critic'].map(n=>edge('dispatch-'+n,'supervisor',n,'delegation','위임','TaskEnvelope / budget / output schema')),
    ...['context','triage','risk','draft','critic'].map(n=>edge('memory-'+n,n,'checkpoint','memory','상태 기록','public state delta / sequence / checkpoint version')),
    edge('rework','critic','draft','rework','수정 요청','CritiqueReport / attempt ≤2 / missing facts'),
  ];
  const deps:Record<string,string[]>={context:['t-receive','t-plan'],triage:['t-context'],risk:['t-context'],draft:['t-triage','t-risk'],critic:['t-draft'],human:['t-critic'],broker:['t-review']};
  const tasks=nodes.map(n=>({id:n.taskId,owner:n.id,goal:n.role,dependsOn:deps[n.id]??[]}));
  const events:RuntimeTape['events']=[];
  const add=(nodeId:string,status:RuntimeTape['events'][number]['status'],type:string,summary:string,extra:Partial<RuntimeTape['events'][number]>={})=>{const sequence=events.length+1;events.push({sequence,atMs:(sequence-1)*550,nodeId,status,type,summary,...extra});};
  add('gateway','running','tool.started','승인된 Gmail 라벨에서 메일 한 건 확인',{input:`${mail.id} · ${mail.latestMessageId}`});
  if(mode==='timeout'){
    add('gateway','running','tool.retry','read timeout · attempt 2/3');add('gateway','running','tool.retry','read timeout · attempt 3/3');add('gateway','failed','tool.retry.exhausted','재시도 종료 · 외부 쓰기 없음',{output:'504 timeout · DEBUG_REQUIRED'});
  }else{
    add('gateway','done','mail.received',mail.subject,{output:mail.preview,edgeId:'receive'});
    add('supervisor','running','supervisor.plan','문맥 → 병렬 분류·위험 → 작성·검토 → 사람 승인',{input:mail.preview,memory:{goal:'회신 필요 분류와 검토 가능한 초안',budget:'12 turns / depth 2 / concurrency 3'}});
    add('supervisor','done','supervisor.plan.accepted','계획 검증 완료 · t-plan 선행 조건 충족',{output:'Context 이후 Triage/Risk 병렬 위임'});
    add('context','queued','task.dispatched','t-context 위임',{edgeId:'dispatch-context'});
    add('context','running','agent.started','원문에서 요청과 근거 추출',{input:mail.originalBody});
    add('context','done','agent.completed','ContextReport 준비',{output:mail.preview,memory:{requests:mail.preview,unconfirmed:'사용자 일정·참석 확정 여부',evidence:`${mail.latestMessageId}:body`},edgeId:'context-triage'});
    add('triage','running','agent.started','회신 분류 · Risk와 병렬',{input:mail.preview,edgeId:'dispatch-triage'});
    add('risk','running','agent.started','위험·민감 주제 검사 · Triage와 병렬',{input:mail.preview,edgeId:'dispatch-risk'});
    add('triage','done','agent.completed',mail.category,{output:`${mail.category} · confidence ${mail.confidence}`,memory:{category:mail.category,confidence:String(mail.confidence)},edgeId:'triage-draft'});
    add('risk','done','agent.completed',`위험 ${mail.risk}`,{output:mail.flags.join(' / ')||'추가 위험 경고 없음',memory:{risk:mail.risk,flags:mail.flags.join(' / ')||'none'},edgeId:'risk-draft'});
    add('supervisor','done','supervisor.join','분류/위험 결과 합류 · 필수 단계 검증',{output:'Task DAG 통과 · 사람 승인 필수',memory:{decision:mail.category,permissions:'Draft artifact only · 외부 쓰기는 Broker만'}});
    if(mail.category==='NO_REPLY'){
      add('checkpoint','done','run.completed','회신 불필요 · 작성/검토/쓰기 생략',{checkpoint:`cp-${mail.runId}-no-reply`,memory:{decision:'NO_REPLY',write:'none'}});
    }else{
      add('draft','running','agent.started','초안 작성',{input:mail.preview,edgeId:'dispatch-draft'});
      add('draft','done','agent.completed','DraftArtifact rev 1',{output:mode==='rework'?'화요일 미팅에 참석하겠습니다.':mail.draftBody,memory:{revision:'1',evidence:`${mail.latestMessageId}:body`},edgeId:'draft-critic'});
      add('critic','running','agent.started','근거·완결성·말투 독립 검토',{input:'원문 근거 + DraftArtifact',edgeId:'dispatch-critic'});
      if(mode==='rework'){
        add('critic','done','critic.rework','미확정 참석 표현 수정 필요',{output:'확정 표현을 확인 후 회신으로 변경',memory:{verdict:'revise',reason:'참석 여부는 미확정'},edgeId:'rework'});
        add('draft','running','agent.restarted','수정 1/2 · CritiqueReport 반영',{input:'미확정 사실을 확정하지 말 것',edgeId:'rework'});
        add('draft','done','agent.completed','DraftArtifact rev 2',{output:mail.draftBody,memory:{revision:'2',change:'미확정 약속 제거'},edgeId:'draft-critic'});
        add('critic','running','agent.started','수정본 재검토');
      }
      add('critic','done','agent.completed','검토 통과 · 사람에게 이관',{output:'근거와 요청 반영 확인 · 최종 결정은 사용자',memory:{verdict:'pass'},edgeId:'critic-review'});
      add('checkpoint','done','checkpoint.saved','검토 대상과 공개 상태 고정',{checkpoint:`cp-${mail.runId}-review`,memory:{thread:mail.latestMessageId,draftRevision:String(mode==='rework'?2:mail.revision),approval:'pending'}});
      add('human','waiting','review.requested','사용자 승인 대기 · 외부 쓰기 없음',{input:mail.draftBody,edgeId:'critic-review'});
      if(mail.status!=='waiting'){
        add('human','done',mail.status==='draft_saved'?'review.approved':'review.rejected',mail.status==='draft_saved'?'사용자 승인':'사용자 거절',{output:`revision ${mail.revision}`,edgeId:mail.status==='draft_saved'?'approval':undefined});
        if(mail.status==='draft_saved'){add('broker','running','draft.write.started','승인 intent 검증');add('broker','done','draft.saved','합성 Draft 저장 · 실제 발송 없음',{output:`mock-draft-${mail.id}`,memory:{draftId:`mock-draft-${mail.id}`,write:'synthetic only'}});}
        add('checkpoint','done','checkpoint.saved','처리 결과 고정',{checkpoint:`cp-${mail.runId}-result`,memory:{approval:mail.status==='draft_saved'?'approved':'rejected',draftRevision:String(mail.revision)}});
      }
    }
  }
  return {version:'runtime.v1',source:'synthetic',runId:mail.runId,mode,nodes,edges,tasks,events};
}
