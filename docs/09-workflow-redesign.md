# 목업 재설계 · 작업 흐름 중심

상태: 2026-10-29 개정 목업 구현·검증 완료 · 2026-11-01 사용자 승인 완료. 후속 3단계 셋업 현황은 [Tool 셋업·연동](10-tool-setup.md)을 따른다. 이 문서의 runtime과 화면 검증은 합성 목업에 대한 기록이다.

## 문제와 변경 계약

이전 버전은 기능 목록별 화면과 상세 링크를 추가했지만, 사용자는 메일 한 건과 릴리스 한 건을 처리할 때 화면 사이에서 맥락을 재구성해야 했다. Registry 도식도 실행 인스턴스의 태스크·상태·메모리를 표시하지 못했다. 이번에는 색/카드 교체가 아니라 정보구조와 상태 모델을 바꾼다.

1. **메일 작업실**: 목록 선택 → 수신/문맥/분류/위험/작성/검토의 단계 → 원문/근거/초안 → 승인/거절/대사와 결과를 같은 URL에서 처리한다. 단계와 실행 노드 선택 시 같은 화면의 상세 검사기가 바뀐다.
2. **LLMOps 판단실**: release 선택을 유지하며 Eval 점수·실패 사례, Observe 계측, Diagnose 가설/실험 계획, gate/manifest/승인을 한 작업 공간에서 확인한다. 사례 상세를 보기 위해 별도 페이지로 떠나지 않는다.
3. **에이전트 실행 감독**: 실제 실행 ID에 대응하는 typed node/edge, agent별 task ownership/dependency, 공개 상태/메모리 snapshot/delta, checkpoint, 이벤트 cursor를 그래프에 결합한다. 노드·엣지·task·event 선택과 재생/일시정지/단계 이동/시점 복원을 지원한다.

## 시각적 방향

새로운 브랜드를 만들지 않는다. 기존 토큰을 유지하되 수치 카드와 반복 패널은 축소한다. 메일은 inbox/list와 작업 면, LLMOps는 근거 비교표와 고정 결정 영역, 감독 화면은 canvas와 inspector/시간축의 도구형 구성을 사용한다. 영어 장식 제목·중복 설명·과도하게 작은 글자를 줄인다. 상태는 텍스트와 아이콘으로 함께 표시한다.

모바일에서는 목록/작업 영역을 세로로 바꾸고 그래프는 자체 pan/zoom을 유지한다. 표/코드/graph만 내부 스크롤을 사용한다. 각 작업의 입력·근거·결정은 다른 페이지로 이동하지 않아도 접근 가능해야 한다.

## 구현 경계

이 단계는 승인 전 목업이다. 합성 runtime event tape를 API로 가져와 reducer가 시점별 상태를 재구성한다. 타이머 재생은 실제 LangGraph/SSE 연결이 아니다. 화면에 이를 상시 표시한다. 실제 연동 시 동일 event schema를 SSE/WebSocket adapter로 공급하고 sequence gap·reconnect/replay·redaction을 검증한다. 사용자의 에이전트 내부 추론이나 비밀을 메모리로 노출하지 않는다. 보여주는 것은 허용된 task context, 구조화 결과, 공개 state/checkpoint뿐이다.

기존 상세 URL은 심층 점검용으로 유지하되 주 탐색은 작업 단위 세 공간과 검수 가이드로 축소한다. 기존 메일 승인·revision 충돌·불확실 저장 대사·release gate 규칙을 우회하지 않는다.

## 스킬 검색 결과

`find-skills`로 leaderboard 확인 후 `user flow`, `information architecture`를 검색했다. 추가 스킬은 설치하지 않았다.

- [information-architecture](https://skills.sh/julianoczkowski/designer-skills/information-architecture): CLI 5.9K installs, [저장소](https://github.com/julianoczkowski/designer-skills) 594 stars. 정확한 구조 설계 후보이나 제3자 출처다. `npx skills add julianoczkowski/designer-skills@information-architecture`
- [critique](https://skills.sh/pbakaus/impeccable/critique): 82.6K installs, 저장소 약 92.5K stars. 정보구조/사용성 검토 후보. audit에 Socket/Snyk Warn이 표시되어 검토 필요. `npx skills add pbakaus/impeccable@critique`
- [frontend-design](https://skills.sh/anthropics/skills/frontend-design): Anthropic 공식, 약 1.0M installs / 저장소 184.5K stars. 시각적 실행에는 적합하지만 이번 핵심인 업무 흐름·정보구조 설계를 대신하지는 않는다.

이번 작업은 사용자가 지정한 설치된 `anti-ui-slop`의 작업 중심 구조·필수 상태·실렌더 finish gate를 적용한다. UIZZE 공개 API는 두 번 접근에 실패해 실제 참고 이미지를 확보하지 못했다. 외부 화면을 관찰했다고 주장하지 않는다. 설치 수와 stars는 조회 시점 값이며 품질·보안을 보장하지 않는다.

## 완료 조건

- 메일 한 건의 수신부터 초안·승인·결과까지 주 작업 URL을 유지한다.
- 같은 release에서 점수→실패 사례→관측→가설→gate→결정을 연결하며 사례는 inline inspector에서 읽는다.
- 그래프 node/edge/task/event/memory가 같은 event cursor에서 갱신되고, 과거 시점에 미래 상태가 보이지 않는다.
- 정상·재작성·도구 실패·새 메시지 충돌·저장 결과 불확실·계측 부족·승격 허용/차단을 검증한다.
- desktop/mobile 렌더, 키보드, 선택·빈 값·오류/복구, reducer 정합성 및 기존 안전 회귀 시험을 수행한다.

사용자가 중단을 요청하면 현재 변경과 재개 지점을 저장하고 중단한다. 이 문서는 실제 시스템의 구현/관측 완료를 의미하지 않는다.

## 새 목업에서 검수할 순서

1. `/` 메일 작업실: 한 메일을 선택한 채 단계별 버튼으로 agent의 태스크·메모리·입출력을 확인한다. 기본은 compact 검사기이며 ‘그래프 펼치기’로 같은 화면에서 전체 관계를 본다. 원문/초안을 수정·저장·승인한 뒤 이력과 Draft ID를 같은 URL에서 확인한다.
2. 과정을 처음부터 재생한다. 과거 시점에는 미래 초안 승인 UI가 나타나지 않아야 한다. ‘최종 기록’으로 돌아오면 검토가 가능하다. 회신 불필요 분기는 Draft/Critic/승인을 생략한다.
3. `/operations`: r0.2.1을 고정하고 case-087을 클릭한다. 기대/기준/후보와 rubric을 inline으로 비교하고, 바로 아래 관측 창·가설·후속 실험과 옆 gate를 확인한다. r0.2.2는 근거 부족으로 차단, r0.2.0은 사람 확인 후 합성 Canary만 승격한다.
4. `/supervision`: 정상 / Critic 수정 요청 / 도구 timeout을 선택한다. 재생·일시정지·단계 이동·시점 슬라이더가 node/edge/task/memory/event를 함께 바꾸는지 확인한다. Triage와 Risk 동시 실행, Draft 재시도 횟수, 사람 승인 전 Broker 미실행을 본다.
5. Context 노드의 메모리 탭에서 snapshot/delta를 확인하고, 처음 시점으로 돌아가 메모리가 사라지는지 확인한다. 엣지 계약 목록 또는 SVG 엣지를 선택해 source/target·전달 계약·해당 시점의 payload를 확인한다. 메모리 엣지는 필터로 켠다.
6. `/scenarios`에서 충돌·불확실 저장·누락·복구 흐름을 준비한다. 기본 링크는 같은 작업실로 연결되며 필요한 경우에만 보조 상세 원장을 연다.

데이터와 그래프는 합성이다. 이 검수로 실제 OAuth, LangGraph 실행, LangSmith 전송, SSE, DB 내구성, 외부 Draft 저장 또는 운영 배포가 검증되는 것은 아니다.

## 시점·이력 정합성

`RuntimeJournal`은 합성 실행의 초기 입력/초안을 복제해 보관하고, 이후 사람 수정·승인·거절·불확실 저장·대사를 append-only action으로 추가한다. 최신 초안으로 과거 Draft agent 출력을 다시 생성하지 않는다. 과거 cursor에서는 당시까지의 공개 상태만 재구성한다. 시나리오 초기화/페이지 재로드 시 이 mock 원장은 초기화되며 실제 DB 내구성을 제공하지 않는다.

사람이 revision 2로 수정하면 Draft agent의 원래 revision 1 출력은 남고, Human 노드의 검토 입력에 수정본이 기록된다. 저장 응답 유실은 Broker의 `uncertain` 상태와 `outcome=unknown`으로 표시한다. 대사 후에는 Broker가 완료되어도 과거 시점으로 돌아가면 여전히 불확실 상태가 보여야 한다. 이 동작을 reducer/원장 단위 시험과 작업실 브라우저 흐름으로 검증한다.

재생의 `atMs`는 합성 event tape의 예시 논리 시각이다. 실제 실행 지연/토큰/비용 측정이 아니며, 타이머 재생 속도나 이 예시 시각을 LangGraph 성능 벤치마크로 해석하지 않는다.

가상 재작성 분기는 새로운 초안 revision을 요구하므로 기존 기록의 사람 승인을 재사용하지 않는다. 승인된 실행을 바탕으로 가상 분기를 보더라도 Human은 다시 대기하고 Broker는 미실행 상태로 유지된다. Checkpoint의 검토 revision은 재작성된 artifact와 일치해야 한다.

## 최종 검증 기록

- `npm run build`: TypeScript 검사와 production build 통과.
- `npm run test:e2e`: **37개 전체 통과**. 기본/상세 화면, 10개 시나리오, 통합 업무 흐름, runtime reducer, append-only 이력, 과거 메모리, 재시도/재작성, Broker 불확실·대사, gate 차단/승격을 검증했다.
- 이후 가상 재작성의 승인 재사용 금지와 checkpoint revision 경계를 보강하고 관련 **3개 단위 시험 통과**(기존 2개 + 신규 1개). 최종 시험 정의는 38개다.
- 기본 화면 4개 폭 ×9개(36), 상세/가이드 3개 폭 ×9개(27), 새 작업 공간 4개 폭 ×3개(12) = **75개 화면 캡처**. 새 공간은 1536/1280/390/320px, 페이지 가로 overflow와 해당 탐색의 uncaught JavaScript 오류 없음.
- 초기 전체 캡처 시험의 90초 시간 제한 초과는 화면 크기별 별도 시험으로 분리해 재검증했다. 숨겨진 재사용 heading을 포함하던 시험 선택자도 실제 접근성 heading을 확인하도록 수정했다. 실패를 통과로 간주하지 않고 다시 실행했다.
- 새 작업 공간 캡처는 `frontend/test-results/workspaces`, 전체 시험의 완료 표시는 `frontend/test-results/.last-run.json`, 마지막 단위 시험 결과는 `frontend/test-results-runtime-final/.last-run.json`에 있다. HTML report는 마지막 실행 결과(3개 단위 시험)로 덮어써진다.
- UI 스킬에 따라 실제 렌더를 보고 메일 작업실의 거대한 기본 그래프를 compact 검사기+펼치기로 변경했으며, 감독 canvas의 노드 겹침과 가독성을 조정했다. 숫자 카드 추가 대신 업무 객체와 결정 근거 중심으로 구성했다.

**승인 요청 범위는 이번 재설계 목업이다.** 실제 LLM/Gmail/Gateway/LangSmith/SSE 연결, 서버 인증, 실제 실험·성능·내구성·배포 검증은 아직 하지 않았다. 사용자 승인 없이 3단계 연동으로 넘어가지 않는다.
