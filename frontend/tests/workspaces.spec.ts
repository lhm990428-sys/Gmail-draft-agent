import { test, expect } from '@playwright/test';
import { runtimeTape } from '../src/mocks/runtime-data';
import { createSnapshot } from '../src/mocks/data';
import { runtimeFrame, RuntimeTapeSchema } from '../src/runtime';
import { RuntimeJournal } from '../src/mocks/runtime-journal';

test('runtime event reducer preserves causality, memory history and typed graph references',()=>{
  const mail=createSnapshot().mails[0];
  for(const mode of ['normal','rework','timeout'] as const){
    const tape=RuntimeTapeSchema.parse(runtimeTape(mail,mode));const ids=new Set(tape.nodes.map(n=>n.id));
    expect(ids.size).toBe(tape.nodes.length);
    for(const edge of tape.edges){expect(ids.has(edge.source)).toBeTruthy();expect(ids.has(edge.target)).toBeTruthy();}
    tape.events.forEach((event,index)=>{expect(event.sequence).toBe(index+1);expect(ids.has(event.nodeId)).toBeTruthy();if(event.edgeId)expect(tape.edges.some(e=>e.id===event.edgeId)).toBeTruthy();});
    const empty=runtimeFrame(tape,0);expect(empty.events).toEqual([]);expect(empty.memory).toEqual({});expect(empty.checkpoint).toBeNull();
    if(mode!=='timeout'){
      const context=tape.events.find(e=>e.nodeId==='context'&&e.memory)!;
      expect(runtimeFrame(tape,context.sequence-1).memory.context).toBeUndefined();
      expect(runtimeFrame(tape,context.sequence).memory.context.requests).toBe(mail.preview);
      const riskStart=tape.events.find(e=>e.nodeId==='risk'&&e.status==='running')!;
      const parallel=runtimeFrame(tape,riskStart.sequence);expect(parallel.status.risk).toBe('running');expect(parallel.status.triage).toBe('running');expect(parallel.status.human).toBe('idle');
      const end=runtimeFrame(tape,tape.events.length);expect(end.status.human).toBe('waiting');expect(end.status.broker).toBe('idle');expect(end.checkpoint).toContain(mail.runId);
      expect(end.attempts.draft).toBe(mode==='rework'?2:1);
    }else{const end=runtimeFrame(tape,tape.events.length);expect(end.status.gateway).toBe('failed');expect(end.attempts.gateway).toBe(3);expect(end.status.draft).toBe('idle');}
  }
});

test('runtime journal appends human changes without overwriting earlier agent output',()=>{
  const mail=createSnapshot().mails[0];const original=mail.draftBody;const journal=new RuntimeJournal([mail]);
  const before=journal.read(mail,'normal');mail.draftBody='사람이 수정한 새 초안';mail.revision=2;
  journal.append(mail.runId,{nodeId:'human',status:'waiting',type:'draft.edited',summary:'사람 수정',input:mail.draftBody,memory:{reviewRevision:'2'}});
  const after=RuntimeTapeSchema.parse(journal.read(mail,'normal'));
  expect(after.events.slice(0,before.events.length)).toEqual(before.events);
  expect(runtimeFrame(after,before.events.length).output.draft).toBe(original);
  expect(runtimeFrame(after,before.events.length).input.human).toBe(original);
  expect(runtimeFrame(after,after.events.length).input.human).toBe('사람이 수정한 새 초안');
  journal.append(mail.runId,{nodeId:'broker',status:'uncertain',type:'draft.write.uncertain',summary:'응답 유실',memory:{outcome:'unknown'}});
  const uncertain=journal.read(mail,'normal');expect(runtimeFrame(uncertain,uncertain.events.length).status.broker).toBe('uncertain');
  journal.append(mail.runId,{nodeId:'broker',status:'done',type:'draft.reconciled',summary:'대사 완료',memory:{outcome:'confirmed'}});
  const final=journal.read(mail,'normal');expect(runtimeFrame(final,uncertain.events.length).memory.broker.outcome).toBe('unknown');expect(runtimeFrame(final,final.events.length).memory.broker.outcome).toBe('confirmed');
});

test('hypothetical rework cannot reuse recorded approval and checkpoint revision matches artifact',()=>{
  const mail=createSnapshot().mails[0];mail.status='draft_saved';const journal=new RuntimeJournal([mail]);
  journal.append(mail.runId,{nodeId:'human',status:'done',type:'review.approved',summary:'기존 승인'});
  const hypothetical=journal.read(mail,'rework');const frame=runtimeFrame(hypothetical,hypothetical.events.length);
  expect(frame.status.human).toBe('waiting');expect(frame.status.broker).toBe('idle');
  expect(frame.memory.checkpoint.draftRevision).toBe(frame.memory.draft.revision);
  const recorded=journal.read(mail,'normal');expect(runtimeFrame(recorded,recorded.events.length).memory.checkpoint.approval).toBe('approved');
});

for(const width of [1536,1280,390,320]){
test(`three workspaces render with stable composition at ${width}px`,async({page})=>{
  test.setTimeout(120000);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setViewportSize({width,height:1000});
    for(const [path,title] of [['/','메일 작업실'],['/operations','LLMOps 판단실'],['/supervision','에이전트 실행 감독']]){
      await page.goto(path);await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
      if(path==='/operations')await expect(page.getByRole('heading',{name:'Eval · 기준 버전과 비교',exact:true})).toBeVisible();
      else await expect(page.getByLabel('이벤트 시점',{exact:true})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
      await page.screenshot({path:`test-results/workspaces/${width}-${path==='/'?'mail':path.slice(1)}.png`,fullPage:true});
    }
  expect(errors).toEqual([]);
});
}

test('one mail workspace contains reception, graph/memory, draft editing and approval result',async({page})=>{
  await page.goto('/?mail=m-101');
  await expect(page.getByLabel('메일 처리 전 과정')).toBeVisible();
  await page.getByLabel('메일 처리 전 과정').getByRole('button').nth(1).click();
  const inspector=page.getByLabel('실행 검사기',{exact:true});
  await inspector.getByRole('button',{name:'메모리',exact:true}).click();
  await expect(inspector.getByText('requests',{exact:true})).toBeVisible();
  const draft=page.getByLabel('회신 초안 편집');await draft.fill('미팅 안건을 확인했습니다. 참석 여부를 확인한 뒤 회신드리겠습니다.');
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'수정 저장',exact:true}).click();
  await expect(page.getByText('rev 2',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'승인 · Draft 저장',exact:true}).click();
  await page.getByRole('button',{name:'승인 · 합성 Draft 저장',exact:true}).click();
  await expect(page.locator('.mail-result-line')).toContainText('mock-draft-m-101');
  await expect(page).toHaveURL(/\/?\?mail=m-101$/);await expect(draft).toBeDisabled();
});

test('runtime cursor rewinds memory, pauses timer, inspects edge payload and rework attempts',async({page})=>{
  await page.goto('/supervision');await expect(page.getByLabel('이벤트 시점',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'처음 시점',exact:true}).click();await expect(page.getByLabel('이벤트 시점',{exact:true})).toHaveValue('0');
  await page.getByLabel('Context 실행 노드',{exact:true}).click();
  const inspector=page.getByLabel('실행 검사기',{exact:true});await inspector.getByRole('button',{name:'메모리',exact:true}).click();
  await expect(inspector.getByText('현재 시점에 기록된 메모리 없음')).toBeVisible();
  await page.getByRole('button',{name:'과정 재생',exact:true}).click();
  await expect.poll(()=>page.getByLabel('이벤트 시점',{exact:true}).inputValue()).not.toBe('0');
  await page.getByRole('button',{name:'일시정지',exact:true}).click();const paused=await page.getByLabel('이벤트 시점',{exact:true}).inputValue();
  await page.waitForTimeout(900);await expect(page.getByLabel('이벤트 시점',{exact:true})).toHaveValue(paused);
  await page.getByRole('button',{name:'최종 기록',exact:false}).click();await expect(inspector.getByText('requests',{exact:true})).toBeVisible();
  await page.getByText('노드 간 엣지 계약 목록',{exact:false}).click();await page.getByRole('button').filter({hasText:'triage-draft'}).click();
  await expect(inspector).toContainText('TriageReport');await expect(inspector).toContainText('category / confidence / priority');
  await page.getByLabel('합성 분기',{exact:true}).selectOption('rework');await page.getByRole('button',{name:'최종 기록',exact:false}).click();
  await page.getByLabel('Draft 실행 노드',{exact:true}).click();await inspector.getByRole('button',{name:'태스크',exact:true}).click();
  await expect(inspector).toContainText('완료 · 2회');
  await page.getByLabel('합성 분기',{exact:true}).selectOption('timeout');await page.getByRole('button',{name:'최종 기록',exact:false}).click();
  await page.getByLabel('Gmail 수신 실행 노드',{exact:true}).click();await expect(inspector).toContainText('실패 · 3회');
});

test('replay historical time cannot approve a future draft in mail workspace',async({page})=>{
  await page.goto('/?mail=m-101');await expect(page.getByLabel('회신 초안 편집')).toBeVisible();
  await page.getByRole('button',{name:'처음 시점',exact:true}).click();
  await expect(page.getByLabel('회신 초안 편집')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'최종 기록',exact:false}).click();
  await expect(page.getByLabel('회신 초안 편집')).toBeVisible();
});

test('LLMOps retains release context for inline case, observability, diagnosis and gated promotion',async({page})=>{
  await page.goto('/operations?release=r0.2.1');
  await page.getByRole('button').filter({hasText:'case-087'}).click();
  await expect(page.getByLabel('실패 사례 비교')).toContainText('Candidate');
  await expect(page.getByRole('heading',{name:'Observe · 운영 창과 계측 신뢰도'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Diagnose · 관찰과 원인 가설'})).toBeVisible();
  await expect(page.getByRole('button',{name:'승인 · Canary 승격',exact:true})).toBeDisabled();
  await expect(page).toHaveURL(/\/operations\?release=r0.2.1$/);
  await page.getByLabel('판단실 릴리스').selectOption('r0.2.2');
  await expect(page.getByText('평가가 완결되지 않았습니다。',{exact:false})).toHaveCount(0);
  await expect(page.getByText('평가가 완결되지 않았습니다. 미측정을 통과로 취급하지 않습니다.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'승인 · Canary 승격',exact:true})).toBeDisabled();
  await page.getByLabel('판단실 릴리스').selectOption('r0.2.0');
  await expect(page.getByRole('button',{name:'승인 · Canary 승격',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'승인 · Canary 승격',exact:true}).click();await page.getByRole('button',{name:'승인 · 합성 Canary 승격',exact:true}).click();
  await expect(page.getByRole('button',{name:'승격 완료',exact:true})).toBeDisabled();
});

test('registry can inspect an agent outside the selected workflow without fabricating a node',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/agents');await expect(page.getByLabel('이벤트 시점',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'선택',exact:true}).last().click();
  await expect(page.getByRole('heading',{name:'Diagnose 계약',exact:true})).toBeVisible();
  await expect(page.getByLabel('Diagnose 실행 노드',{exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('mail workspace reflects uncertain Broker result and reconciliation without leaving the mail',async({page})=>{
  await page.goto('/scenarios?case=draft-uncertain');await page.getByRole('button',{name:'이 시나리오 시작',exact:true}).click();
  await page.getByRole('button',{name:'초기화 후 시나리오 시작',exact:true}).click();await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('link',{name:'상세 화면으로 이동',exact:true}).first().click();
  await page.getByRole('button',{name:'승인 · Draft 저장',exact:true}).click();await page.getByRole('button',{name:'승인 · 합성 Draft 저장',exact:true}).click();
  await expect(page.getByRole('button',{name:'저장 결과 대사',exact:true})).toBeVisible();
  const unknown=RuntimeTapeSchema.parse(await page.evaluate(()=>fetch('/api/v1/runs/ex-1042/runtime?mode=normal').then(r=>r.json())));
  expect(runtimeFrame(unknown,unknown.events.length).status.broker).toBe('uncertain');
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'저장 결과 대사',exact:true}).click();await expect(page.locator('.mail-result-line')).toContainText('mock-draft-m-101');
  const confirmed=RuntimeTapeSchema.parse(await page.evaluate(()=>fetch('/api/v1/runs/ex-1042/runtime?mode=normal').then(r=>r.json())));
  expect(runtimeFrame(confirmed,confirmed.events.length).status.broker).toBe('done');
  expect(runtimeFrame(confirmed,unknown.events.length).status.broker).toBe('uncertain');await expect(page).toHaveURL(/\/\?mail=m-101$/);
});
