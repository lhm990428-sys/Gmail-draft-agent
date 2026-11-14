import { test, expect, type Page } from '@playwright/test';
import { scenarios } from '../src/scenario-catalog';
import { scenarioSnapshot } from '../src/mocks/scenarios';
import { SnapshotSchema } from '../src/domain';

async function startScenario(page:Page,id:string,advanced=true){
  await page.goto(`/scenarios?case=${id}`);
  await page.getByRole('button',{name:'이 시나리오 시작',exact:true}).click();
  await page.getByRole('button',{name:'초기화 후 시나리오 시작',exact:true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button',{name:'시나리오 다시 시작',exact:true})).toBeVisible();
  await page.getByRole('link',{name:advanced?'상세 원장으로 이동':'상세 화면으로 이동',exact:true}).first().click();
}
async function approve(page:Page){
  await page.getByRole('button',{name:'승인 · Draft 저장',exact:true}).click();
  await page.getByRole('button',{name:'승인 · 합성 Draft 저장',exact:true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
}

for(const width of [1440,390,320]){
test(`depth 2 pages and review workbench render at ${width}px`,async({page})=>{
  test.setTimeout(120000);
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const screens=[['scenarios','시나리오 검수'],['reviews/m-101','메일 검토 상세'],['runs/ex-1042','실행 상세'],['agents/draft','Draft 상세'],['evaluations/cases/case-087','평가 실패 사례 상세'],['observe/draft','Draft 관측 상세'],['diagnose/inc-023','진단 상세'],['releases/r0.2.1','릴리스 상세'],['settings/gmail','Gmail Adapter 연결 상세']];
    await page.setViewportSize({width,height:1000});
    for(const [path,title] of screens){
      await page.goto('/'+path);await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
      await expect(page.getByText('불러오는 중…',{exact:false})).toHaveCount(0);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
      if(width===1440&&path.startsWith('runs/'))expect((await page.locator('.trace-main').boundingBox())!.width).toBeGreaterThan(900);
      if(width===1440&&path.startsWith('reviews/'))expect((await page.locator('.review-workspace').boundingBox())!.width).toBeGreaterThan(900);
      await page.screenshot({path:`test-results/depth2/${width}-${path.replaceAll('/','-')}.png`,fullPage:true});
    }
  expect(errors).toEqual([]);
});
}

test('all ten scenarios provide valid fixtures and usable first detail links',async({page})=>{
  test.setTimeout(120000);
  for(const scenario of scenarios){
    expect(SnapshotSchema.safeParse(scenarioSnapshot(scenario.id)).success).toBeTruthy();
    await startScenario(page,scenario.id,false);
    await expect.poll(()=>{const url=new URL(page.url());return url.pathname+url.search;}).toBe(scenario.steps[0].to);
    await expect(page.getByRole('heading',{level:1})).toBeVisible();
    await expect(page.getByRole('heading',{name:'상세 항목을 찾을 수 없습니다'})).toHaveCount(0);
  }
});

test('depth 1 entry links open real depth 2 pages and browser back works',async({page})=>{
  await page.goto('/reviews');await page.getByRole('link',{name:'메일 상세 열기',exact:true}).click();
  await expect(page).toHaveURL(/\/reviews\/m-101$/);await expect(page.getByRole('heading',{name:'메일 검토 상세',exact:true})).toBeVisible();
  await page.goBack();await expect(page.getByRole('heading',{name:'메일 검토',exact:true})).toBeVisible();
  await page.goto('/agents');await page.getByRole('link',{name:'계약 상세',exact:true}).nth(4).click();
  await expect(page.getByRole('heading',{name:'Draft 상세',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'버전·평가',exact:true}).click();
  await expect(page.getByText('draft@41a82c → draft@72d39e',{exact:true})).toBeVisible();
});

test('normal depth 2 draft edit and approval shows immutable result and audit',async({page})=>{
  await startScenario(page,'reply-review');
  await page.getByLabel('회신 초안 편집').fill('변경된 안건을 확인했습니다. 참석 여부는 확인 후 회신드리겠습니다.');
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'수정 저장',exact:true}).click();await expect(page.getByText('rev 2',{exact:true})).toBeVisible();
  await approve(page);
  await expect(page.getByText('mock-draft-m-101',{exact:true})).toBeVisible();
  await expect(page.getByLabel('회신 초안 편집')).toBeDisabled();
  await expect(page.getByText('draft.edited',{exact:true})).toBeVisible();await expect(page.getByText('draft.saved',{exact:true})).toBeVisible();
});

test('stale thread refuses old approval and requires fresh review',async({page})=>{
  await startScenario(page,'stale-review');await approve(page);
  await expect(page.getByRole('alert')).toContainText('새 메시지가 도착');
  await expect(page.getByText('mock-draft-m-101',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'최신 데이터 조회',exact:true}).click();
  await expect(page.getByText('rev 2',{exact:true})).toBeVisible();
  await expect(page.locator('.original-body')).toContainText('오후 3시');
  await expect(page.getByLabel('회신 초안 편집')).toHaveValue(/오후 3시/);
  await approve(page);await expect(page.getByText('mock-draft-m-101',{exact:true})).toBeVisible();
});

test('uncertain write blocks editing/redecision and reconciles without duplicate',async({page})=>{
  await startScenario(page,'draft-uncertain');await approve(page);
  await expect(page.getByRole('alert')).toContainText('불확실');
  await expect(page.getByRole('button',{name:'승인 · Draft 저장',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'거절',exact:true})).toBeDisabled();
  const status=await page.evaluate(async()=>{
    const response=await fetch('/api/v1/reviews/m-101/draft',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:1,body:'should not save'})});return response.status;
  });expect(status).toBe(409);
  await page.getByRole('button',{name:'저장 결과 대사',exact:true}).click();
  await expect(page.getByText('mock-draft-m-101',{exact:true})).toBeVisible();
  await expect(page.getByText('draft.reconciled',{exact:true})).toBeVisible();
  await expect(page.getByText('draft.saved',{exact:true})).toHaveCount(0);
});

test('uncertain write stays correlated to original mail even after another run is added',async({page})=>{
  await startScenario(page,'draft-uncertain');
  await page.evaluate(()=>fetch('/api/v1/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:'label:agent-test',maxItems:1})}));
  await approve(page);
  await expect(page.getByText('draft.write.uncertain',{exact:true})).toBeVisible();
  const sourceIds=await page.evaluate(async()=>{
    const snapshot=await (await fetch('/api/v1/snapshot')).json();
    return snapshot.runs.filter((r:{events:{type:string}[]})=>r.events.some(e=>e.type==='draft.write.uncertain')).map((r:{id:string})=>r.id);
  });expect(sourceIds).toEqual(['ex-1042']);
});

test('manual retry uses a new run and retains original failure',async({page})=>{
  await startScenario(page,'tool-timeout');
  await expect(page.getByText('tool.retry.exhausted',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'수동 재실행 검토',exact:true}).click();
  await page.getByRole('button',{name:'승인 · 합성 재실행',exact:true}).click();
  await expect(page).toHaveURL(/\/runs\/ex-1043$/);
  await expect(page.getByText('사람 승인 재실행 · source ex-1037',{exact:true})).toBeVisible();
  await page.goBack();await expect(page.getByText('tool.retry.exhausted',{exact:true})).toBeVisible();
});

test('quality chain links case to diagnosis to blocked release; manifest resolves',async({page})=>{
  await startScenario(page,'quality-regression');
  await expect(page.getByRole('heading',{name:'Candidate draft@72d39e'})).toBeVisible();
  await page.getByRole('link',{name:'진단 증거',exact:true}).click();
  await expect(page.getByRole('heading',{name:'진단 상세',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'개선 실험 계획',exact:true}).click();
  await expect(page.getByRole('heading',{name:'재현 가능한 개선 실험 · 계획만 제공'})).toBeVisible();
  await page.getByRole('link',{name:'개선 필요 · 릴리스 상세',exact:true}).click();
  await expect(page.getByRole('button',{name:'승인 · Canary 승격',exact:true})).toBeDisabled();
  await expect(page.getByRole('heading',{name:'고정 ReleaseManifest'})).toBeVisible();
  await expect(page.getByText('gmail-supervised@1.0',{exact:true})).toBeVisible();
});

test('missing telemetry holds promotion and ready release allows explicit approval',async({page})=>{
  await startScenario(page,'missing-events');
  await expect(page.getByText('계측 불완전 · 이 지표만으로 정상/배포 가능을 판단할 수 없습니다.',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'배포 게이트',exact:true}).click();
  await expect(page.getByRole('heading',{name:'보류',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'승인 · Canary 승격',exact:true})).toBeDisabled();
  await startScenario(page,'ready-release');
  await page.getByRole('button',{name:'승인 · Canary 승격',exact:true}).click();
  await page.getByRole('button',{name:'승인 · 합성 Canary 승격',exact:true}).click();
  await expect(page.getByRole('button',{name:'승격 완료',exact:true})).toBeDisabled();
  await expect(page.getByText('사용자 확인 모달 승인 · 합성 Canary 반영',{exact:true})).toBeVisible();
});

test('review feedback persists separately; scenario reset is explicit and cancelable',async({page})=>{
  await page.goto('/scenarios?case=quality-regression');
  await page.getByLabel('화면·흐름에 대한 판단').selectOption('change');
  await page.getByLabel('검수 메모').fill('실패 근거를 먼저 보고 승격 차단을 확인하고 싶습니다.');
  await page.getByRole('button',{name:'검수 의견 저장',exact:true}).click();
  await page.reload();await expect(page.getByLabel('화면·흐름에 대한 판단')).toHaveValue('change');
  await expect(page.getByLabel('검수 메모')).toHaveValue(/실패 근거/);
  await page.getByRole('button',{name:'이 시나리오 시작',exact:true}).click();
  await page.getByRole('button',{name:'취소',exact:true}).click();
  await expect(page.getByRole('button',{name:'이 시나리오 시작',exact:true})).toBeVisible();
});

test('unknown detail IDs recover with a real list link',async({page})=>{
  for(const path of ['/reviews/missing','/runs/missing','/agents/missing','/evaluations/cases/missing','/observe/missing','/diagnose/missing','/releases/missing','/settings/missing']){
    await page.goto(path);await expect(page.getByRole('heading',{name:'상세 항목을 찾을 수 없습니다',exact:true})).toBeVisible();
    await expect(page.getByRole('link',{name:'목록으로 돌아가기',exact:true})).toBeVisible();
  }
});
