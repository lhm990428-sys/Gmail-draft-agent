export type Scenario={id:string;title:string;group:string;decision:string;description:string;steps:{title:string;to:string;expected:string;detailTo?:string}[]};
function workspaceFor(path:string):string{
  if(path.startsWith('/reviews/'))return '/?mail='+path.split('/').at(-1);
  if(path.startsWith('/runs/ex-1037')||path.startsWith('/settings/'))return '/supervision?run=ex-1037';
  if(path.startsWith('/runs/'))return '/?run='+path.split('/').at(-1);
  if(path.startsWith('/agents/risk'))return '/?mail=m-102';
  if(path.startsWith('/evaluations/cases/'))return '/operations?release=r0.2.1&case='+path.split('/').at(-1);
  if(path.startsWith('/observe/'))return '/operations?release=r0.2.2';
  if(path.startsWith('/releases/'))return '/operations?release='+path.split('/').at(-1);
  if(path.startsWith('/diagnose/'))return '/operations?release=r0.2.1';
  return path;
}
export const scenarios:Scenario[]=[
  {id:'reply-review',title:'정상 회신 · 수정 후 승인',group:'메일',decision:'초안을 수정해 Gmail Draft로 저장할지 결정',description:'회신 필요 판단 → 원문 비교 → 수정 저장 → 승인 → 저장 결과/이력',steps:[{title:'메일 상세에서 원문·근거 확인',to:'/reviews/m-101',expected:'회신 필요 97%, 일정 확정은 사용자 확인'},{title:'수정 저장 후 승인',to:'/reviews/m-101',expected:'수정 중에는 승인 차단, 저장 후 revision 증가'},{title:'승인 이벤트 확인',to:'/runs/ex-1042',expected:'draft.edited / draft.saved, 실제 발송 없음'}]},
  {id:'risk-review',title:'위험 메일 · 사람 판단',group:'메일',decision:'계약·견적 초안을 수정·승인할지, 거절할지 결정',description:'민감 주제와 미처리 첨부파일이 있어 명시적인 사람 검토 필요',steps:[{title:'위험 근거 검토',to:'/reviews/m-102',expected:'계약·견적/첨부파일 경고를 초안과 함께 표시'},{title:'위험 agent 계약 확인',to:'/agents/risk',expected:'읽기/분류만 허용, 저장·발송 도구 없음'}]},
  {id:'stale-review',title:'새 메일 도착 · 승인 충돌',group:'메일',decision:'이전 초안 승인을 중단하고 최신 메시지를 다시 검토',description:'확인 모달에서 승인할 때 새 메시지 도착을 합성해 409를 반환',steps:[{title:'이전 초안 승인 시도',to:'/reviews/m-101',expected:'첫 승인 거부: 최신 메시지 변경 안내'},{title:'최신 데이터 조회 후 재검토',to:'/reviews/m-101',expected:'변경된 원문·revision·초안을 확인하고 새 승인'}]},
  {id:'draft-uncertain',title:'Draft 저장 결과 불확실 · 대사',group:'복구',decision:'재저장 대신 결과를 대사하여 중복을 방지',description:'저장 응답이 유실된 상태를 합성. 승인 재시도는 차단하고 결과 대사만 허용',steps:[{title:'초안 승인 후 응답 유실 확인',to:'/reviews/m-101',expected:'503 오류와 저장 결과 불확실 경고'},{title:'저장 결과 대사',to:'/reviews/m-101',expected:'같은 intent의 합성 Draft 확인, 중복 저장 없이 완료'},{title:'대사 이벤트 확인',to:'/runs/ex-1042',expected:'draft.reconciled, Draft ID와 저장된 내용 확인'}]},
  {id:'tool-timeout',title:'도구 장애 · 제한 재시도 종료',group:'복구',decision:'실패 원인을 확인하고 수동 재실행할지 결정',description:'Gmail read 3회 timeout → Debug 필요 → 합성 의존성 복구 후 새 실행 생성',steps:[{title:'실패 실행 상세',to:'/runs/ex-1037',expected:'tool.retry.exhausted, 쓰기 없는 실패 종료'},{title:'의존성 진단',to:'/settings/gmail',expected:'Gmail 연결 장애 시나리오, 자격증명 입력 없음'},{title:'승인 후 재실행',to:'/runs/ex-1037',expected:'새 run ID 생성, 원래 실패 이력은 보존'}]},
  {id:'quality-regression',title:'품질 회귀 · 배포보다 개선',group:'LLMOps',decision:'실패 근거를 확인하고 후보 릴리스를 보류/개선',description:'점수 미달 사례 → Draft prompt 비교 → 진단 → Quality gate FAIL',steps:[{title:'평가 실패 사례 상세',to:'/evaluations/cases/case-087',expected:'기대/후보/기준 결과와 채점 근거 비교'},{title:'진단 증거와 원인 가설',to:'/diagnose/inc-023',expected:'프롬프트 변경은 가설, 확정 원인이 아님'},{title:'릴리스 판정 상세',to:'/releases/r0.2.1',expected:'IMPROVE_REQUIRED, 승격 차단'}]},
  {id:'missing-events',title:'계측 누락 · 근거 부족',group:'LLMOps',decision:'미측정을 합격으로 처리하지 않고 대사 완료까지 보류',description:'이벤트 coverage 92% → Observability Unknown → Release Hold',steps:[{title:'관측 상세와 결측 확인',to:'/observe/draft',expected:'계측 불완전, 지표 신뢰도 경고'},{title:'릴리스 증거 상세',to:'/releases/r0.2.2',expected:'UNKNOWN 게이트와 증거 수집 항목, 승격 불가'}]},
  {id:'ready-release',title:'모든 게이트 통과 · 사람 승격',group:'LLMOps',decision:'고정 manifest를 검토한 뒤 Canary 승격 승인',description:'8개 게이트 PASS → manifest 확인 → 합성 Canary 승격 → 승인 결과',steps:[{title:'릴리스 상세 / manifest',to:'/releases/r0.2.0',expected:'READY_FOR_APPROVAL, 8/8 PASS'},{title:'승격 확인과 결과',to:'/releases/r0.2.0',expected:'사람 승인 후 promoted, 실제 배포 없음'}]},
  {id:'draft-saved',title:'저장 완료 · 결과 재확인',group:'결과',decision:'승인된 내용과 저장 결과가 일치하는지 검토',description:'검토 종료 뒤에도 원문, 초안 revision, Draft ID와 승인 이력을 확인',steps:[{title:'저장된 초안 상세',to:'/reviews/m-101',expected:'초안 저장 상태, 수정/재승인 차단'},{title:'승인 이력 확인',to:'/runs/ex-1042',expected:'사람 승인 및 Draft 저장 이벤트'}]},
  {id:'review-rejected',title:'거절 완료 · 외부 쓰기 없음',group:'결과',decision:'거절 이력과 외부 쓰기 없음 확인',description:'사람 거절 결과와 검토 종료 상태를 상세 화면에서 확인',steps:[{title:'거절된 메일 상세',to:'/reviews/m-101',expected:'검토 종료 상태, 승인 버튼 비활성'},{title:'거절 이력 확인',to:'/runs/ex-1042',expected:'review.rejected, 외부 쓰기 없음'}]},
].map(s=>({...s,steps:s.steps.map(step=>({...step,detailTo:step.to,to:workspaceFor(step.to)}))}));
