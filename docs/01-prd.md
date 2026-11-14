# PRD — Supervised Agent Platform / Gmail Reply Triage

후속 제안: [v0.3 자동 Gmail·최소 비용 실습 PRD](15-prd-v03-automatic-mail.md)는 별도 승인 대기다. 아래 v0.2 승인 기록을 대체 완료한 것은 아니다.

문서 상태: **v0.2 · 1단계 사용자 승인 완료**  
기준일: 2026-10-05  
승인 게이트: 설계·PRD 승인 → 목업 승인 → 연동 승인 → 구축 검수 → 기능 검증 → LLMOps 시연 검수

## 1. 제품 정의와 개정 이유

제품은 감독 에이전트가 전문 에이전트들을 관리하는 확장 가능한 로컬 에이전트 환경이다. 첫 업무는 Gmail 회신 필요 메일 분류와 회신 초안 생성이다. LangGraph는 감독·실행 하네스를 구성하고, LangSmith는 이벤트 추적·점수 평가·운영 관측을 제공한다. 이 데이터를 통합하는 LLMOps Control System이 건강 상태와 배포 가능 여부를 판단한다.

v0.1의 단일 그래프 설계를 감독 계층, 전문 에이전트 계층, 실행 통제 계층, LLMOps 계층으로 개정했다. LLMOps는 선택적 로그 부가기능이 아니라 업무 실행과 배포 의사결정의 필수 부분이다. 모든 숫자는 **설계 목표와 초기 제안값**이며, 측정 결과가 아니다.

## 2. 목표와 범위

1. Supervisor Agent가 계획, 위임, 결과 통합, 충돌 해결, 제한된 재작업, 사람 이관을 수행한다.
2. 전문 에이전트는 독립적인 프롬프트·모델·도구·상태·평가 계약을 갖는다.
3. 에이전트를 추가하거나 교체할 때 감독 프로토콜과 LLMOps 추적 계약을 재사용한다.
4. 회신 필요 여부를 `REPLY_REQUIRED`, `NO_REPLY`, `REVIEW_REQUIRED`로 분류하고 근거와 검토 가능한 초안을 만든다.
5. 시스템 경계 내 모든 업무·운영 이벤트를 상관 ID로 연결하고, 승인된 데이터 정책 범위에서 입출력과 변경 이력을 추적한다.
6. Eval 점수, Observe 지표, Diagnose 결과를 동일한 release ID에 연결해 배포·디버그·개선·보류 결정을 지원한다.

MVP에서는 자동 발송, 임의 외부 링크 방문, 첨부파일 실행, 스스로 권한을 확대하는 에이전트, 스스로 운영 배포를 승인하는 에이전트를 제공하지 않는다. 미래 Calendar/CRM/Knowledge 에이전트는 확장 인터페이스만 정의하고 구현 범위에 넣지 않는다.

## 3. 운영자 시나리오

1. 운영자가 Hermes Gateway 또는 로컬 콘솔에서 승인된 조회 범위의 실행을 요청한다.
2. Supervisor가 버전 고정된 Registry에서 사용 가능한 에이전트를 조회하고 Task Plan을 작성한다.
3. Runtime이 예산·도구 권한·의존성·건강 상태를 검증한 뒤 Context/Triage/Risk 에이전트를 실행한다.
4. Supervisor가 결과를 통합한다. 회신이 필요하면 Draft 에이전트, 이후 Critic 에이전트로 위임한다.
5. 불일치나 불확실성은 제한된 재작업 또는 사람 검토로 이관한다.
6. 사람이 초안을 검토하고 승인하면 Tool Broker가 Gmail Draft만 저장한다.
7. 실행 전체가 LangSmith trace와 이벤트 이력에 연결된다. 실행 재개, 승인 대기, 재시도도 별도 이벤트다.
8. LLMOps가 버전별 Eval·Observe를 집계하고 Diagnose Report와 Release Decision을 만든다.
9. 운영자는 근거 trace와 실패 사례를 확인하고 배포 승인 또는 디버그/개선 방향을 결정한다.

## 4. 에이전트 구성

| 역할 | 책임 | 결과/권한 |
|---|---|---|
| Supervisor | 계획·위임·취합·재작업·이관 | Task Plan, 구조화된 다음 행동; Gmail 자격증명 없음 |
| Context | 스레드 사실·질문·요청·근거 추출 | ContextReport; 해당 스레드 읽기만 |
| Triage | 회신 필요·우선순위·신뢰도 판단 | TriageReport; 외부 쓰기 없음 |
| Risk | 인젝션·민감 주제·위험 행동 판단 | RiskReport; 외부 쓰기 없음 |
| Draft | 근거에 맞춘 회신 작성 | DraftArtifact; Gmail 저장·발송 권한 없음 |
| Critic | 초안의 근거·완결성·말투 검토 | CritiqueReport와 수정 요청; 외부 쓰기 없음 |
| Diagnose | 운영 증거를 묶어 원인 후보·개선안 제시 | HealthReport; 메일/배포/설정 쓰기 없음 |

Gmail 수집·정규화·승인 검증·Draft 저장·배포 규칙은 결정론적인 서비스다. Runtime과 Policy Engine이 감독 에이전트의 결정을 검증한다.

## 5. 기능 요구사항

| ID | 요구사항 | 검수 증거 |
|---|---|---|
| FR-01 | Gmail 검색식·라벨·건수 제한 및 스레드 정규화 | 범위 밖 접근 차단 테스트 |
| FR-02 | Supervisor의 계획·위임·취합·이관 | 계획 버전과 delegation trace |
| FR-03 | Registry 기반 에이전트 등록·버전 고정·비활성화 | 가짜 신규 에이전트의 계약 테스트 |
| FR-04 | 역할별 컨텍스트·도구·예산·출력 스키마 격리 | 미허용 도구/잘못된 결과 거부 이벤트 |
| FR-05 | 독립 Triage/Risk 병렬 실행과 합류·충돌 처리 | 병렬 branch와 join 이력 |
| FR-06 | Draft→Critic→최대 2회 재작성→사람 검토 | 수정 diff, critique, 상한 도달 이관 |
| FR-07 | 승인 내용·스레드 최신성·멱등성 검증 후 Draft 저장 | 승인 해시, 저장 시도, 재실행 결과 |
| FR-08 | 전체 이벤트 수집·전송 재시도·누락 감지 | 이벤트 수 대사와 장애 복구 이력 |
| FR-09 | LangSmith에 root/agent/LLM/tool trace 및 공통 버전 metadata | 실행에서 leaf까지 탐색 가능 |
| FR-10 | 개별 에이전트·감독·전체 시스템 점수 평가 | 버전된 dataset, evaluator, experiment |
| FR-11 | 토큰·비용·지연·실패·예산·계측 품질 관측 | 에이전트별/전체/버전별 대시보드 |
| FR-12 | 건강 진단과 원인 증거·권고 조치 | HealthReport + trace/event links |
| FR-13 | 배포·디버그·개선·보류의 규칙 기반 판정 | ReleaseDecision + 모든 gate 상태 |
| FR-14 | dev/staging/prod 분리, 승인된 manifest 승격/복구 | 승인 이력과 release/rollback 이벤트 |
| FR-15 | Hermes 인증된 실행/상태/진단 요청·알림 | 사용자 allowlist 및 redaction 확인 |

## 6. 배포 가능 판정

판정 입력은 고정된 ReleaseManifest, EvalReport, ObserveWindow, HealthReport, EventCoverageReport다. 점수 평균 하나로 결론을 내리지 않는다.

- `READY_FOR_APPROVAL`: 안전·품질·성능·추적·복구 검증이 모두 통과. 운영자 승인 시에만 staging/canary/production으로 승격한다.
- `DEBUG_REQUIRED`: 인증·도구·체크포인트·중복·계측 결함이 발견됨. 구체적인 실패 trace와 재현 입력을 제공한다.
- `IMPROVE_REQUIRED`: 기능은 동작하지만 분류·회신·위임 점수 또는 성능/비용 목표가 미달. 에이전트별 개선 실험을 생성한다.
- `HOLD`: 표본 부족, 평가 미완료, 계측 누락, 데이터 반출 정책 미확정 등 근거 부족. 정상/합격으로 표시하지 않는다.

안전 위반은 가장 우선하며 운영 중이면 해당 기능 차단 및 수동 확인으로 이어진다. 상세 임계값, 지표 분모와 우선순위는 [LLMOps 사양](03-security-and-llmops.md)을 따른다.

## 7. 초기 수용 기준

| 영역 | 제안 기준 |
|---|---|
| 분류 | reply precision ≥0.90, recall ≥0.85; abstain/검토 이관 별도 집계 |
| 위험 라우팅 | 위험 세트에서 사람 검토 라우팅 recall ≥0.95 |
| 초안 | 가중 품질 점수 ≥0.85, grounding ≥0.90, 완결성 ≥0.85 |
| 감독 | 위임 적합도 ≥0.95, 예산/순환/권한 제한 준수 1.00 |
| 안전 | 미승인 쓰기, 발송 호출, 비밀 노출, 금지 에이전트 등록 0건 |
| 성능 | 초안 준비 active-time p95 ≤30초; 다중 에이전트 기준으로 기존 15초 목표 재설정 |
| 안정성 | 성공률 ≥0.98; duplicate draft 0건; 중단/재개 시 승인 정책 유지 |
| 이력 | 필수 이벤트 local capture 및 대사 coverage 1.00; trace metadata 계약 충족 |
| 출시 | 잠긴 평가 세트·baseline·manifest와 HealthReport가 같은 release에 연결됨 |
| 확장성 | 테스트용 신규 agent 등록 및 비활성화 시 core gate 변경 없이 실행/계측/평가 적용 |

최소 300개의 잠긴 오프라인 평가 사례와 200개의 staging/shadow 완료 사례를 초기 배포 증거로 제안한다. 안전 세트·위험 클래스·언어별 표본을 별도 확보한다. 표본수와 신뢰구간을 함께 보고하며 시험 통과를 현실의 무오류 보장으로 해석하지 않는다.

## 8. 설계 승인 항목과 미확정 사항

- 감독+전문 에이전트 구성 및 Registry 확장 계약
- 전체 이벤트 이력과 LangSmith 기반 Eval/Observe/Diagnose/Release 연결
- 점수·지연·예산·표본수의 초기 기준
- Draft-only 행동 통제와 사람 승인
- Hermes 제품/버전, LLM 공급자/모델, Gmail 계정 종류, LangSmith 리전·계약·보존·본문 반출 범위는 구축 전 확정

Gmail 플러그인 연결은 이 대화의 연결 상태이며 로컬 앱의 OAuth 자격증명 발급을 의미하지 않는다. 3단계에서 로컬 연동을 별도로 검수한다.

본 개정은 승인된 1단계 산출물이다. 사용자 승인에 따라 2단계 목업을 진행했으며, 목업 승인 전에는 3단계 Tool 연동을 시작하지 않는다.
