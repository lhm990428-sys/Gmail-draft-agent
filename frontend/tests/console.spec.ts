import { test, expect } from '@playwright/test';
import { createSnapshot } from '../src/mocks/data';
import { SnapshotSchema } from '../src/domain';

for(const width of [1440,1024,390,320]){
test(`9 screens render at ${width}px without page overflow`,async({page})=>{
  test.setTimeout(90000);
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const screens=[['/','메일 작업실'],['/reviews','메일 검토'],['/runs','실행 이력'],['/agents','에이전트 Registry'],['/evaluations','점수 기반 평가'],['/observe','운영 관측'],['/diagnose','에이전트 건강 진단'],['/releases','릴리스 판단'],['/settings','환경과 연결']];
    await page.setViewportSize({width,height:1000});
    for(const [path,title] of screens){
      await page.goto(path);await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
      await page.screenshot({path:`test-results/screens/${width}-${path.replace('/','')||'overview'}.png`,fullPage:true});
    }
  expect(errors).toEqual([]);
});
}

test('fixture schema, token accounting, span/event correlation and no-reply branching are consistent',()=>{
  const data=SnapshotSchema.parse(createSnapshot());
  for(const run of data.runs){
    expect(run.tokens).toBe(run.spans.reduce((sum,s)=>sum+(s.inputTokens??0)+(s.outputTokens??0),0));
    for(const event of run.events)expect(run.spans.some(s=>s.id===event.spanId)).toBeTruthy();
    if(run.status==='success')expect(run.spans.every(s=>s.status==='success')).toBeTruthy();
    if(run.decision==='NO_REPLY')expect(run.spans.some(s=>s.agentId==='draft')).toBeFalsy();
  }
  expect(data.trend.reduce((sum,t)=>sum+t.tokens,0)).toBe(data.metrics.tokens);
  expect(data.trend.reduce((sum,t)=>sum+t.executions,0)).toBe(data.metrics.executions);
});

test('modal keyboard focus and observation selectors work',async({page})=>{
  await page.goto('/reviews?mail=m-101');
  await page.getByRole('button',{name:'승인 · Draft 저장',exact:true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toBeFocused();
  await page.goto('/observe');
  await page.getByRole('button',{name:'p95 지연',exact:true}).click();
  await expect(page.getByRole('img',{name:'p95 지연(초) · 합성 추이',exact:true})).toBeVisible();
  await page.getByLabel('관측 기간').selectOption('12');
  await expect(page.getByLabel('관측 기간')).toHaveValue('12');
});

test('edit draft, enforce saved revision, confirm approval, update event history',async({page})=>{
  await page.goto('/reviews?mail=m-101');
  const textarea=page.getByLabel('회신 초안 편집');await expect(textarea).toBeVisible();
  await textarea.fill('안녕하세요. 참석 여부를 확인한 후 회신드리겠습니다. 감사합니다.');
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'수정 저장',exact:true}).click();
  await expect(page.getByText('rev 2',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'승인 · Draft 저장',exact:true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'승인 · 합성 Draft 저장',exact:true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toBeDisabled();
  await page.getByRole('link',{name:'ex-1042 실행 근거'}).click();
  await expect(page.getByText('draft.saved',{exact:true})).toBeVisible();
});

test('reject and empty search are reachable',async({page})=>{
  await page.goto('/reviews?mail=m-103');
  await page.getByRole('button',{name:'거절',exact:true}).click();
  await page.getByRole('button',{name:'거절 확인',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('검토를 거절');
  await page.getByLabel('메일 검색').fill('없음-999');
  await expect(page.getByText('조건에 맞는 메일이 없습니다.',{exact:false})).toBeVisible();
});

test('release gates block fail/unknown and allow explicit human promotion',async({page})=>{
  await page.goto('/releases');
  const promote=page.getByRole('button',{name:'승인 · Canary 승격',exact:true});
  await expect(promote).toBeDisabled();
  await page.getByLabel('Release',{exact:true}).selectOption('r0.2.2');
  await expect(promote).toBeDisabled();
  await page.getByLabel('Release',{exact:true}).selectOption('r0.2.0');
  await expect(promote).toBeEnabled();await promote.click();
  await page.getByRole('button',{name:'승인 · 합성 Canary 승격',exact:true}).click();
  await expect(page.getByRole('button',{name:'승격 완료',exact:true})).toBeDisabled();
});

test('eval case, trace selection and new run work',async({page})=>{
  await page.goto('/evaluations');
  await page.getByRole('button',{name:'검토',exact:true}).first().click();
  await expect(page.getByRole('dialog')).toContainText('case-087');await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'테스트 실행',exact:true}).click();
  await expect(page).toHaveURL(/run=ex-1043/);
  await page.getByRole('button',{name:'sp-draft',exact:true}).click();
  await expect(page.getByRole('heading',{name:'출력 · 구조화 요약'})).toBeVisible();
  await expect(page.locator('.span-detail')).toContainText('draft');
});

test('synthetic error offers recovery; stale revision and unsafe promotion refused by HTTP mock',async({page})=>{
  await page.goto('/?scenario=error');
  await expect(page.getByRole('heading',{name:'운영 데이터를 불러오지 못했습니다'})).toBeVisible();
  await page.getByRole('button',{name:'다시 시도',exact:true}).click();
  await expect(page.getByRole('heading',{name:'메일 작업실',exact:true})).toBeVisible();
  const statuses=await page.evaluate(async()=>{
    const revision=await fetch('/api/v1/reviews/m-101/draft',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:99,body:'stale'})});
    const gate=await fetch('/api/v1/releases/r0.2.1/promote',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"target":"canary"}'});
    return [revision.status,gate.status];
  });
  expect(statuses).toEqual([409,409]);
});
