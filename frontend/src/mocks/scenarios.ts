import { createSnapshot } from './data';
import type { Snapshot } from '../domain';
import { scenarios } from '../scenario-catalog';

export function scenarioSnapshot(id:string):Snapshot|null{
  if(!scenarios.some(s=>s.id===id))return null;
  const state=createSnapshot();state.demoScenario=id;
  if(id==='tool-timeout'){
    state.dependencies[0].status='unknown';state.dependencies[0].description='합성 Gmail read timeout · probe 실패';
    state.health.find(h=>h.id==='dependencies')!.status='UNHEALTHY';
    const release=state.releases[0];release.decision='DEBUG_REQUIRED';release.gates.find(g=>g.id==='reliability')!.status='FAIL';release.gates.find(g=>g.id==='reliability')!.evidence='Gmail read probe 실패 · 3회 재시도 종료';
  }
  if(id==='missing-events'){
    state.metrics.coverage=.92;state.health.find(h=>h.id==='observability')!.status='UNKNOWN';state.health.find(h=>h.id==='observability')!.value='전송 대사 92% · 필수 이벤트 결측';
    state.runs[0].events=state.runs[0].events.filter(e=>e.sequence!==4);
    const release=state.releases[0];release.decision='HOLD';release.gates.find(g=>g.id==='observability')!.status='UNKNOWN';release.gates.find(g=>g.id==='observability')!.evidence='필수 이벤트 대사 92% · 누락 1개';
  }
  if(id==='draft-saved'||id==='review-rejected'){
    const saved=id==='draft-saved';state.mails[0].status=saved?'draft_saved':'rejected';const run=state.runs[0];run.status='success';run.spans.forEach(s=>{if(s.status==='waiting'){s.status='success';s.output=saved?'사람 승인 · 합성 Draft 저장':'사람 거절 · 외부 쓰기 없음';}});
    run.events.push({id:`${run.id}-result`,sequence:10,time:'합성 검토 시점',type:saved?'draft.saved':'review.rejected',actor:'human',detail:saved?'revision 1 · 합성 Draft 저장':'검토 거절 · 외부 쓰기 없음',status:'success',spanId:'sp-review'});
  }
  return state;
}
