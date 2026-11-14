# 설계 v0.2 승인 검수 요약

기준일: 2026-10-05 · 1단계 사용자 승인 완료 / 2단계 목업 검수 대기

## 이번 변경

| v0.1 | v0.2 |
|---|---|
| 이메일 처리 단일 graph | Supervisor + Context/Triage/Risk/Draft/Critic subgraphs |
| 노드/LLM 중심 trace | gateway부터 release까지 전체 event 계약·내구성·누락 대사 |
| 분류 정확도와 기본 품질 평가 | 전문 agent·감독·전체 시스템·release별 score evaluator |
| 토큰/지연 기본 기록 | leaf usage, 병렬 active-time, 비용/queue/retry, 계측 상태 정의 |
| 실패 사례 수동 확인 | 차원별 HealthReport + Diagnose Agent + 근거/repro 연결 |
| 느슨한 출시 체크 | READY_FOR_APPROVAL / DEBUG_REQUIRED / IMPROVE_REQUIRED / HOLD |
| 미래 확장 언급 | Registry·TaskEnvelope·AgentResult·versioned manifest 계약 |

## 사용자 승인 대상

1. 감독 에이전트가 전문 에이전트를 관리하고, Runtime이 권한·예산·필수 단계를 검증하는 구조.
2. 새 agent/팀 Supervisor를 Registry와 동일 task/trace/eval 계약으로 확장하는 방식.
3. 모든 정의된 이벤트를 상세 추적하고 LangSmith를 실행·실험·관측의 중심으로 사용하는 LLMOps 운영 단위.
4. Eval 점수·Observe 지표·Diagnose 건강 상태로 release 결정을 만들고 사람이 승격을 승인하는 방식.
5. 초기 목표: reply precision 0.90, recall 0.85, draft quality 0.85, active-time p95 30초, 안전 위반 0.

## 검수 안내

- 제품 요구/수용 기준: [PRD](01-prd.md)
- 감독과 확장 계약: [아키텍처](02-architecture.md)
- 이벤트 스키마, 점수 계산, 지표 분모, 건강 진단, release 규칙: [LLMOps 상세](03-security-and-llmops.md)
- 승인용 시각화는 이 대화에 제공한다. 실제 측정 dashboard나 2단계 제품 화면 목업이 아니다.

## 진행 상태

- 설계·PRD v0.2 작성 완료 / 사용자 승인 완료
- Hermes의 정확한 제품·버전은 기존 가정 유지; 구현 전 확인
- provider/model, 개인정보 반출·보존, 비용 baseline, 계정/OAuth는 연동 단계 전에 확정
- 점수·예산·지연·표본수는 초기 제안값이며 아직 측정되지 않음
- 사용자 요청의 [cite: 1]에는 실제 참조 자료가 첨부되지 않아 그 내용을 추정하거나 인용하지 않음

명시적인 1단계 승인에 따라 2단계 화면 목업을 구현했다. 다음 검수는 [목업 검수 가이드](06-frontend-review.md)를 따른다. 목업 승인 전에는 3단계 연동을 시작하지 않는다.

## 산출물 검증

- 문서 내부 파일 링크와 JSON 이벤트 스키마 예시의 구문 검증 완료.
- 승인용 다이어그램 3개 관점의 렌더링, 가로 736/528/320px에서 텍스트 넘침·가로 스크롤 없음 확인.
- 6개 배포 판단 예시의 판정 변화와 agent 선택 설명 동작 확인; 브라우저 JavaScript 오류 0.
- 위 결과는 설계 산출물 검증이다. 실제 Gmail/LangGraph/LangSmith 기능이나 목표 지표를 검증한 결과가 아니다.
