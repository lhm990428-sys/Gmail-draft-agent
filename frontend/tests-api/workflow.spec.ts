import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';

test('authenticated real API console: graph, edit, approval, ops, empty states and mobile',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const token=JSON.parse(readFileSync('../.local/browser-test-control.json','utf8')).token;
  await page.goto('/#console='+token);
  await expect(page.getByRole('heading',{name:'메일 작업실',exact:true})).toBeVisible();
  await expect(page).not.toHaveURL(/console=/);
  for(const [path,title] of [['/supervision','에이전트 실행 감독'],['/evaluations','점수 기반 평가'],['/agents','에이전트 Registry']]){
    await page.goto(path);await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  }
  await page.goto('/');await page.getByRole('button',{name:'테스트 실행',exact:true}).click();
  await expect(page.getByRole('heading',{name:'스터디 자료 수신 확인 요청',exact:true})).toBeVisible();
  await expect(page.getByLabel('회신 초안 편집')).toBeVisible({timeout:20000});
  await expect(page.getByText('실제 LangGraph 이벤트 원장',{exact:true})).toBeVisible();
  await page.getByLabel('회신 초안 편집').fill('검수자가 수정한 합성 테스트 초안입니다.');
  await page.getByRole('button',{name:'수정 저장',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'초안 수정본을 저장했습니다. Gmail에는 아직 저장하지 않았습니다.'})).toBeVisible();
  await page.getByRole('button',{name:'승인 · Draft 저장',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'승인 · Draft 저장',exact:true}).click();
  await expect(page.getByText(/로컬 테스트 Draft 저장 확인/)).toBeVisible();
  await expect(page.getByText(/로컬 테스트 Draft: local-draft-/)).toBeVisible();
  await page.goto('/supervision');await page.getByRole('button',{name:'메모리',exact:true}).click();
  await expect(page.getByText('허용된 공개 상태만 표시합니다.',{exact:false})).toBeVisible();
  mkdirSync('test-results-api/screens',{recursive:true});
  await page.screenshot({path:'test-results-api/screens/supervision-1440.png',fullPage:true});
  await page.goto('/operations');await expect(page.getByRole('heading',{name:'LLMOps 판단실',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'승인 · Canary 승격',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'개발 회귀 평가 · 합성 2건',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'개발용 합성 회귀 평가 완료 · holdout/배포 검증과 별도'})).toBeVisible({timeout:25000});
  await page.getByRole('button',{name:'건강 진단 갱신',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'운영 근거에 대한 가설 갱신 완료'})).toBeVisible({timeout:15000});
  await expect(page.getByRole('button',{name:'승인 · Canary 승격',exact:true})).toBeDisabled();
  await page.screenshot({path:'test-results-api/screens/operations-1440.png',fullPage:true});
  for(const path of ['/overview','/reviews','/runs','/agents','/evaluations','/observe','/diagnose','/releases','/settings']){
    await page.goto(path);await expect(page.locator('main h1').first()).toBeVisible();
  }
  for(const width of [390,320]){
    await page.setViewportSize({width,height:900});
    for(const [path,name] of [['/','mail'],['/supervision','supervision'],['/operations','operations']]){
      await page.goto(path);await expect(page.locator('main h1').first()).toBeVisible();
      const overflow=await page.evaluate(()=>Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=='absolute'&&getComputedStyle(e).position!=='fixed').slice(0,8).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right})));
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),JSON.stringify({width,path,overflow})).toBe(true);
      await page.screenshot({path:`test-results-api/screens/${name}-${width}.png`,fullPage:true});
    }
  }
  expect(errors).toEqual([]);
});
