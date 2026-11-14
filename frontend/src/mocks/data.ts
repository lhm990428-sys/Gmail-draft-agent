import type { Snapshot, Run } from '../domain';

const baseSpans:Run['spans']=[
  {id:'sp-root',parentId:null,name:'email.workflow',agentId:'supervisor',type:'chain',status:'waiting',durationMs:12400,inputTokens:null,outputTokens:null,input:'검색 범위: label:agent-test\nexecution: ex-1042\nrelease: r0.2.1',output:'초안 준비 완료 · 사람 승인 대기',attempt:1},
  {id:'sp-plan',parentId:'sp-root',name:'supervisor.plan',agentId:'supervisor',type:'llm',status:'success',durationMs:1380,inputTokens:842,outputTokens:188,input:'목표: 회신 필요 여부를 판단하고 승인 가능한 초안을 준비',output:'Context → [Triage ∥ Risk] → Draft → Critic → Human Review',attempt:1},
  {id:'sp-context',parentId:'sp-root',name:'context.extract',agentId:'context',type:'llm',status:'success',durationMs:1840,inputTokens:1240,outputTokens:246,input:'다음 주 화요일 오후 2시 미팅 참석 여부 문의',output:'요청: 미팅 참석 여부 · 확정 여부는 사용자 검토 필요',attempt:1},
  {id:'sp-triage',parentId:'sp-root',name:'triage.classify',agentId:'triage',type:'llm',status:'success',durationMs:1320,inputTokens:638,outputTokens:92,input:'ContextReport: 참석 여부에 대한 응답 필요',output:'REPLY_REQUIRED · confidence 0.97 · priority normal',attempt:1},
  {id:'sp-risk',parentId:'sp-root',name:'risk.screen',agentId:'risk',type:'llm',status:'success',durationMs:1160,inputTokens:640,outputTokens:84,input:'정규화된 스레드 · policy.v1',output:'risk low · injection false · 약속 미확정',attempt:1},
  {id:'sp-draft',parentId:'sp-root',name:'draft.generate',agentId:'draft',type:'llm',status:'success',durationMs:3100,inputTokens:1126,outputTokens:248,input:'Context + Triage + Risk + 격식 있는 한국어',output:'미팅 시간과 참석 가능 여부를 확인하는 초안 생성',attempt:1},
  {id:'sp-critic',parentId:'sp-root',name:'critic.review',agentId:'critic',type:'llm',status:'success',durationMs:2480,inputTokens:1260,outputTokens:208,input:'draft artifact + evidence refs',output:'grounding 0.94 · completeness 0.91 · 통과',attempt:1},
  {id:'sp-review',parentId:'sp-root',name:'human.interrupt',agentId:'human',type:'review',status:'waiting',durationMs:0,inputTokens:null,outputTokens:null,input:'draft revision 1 · 승인 snapshot 고정',output:'사용자 승인·수정·거절을 기다리는 중',attempt:1},
];
const baseEvents:Run['events']=[
  {id:'evt-01',sequence:1,time:'11:42:00.000',type:'request.received',actor:'gateway',detail:'테스트 라벨 분석 요청 접수',status:'success',spanId:'sp-root'},
  {id:'evt-02',sequence:2,time:'11:42:00.080',type:'run.admitted',actor:'runtime',detail:'범위·권한·manifest 검증 완료',status:'success',spanId:'sp-root'},
  {id:'evt-03',sequence:3,time:'11:42:01.460',type:'supervisor.plan',actor:'supervisor',detail:'Task DAG 작성 · 6단계 계획',status:'success',spanId:'sp-plan'},
  {id:'evt-04',sequence:4,time:'11:42:03.300',type:'agent.completed',actor:'context',detail:'스레드 사실과 근거 추출',status:'success',spanId:'sp-context'},
  {id:'evt-05',sequence:5,time:'11:42:03.320',type:'task.dispatched',actor:'runtime',detail:'Triage와 Risk 병렬 dispatch',status:'success',spanId:'sp-triage'},
  {id:'evt-06',sequence:6,time:'11:42:04.640',type:'task.joined',actor:'supervisor',detail:'분류·위험 결과 충돌 없음',status:'success',spanId:'sp-triage'},
  {id:'evt-07',sequence:7,time:'11:42:07.740',type:'agent.completed',actor:'draft',detail:'초안 revision 1 생성',status:'success',spanId:'sp-draft'},
  {id:'evt-08',sequence:8,time:'11:42:10.220',type:'agent.completed',actor:'critic',detail:'근거·정책 검토 통과',status:'success',spanId:'sp-critic'},
  {id:'evt-09',sequence:9,time:'11:42:12.400',type:'review.requested',actor:'runtime',detail:'checkpoint cp-1042 저장 · 승인 대기',status:'waiting',spanId:'sp-review'},
];
const makeRun=(id:string,subject:string,status:Run['status'],decision:string,time:string):Run=>{
  const noReply=decision==='NO_REPLY';
  const spans=baseSpans.filter(s=>!noReply||!['sp-draft','sp-critic','sp-review'].includes(s.id)).map(s=>({...s,
    durationMs:s.id==='sp-root'&&noReply?4800:s.durationMs,
    input:s.id==='sp-root'?`검색 범위: label:agent-test\nexecution: ${id}\nrelease: r0.2.1`:s.id==='sp-context'?subject:s.input,
    output:s.id==='sp-root'?status==='review'?'초안 준비 완료 · 사람 승인 대기':status==='failed'?'의존성 오류로 실행 실패':noReply?'회신 불필요 · 초안 생성 생략':'승인된 합성 Draft 저장 완료':s.id==='sp-triage'?`${decision} · 구조화 분류 결과`:s.id==='sp-context'?`메일 요청 추출: ${subject}`:s.id==='sp-review'&&status==='success'?'사용자 승인 완료':s.output,
    status:s.id==='sp-root'?status==='failed'?'error' as const:status==='review'?'waiting' as const:'success' as const:s.id==='sp-review'&&status==='success'?'success' as const:s.status,
  }));
  const events=baseEvents.filter(e=>spans.some(s=>s.id===e.spanId)).map(e=>({...e,id:`${id}-${e.id}`,time:time+' +'+e.sequence+'단계',detail:e.type==='review.requested'?`checkpoint cp-${id} 저장 · 승인 대기`:e.detail}));
  if(status==='success')events.push({id:`${id}-completed`,sequence:events.length+1,time:time+' 완료',type:noReply?'run.completed':'draft.saved',actor:noReply?'runtime':'human',detail:noReply?'회신 불필요 · 외부 쓰기 없음':'사람 승인 · 합성 Draft 저장',status:'success',spanId:noReply?'sp-root':'sp-review'});
  return {
  id,subject,status,decision,startedAt:time,latency:12.4,tokens:6812,cost:0.016,releaseId:'r0.2.1',
  plan:noReply?['스레드 사실·근거 추출','Triage / Risk 병렬 판단','회신 불필요 · 실행 종료']:['스레드 사실·근거 추출','Triage / Risk 병렬 판단','회신 초안 생성','Critic 독립 검토',status==='success'?'사람 승인 완료':'사람 승인 대기'],
  spans,events,
  ...noReply?{latency:4.8,tokens:spans.reduce((sum,s)=>sum+(s.inputTokens??0)+(s.outputTokens??0),0),cost:0.008}:{},
};};
const failedRun=():Run=>({
  ...makeRun('ex-1037','리서치 자료 수신 확인','failed','DEPENDENCY_TIMEOUT','08:52:19'),
  tokens:0,cost:0,latency:15,plan:['범위·manifest 검증','Gmail 스레드 읽기','제한 재시도 종료 · 디버그 필요'],
  spans:[{...baseSpans[0],status:'error',durationMs:15000,input:'execution: ex-1037 · Gmail thread read',output:'테스트 Gmail 어댑터 timeout · attempt 3/3'},{...baseSpans[2],name:'gmail.thread.read',type:'tool',status:'error',durationMs:15000,attempt:3,inputTokens:null,outputTokens:null,input:'합성 Gmail 스레드 요청',output:'504 Gateway timeout · 제한 재시도 종료'}],
  events:[{id:'ex-1037-01',sequence:1,time:'08:52:19',type:'request.received',actor:'gateway',detail:'합성 실행 접수',status:'success',spanId:'sp-root'},{id:'ex-1037-02',sequence:2,time:'08:52:34',type:'tool.retry.exhausted',actor:'runtime',detail:'Gmail read timeout · 3회 제한 종료',status:'error',spanId:'sp-context'},{id:'ex-1037-03',sequence:3,time:'08:52:34',type:'run.failed',actor:'runtime',detail:'외부 쓰기 없음 · DEBUG_REQUIRED',status:'error',spanId:'sp-root'}],
});
export const createSnapshot=():Snapshot=>({
  schemaVersion:'console.v1',environment:'staging',generatedAt:'2026-10-05T11:42:12+09:00',
  metrics:{executions:248,successes:245,avgLatency:12.4,p95:24.6,tokens:1420000,cost:3.64,coverage:1},
  trend:[
    {time:'00:00',executions:22,tokens:124000,latency:18.2,cost:0.32},
    {time:'03:00',executions:18,tokens:106000,latency:16.8,cost:0.27},
    {time:'06:00',executions:25,tokens:148000,latency:21.4,cost:0.38},
    {time:'09:00',executions:33,tokens:187000,latency:24.6,cost:0.48},
    {time:'12:00',executions:42,tokens:239000,latency:22.1,cost:0.61},
    {time:'15:00',executions:40,tokens:223000,latency:19.8,cost:0.57},
    {time:'18:00',executions:38,tokens:215000,latency:23.4,cost:0.55},
    {time:'21:00',executions:30,tokens:178000,latency:20.7,cost:0.46},
  ],
  agents:[
    {id:'supervisor',name:'Supervisor',role:'업무 감독',description:'업무 계획, 위임, 결과 통합과 사람 이관',status:'healthy',version:'1.0.0',model:'supervisor-primary',prompt:'sup@b38f1a',tools:['agent.dispatch','registry.read'],calls:248,score:.97,latency:1.4,maxTokens:4000,timeout:30},
    {id:'context',name:'Context',role:'문맥 이해',description:'스레드에서 사실, 요청, 근거 위치 추출',status:'healthy',version:'1.0.0',model:'worker-efficient',prompt:'ctx@83c14d',tools:['gmail.thread.read'],calls:248,score:.94,latency:1.8,maxTokens:4000,timeout:30},
    {id:'triage',name:'Triage',role:'회신 분류',description:'회신 필요 여부, 우선순위와 신뢰도 분류',status:'healthy',version:'1.0.0',model:'worker-efficient',prompt:'tri@04ac8d',tools:[],calls:248,score:.93,latency:1.3,maxTokens:2500,timeout:20},
    {id:'risk',name:'Risk',role:'위험 판단',description:'인젝션, 민감 주제와 위험 행동 검사',status:'healthy',version:'1.0.0',model:'worker-efficient',prompt:'risk@f290cb',tools:[],calls:248,score:.98,latency:1.2,maxTokens:2500,timeout:20},
    {id:'draft',name:'Draft',role:'회신 작성',description:'스레드의 사실과 말투에 근거한 회신 작성',status:'degraded',version:'1.1.0',model:'writer-primary',prompt:'draft@72d39e',tools:[],calls:162,score:.81,latency:3.1,maxTokens:4500,timeout:40},
    {id:'critic',name:'Critic',role:'독립 검토',description:'초안 근거·완결성·말투를 검토하고 수정 요청',status:'healthy',version:'1.0.0',model:'judge-independent',prompt:'crit@04d28b',tools:[],calls:162,score:.94,latency:2.5,maxTokens:3000,timeout:30},
    {id:'diagnose',name:'Diagnose',role:'운영 진단',description:'운영 증거를 묶어 원인 후보와 개선 방향 제시',status:'healthy',version:'1.0.0',model:'diagnose-primary',prompt:'diag@a742be',tools:['ops.traces.read','ops.eval.read'],calls:12,score:.92,latency:4.2,maxTokens:5000,timeout:40},
  ],
  mails:[
    {id:'m-101',sender:'김지은',address:'jieun@example.test',subject:'다음 주 미팅 일정 확인 부탁드립니다',preview:'화요일 오후 2시 미팅 참석 가능하신지 확인 부탁드립니다.',receivedAt:'11:42',category:'REPLY_REQUIRED',confidence:.97,risk:'low',priority:'normal',status:'waiting',originalBody:'안녕하세요, 임헌민님.\n\n다음 주 화요일 오후 2시에 프로젝트 진행 상황을 공유하는 미팅을 갖고자 합니다. 해당 시간에 참석 가능하신지 확인 부탁드립니다.\n\n안건은 에이전트 구축 일정과 평가 계획이며, 약 30분 정도 소요될 예정입니다.\n\n감사합니다.\n김지은 드림',draftBody:'안녕하세요, 지은님.\n\n미팅 일정과 안건 공유 감사합니다. 다음 주 화요일 오후 2시 참석 가능 여부를 확인한 뒤 회신드리겠습니다.\n\n공유해 주신 안건도 함께 확인했습니다.\n\n감사합니다.\n임헌민 드림',revision:1,runId:'ex-1042',flags:['참석 확정 여부는 사용자 확인이 필요합니다.'],latestMessageId:'msg-101'},
    {id:'m-102',sender:'박서준',address:'seojun@example.test',subject:'프로젝트 견적서 검토 및 의견 요청',preview:'첨부한 견적서를 확인하시고 금요일까지 의견 부탁드립니다.',receivedAt:'10:58',category:'REVIEW_REQUIRED',confidence:.89,risk:'medium',priority:'high',status:'waiting',originalBody:'안녕하세요.\n\n프로젝트 견적서 초안을 전달드립니다. 금요일까지 검토 의견 부탁드립니다. 계약 조건은 확인 후 별도로 협의하려 합니다.\n\n박서준 드림',draftBody:'안녕하세요, 서준님.\n\n견적서 공유 감사합니다. 검토 후 의견을 전달드리겠습니다. 계약 조건은 내용을 확인한 뒤 별도로 협의하겠습니다.\n\n감사합니다.',revision:1,runId:'ex-1041',flags:['견적·계약 관련 민감 주제입니다.','첨부파일은 목업에서 처리하지 않습니다.'],latestMessageId:'msg-102'},
    {id:'m-103',sender:'이하늘',address:'haneul@example.test',subject:'LLMOps 평가 데이터셋 공유드립니다',preview:'테스트 데이터셋을 공유합니다. 수신 확인 부탁드립니다.',receivedAt:'10:31',category:'REPLY_REQUIRED',confidence:.95,risk:'low',priority:'normal',status:'waiting',originalBody:'안녕하세요.\n\n평가 데이터셋 준비가 완료되어 공유드립니다. 수신 여부 확인 부탁드립니다. 민감 정보는 비식별화했으며 라벨링 기준도 함께 포함했습니다.\n\n이하늘 드림',draftBody:'안녕하세요, 하늘님.\n\n데이터셋 공유 메일을 확인했습니다. 준비해주셔서 감사합니다. 라벨링 기준과 데이터 내용을 검토한 뒤 필요한 사항이 있으면 연락드리겠습니다.\n\n감사합니다.',revision:1,runId:'ex-1040',flags:[],latestMessageId:'msg-103'},
    {id:'m-104',sender:'Product Weekly',address:'weekly@example.test',subject:'이번 주 AI 제품 업데이트',preview:'이번 주 주요 제품 소식과 출시 정보를 확인하세요.',receivedAt:'09:16',category:'NO_REPLY',confidence:.99,risk:'low',priority:'normal',status:'rejected',originalBody:'이번 주 AI 제품 업데이트 뉴스레터입니다.\n주요 기능 업데이트와 산업 동향을 공유합니다. 이 메일은 자동 발송되었습니다.',draftBody:'',revision:1,runId:'ex-1039',flags:[],latestMessageId:'msg-104'},
  ],
  runs:[
    makeRun('ex-1042','다음 주 미팅 일정 확인 부탁드립니다','review','REPLY_REQUIRED','11:42:00'),
    makeRun('ex-1041','프로젝트 견적서 검토 및 의견 요청','review','REVIEW_REQUIRED','10:58:14'),
    makeRun('ex-1040','LLMOps 평가 데이터셋 공유드립니다','review','REPLY_REQUIRED','10:31:02'),
    makeRun('ex-1039','이번 주 AI 제품 업데이트','success','NO_REPLY','09:16:48'),
    makeRun('ex-1038','API 연동 범위 확인 요청','success','REPLY_REQUIRED','09:04:11'),
    failedRun(),
  ],
  experiments:[
    {id:'eval-028',name:'Gmail Reply · release validation',releaseId:'r0.2.1',dataset:'gmail-reply-holdout',datasetVersion:'v1.0 · 300 cases',evaluatorVersion:'eval.v1.2',count:300,status:'regression',metrics:[
      {key:'precision',label:'회신 분류 정밀도',baseline:.94,candidate:.93,threshold:.90},
      {key:'recall',label:'회신 분류 재현율',baseline:.90,candidate:.89,threshold:.85},
      {key:'risk',label:'위험 이관 재현율',baseline:.98,candidate:.98,threshold:.95},
      {key:'grounding',label:'초안 근거 충실도',baseline:.95,candidate:.84,threshold:.90},
      {key:'completeness',label:'초안 완결성',baseline:.91,candidate:.80,threshold:.85},
      {key:'tone',label:'초안 말투',baseline:.88,candidate:.76,threshold:.80},
      {key:'dispatch',label:'감독 위임 적합도',baseline:.97,candidate:.97,threshold:.95},
    ],failures:[
      {id:'case-087',subject:'미팅 참석 여부 확인',agent:'Draft',expected:'확정 전에는 확인 후 회신',actual:'참석이 확정된 표현 사용',score:.50},
      {id:'case-142',subject:'견적 조건 문의',agent:'Draft',expected:'제공된 조건만 인용',actual:'미확정 할인 조건 추가',score:.25},
      {id:'case-206',subject:'자료 검토 요청',agent:'Draft',expected:'두 가지 요청 모두 회신',actual:'검토 기한 답변 누락',score:.50},
    ]},
    {id:'eval-027',name:'Gmail Reply · baseline',releaseId:'r0.2.0',dataset:'gmail-reply-holdout',datasetVersion:'v1.0 · 300 cases',evaluatorVersion:'eval.v1.2',count:300,status:'passed',metrics:[],failures:[]},
  ],
  releases:[
    {id:'r0.2.1',version:'0.2.1',state:'candidate',decision:'IMPROVE_REQUIRED',createdAt:'2026.10.05 11:30',commit:'72d39e1',dataset:'holdout.v1.0',evaluator:'eval.v1.2',gates:[
      {id:'integrity',name:'Integrity',status:'PASS',evidence:'Registry 및 모든 agent 계약 검증 완료',threshold:'manifest 고정'},
      {id:'safety',name:'Safety',status:'PASS',evidence:'승인 우회 · 발송 · 비밀 유출 · 중복 0건',threshold:'위반 0'},
      {id:'evidence',name:'Evidence',status:'PASS',evidence:'Holdout 300건 · Staging 완료 248건',threshold:'300 / 200 이상'},
      {id:'quality',name:'Quality',status:'FAIL',evidence:'초안 품질 0.81 · baseline 대비 −8%p',threshold:'≥0.85 · 회귀 ≤3%p'},
      {id:'reliability',name:'Reliability',status:'PASS',evidence:'기술 성공 245 / 248 · 98.8%',threshold:'≥98%'},
      {id:'performance',name:'Performance / Cost',status:'PASS',evidence:'p95 24.6초 · 비용 baseline +8%',threshold:'≤30초 / +20%'},
      {id:'observability',name:'Observability',status:'PASS',evidence:'필수 이벤트 전송 대사 100% · 누락 0',threshold:'coverage 100%'},
      {id:'recovery',name:'Recovery',status:'PASS',evidence:'중단·재개 · 멱등성 · rollback 통과',threshold:'모든 테스트 통과'},
    ]},
    {id:'r0.2.0',version:'0.2.0',state:'baseline',decision:'READY_FOR_APPROVAL',createdAt:'2026.10.04 17:24',commit:'b38f1a7',dataset:'holdout.v1.0',evaluator:'eval.v1.2',gates:['Integrity','Safety','Evidence','Quality','Reliability','Performance / Cost','Observability','Recovery'].map((name,i)=>({id:'base-'+i,name,status:'PASS' as const,evidence:'기준 버전 검증 완료',threshold:'기준 충족'}))},
    {id:'r0.2.2',version:'0.2.2',state:'candidate',decision:'HOLD',createdAt:'2026.10.05 11:39',commit:'8a2cb34',dataset:'holdout.v1.0',evaluator:'eval.v1.2',gates:['Integrity','Safety','Evidence','Quality','Reliability','Performance / Cost','Observability','Recovery'].map((name,i)=>({id:'next-'+i,name,status:i===2||i===3||i===6?'UNKNOWN' as const:'PASS' as const,evidence:i===2?'Staging 완료 80 / 200건':i===3?'평가 진행 중':i===6?'Outbox 전송 대사 진행 중':'검증 완료',threshold:'증거 완결 필요'}))},
  ],
  health:[
    {id:'quality',label:'품질',status:'DEGRADED',value:'초안 품질 0.81',target:'≥0.85'},
    {id:'reliability',label:'안정성',status:'HEALTHY',value:'성공률 98.8%',target:'≥98%'},
    {id:'performance',label:'성능',status:'HEALTHY',value:'p95 24.6초',target:'≤30초'},
    {id:'cost',label:'비용·예산',status:'HEALTHY',value:'기준 대비 +8%',target:'≤+20%'},
    {id:'safety',label:'안전',status:'HEALTHY',value:'정책 위반 0',target:'0건'},
    {id:'observability',label:'관측 완전성',status:'HEALTHY',value:'이벤트 대사 100%',target:'100%'},
    {id:'dependencies',label:'의존성',status:'HEALTHY',value:'테스트 probe 정상',target:'모두 ready'},
  ],
  incidents:[{id:'inc-023',title:'Draft Agent 품질 회귀',severity:'warning',agent:'draft',cause:'후보 prompt draft@72d39e에서 근거 없는 확정 표현과 요청 누락이 증가했습니다. 프롬프트 변경이 원인 후보이며 추가 실험으로 확인이 필요합니다.',evidence:['eval-028: grounding 0.84 (−11%p)','case-087 · case-142 · case-206','prompt diff: draft@41a82c → draft@72d39e'],action:'이전 prompt와 후보를 같은 holdout에서 재평가하고, 사실 확정 금지와 요청 체크리스트를 보강하세요.',runId:'ex-1042'}],
  dependencies:[
    {id:'gmail',name:'Gmail Adapter',status:'ready',description:'테스트 계정 시나리오 · 읽기 / Draft-only',checkedAt:'11:42:12'},
    {id:'hermes',name:'Hermes Gateway',status:'ready',description:'허용 사용자 · 명령 / 알림 채널',checkedAt:'11:42:12'},
    {id:'langsmith',name:'LangSmith',status:'ready',description:'Trace / Eval / Observe · 합성 응답',checkedAt:'11:42:12'},
    {id:'checkpoint',name:'Checkpoint Store',status:'ready',description:'SQLite WAL · 체크포인트 시나리오',checkedAt:'11:42:12'},
  ],
});
