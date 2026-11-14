# 4단계 구축 작업 기록

**최신 증분 구현:** 사용자 지시로 화이트톤 유지·자동 Gmail 처리·실제 AI 검증을 수행했다. 누적 $1 예산 제안은 취소했다. [자동 Gmail 검수 안내](18-automatic-gmail-review.md)에 최신 동작과 48건 백엔드/새 자동 E2E/기존 API E2E 결과 및 실제 호출 비용을 기록했다. 아래는 기존 구축 시점의 이력이다.

상태: **로컬 구축본 검수 준비 · 2026-11-02**. 사용자 4단계 진행 승인에 따라 구현했다. 5단계와 6단계는 별도 검수·승인 전이다.

## 구현한 경계

- backend/src/mail_tools/app: 암호화된 SQLAlchemy SQLite store / 이벤트 hash chain+outbox / 명시적 LangGraph worker subgraph / 병렬 Triage·Risk / Supervisor 계획 검증 / Critic 재작성 상한 / human interrupt.
- broker: Gmail readonly 읽기 adapter, 별도 동의·정책으로 차단된 compose Draft adapter, 서명된 승인 snapshot, durable intent, uncertain write 대사. 발송 메서드 없음.
- server: loopback FastAPI, 1회 bootstrap, HttpOnly/SameSite 세션, origin/CSRF 검증, REST DTO, SSE global cursor.
- 프론트: 기존 화면 구조 유지, session gate / API headers / SSE query invalidation, 실제 runtime source 구분. API 빌드는 frontend/dist-api로 분리.
- 확장: AgentRegistry에 등록한 신규 worker와 하위 팀 감독이 같은 checkpoint/budget/event 계약으로 실행된다. schema·prompt·factory hash를 manifest에 고정한다. HTTP나 메일 입력으로 코드·도구 권한을 추가할 수 없다.
- LLMOps: 독립 evaluator, 잠긴 합성 JSON 평가셋 import, 점수·기준 버전·실패 사례, provider leaf token/latency, 7개 건강 차원, 근거 ID로 제한한 Diagnose 가설, 8개 release gate. LangSmith에는 metadata·점수·usage·hash만 보내고 상세 원문은 로컬에서 조회한다.
- 로컬 canary: 현재 코드·설정과 일치하고 8개 gate가 PASS인 manifest만 사람 승인으로 활성화 기록한다. 이전 승인 manifest hash를 검사하는 rollback 경로가 있다. 외부 운영 서버 배포 adapter는 아니다.

## 개발 검증 결과

- [x] API 화면·빈 상태·모바일 실렌더, API 상세의 고정 목업 문구 분리. 승인된 화면 구성 유지.
- [x] 업무 graph와 별도 evaluator 호출, 개발 회귀 점수, 진단, LangSmith native experiment 업로드/조회. 초기 실제 실험의 2개 row·5개 score 대사 확인.
- [x] 실제 Hermes 인증 command → LangGraph → 사람 검토 대기 → 상태 조회. Gateway에 Gmail/모델/LangSmith 키를 전달하지 않음.
- [x] Alembic 초기 migration, 암호화 artifact와 7일 보존·삭제/tombstone, runtime 소유권 잠금.
- [x] 실제 OpenAI 합성 메일 실행과 사람 검토 interrupt 확인. 예: `run-26beee75f1ed49ad932002d805f800a1`, 12회 호출, active 18,734ms, 원장 hash 정상. 단일 개발 실행이며 benchmark가 아님.
- [x] LangSmith 공개 동기 v2 클라이언트로 조회 경로 전환. SDK 비동기 generated transport 종료 문제와 span 갱신 parent/partition 누락을 수정. 중복 409는 실제 서버 종료 시각 확인 후에만 완료 처리.
- [x] 백엔드 **40건 통과**: 승인·재시작·불확실 쓰기·중복·원장 저장 실패·실행 중 대사 경쟁·하위 팀 확장·인증/CSRF·보존·평가셋·gate·로컬 canary/rollback·trace 종료 readback·backoff 큐 공정성·재실행 원본 보존·trace 생성 응답 유실 대사·감사 stream 추가 기록.
- [x] 실제 API 브라우저 E2E **1건 통과**: 빈 상태 → graph → 수정 → 승인·로컬 Draft → 공개 memory → 평가 → 진단 → 승격 차단. 1440/390/320px, JS 오류/가로 넘침 없음.
- [x] 기존 승인 목업 브라우저 회귀 **38건 통과**. 9개 화면·뎁스 2·정상/오류/복구·작업실/감독/판단실·모바일 포함.
- [x] API production 번들 빌드. desktop 감독/판단실과 320px 메일 화면 PNG 직접 확인.
- [x] 실행기와 [실제 앱 검수 안내](14-runtime-review.md), 실제 Gmail 동의·외부 배포 범위 명시.
- [x] 마지막 수정 재검증: release 소스·prompt·schema·lock 암호화 원문 보관과 manifest hash 대조, 평가 사례의 이전 실제 출력 baseline 포함. 백엔드 40건 통과를 확인했다. 중단 전 실행한 API E2E도 `frontend/test-results-api/.last-run.json`에 passed로 남았으며 마지막 기록 시각은 2026-11-02 09:07 KST다.
- [x] 추가 비용 없는 검수 설정 유지: scripted 모델, LangSmith 신규 전송 비활성, Gmail 외부 전송·Draft 쓰기 비활성. 실행 안내의 과거 유료 모드 설명을 현재 설정과 일치시켰다. 이번 재개에서는 외부 모델·LangSmith 호출을 하지 않았다.

실제 Gmail 본문을 모델로 보내는 정책은 기본 false다. 실제 Gmail Draft 쓰기도 기본 false이며 현재 OAuth는 readonly다. 사용자가 자리를 비운 동안 이 동의를 대신하지 않는다. 개발 검증은 합성 입력과 로컬 Draft adapter로 수행한다. Unknown 지표는 null/N/A, 운영 release는 증거 부족 시 HOLD다.

실제 독립 평가에서 완결성 0.78로 기준 0.85에 미달한 사례를 관찰했고, 후속 동일 prompt 평가에서 점수가 변했다. 이를 제품 개선으로 해석하지 않는다. 고정된 표본의 반복 평가가 필요하다. 개발용 2건은 정식 holdout·risk·shadow·안전/복구/capture 증거를 대신하지 않는다.

최종 실행/대사 metadata는 `.local/application/phase4-evidence.json`, 별도 연결 점검은 `.local/reports/`, 화면은 `frontend/test-results-api/screens/`에 보관한다. 키·OAuth token·실제 메일 본문을 보고서에 포함하지 않는다. 최신 대사 상태는 해당 JSON의 coverage와 pending 수를 확인한다.

다음은 사용자 4단계 검수다. 승인 후 5단계에서 실제 테스트 메일 범위와 compose 동의, 정식 평가셋/수용 기준·관측 창·복구 증거를 확정한다.

## 사용자 실행 중 발견한 문제와 수정

2026-11-02 `Open-Console.cmd` 실행 실패를 재현했다. 남은 프로젝트 Hermes 프로세스의 8642 포트 점유로 Windows 오류 10048이 발생했다. 프로젝트 실행 경로·명령·부모/자식 관계를 확인한 Gateway 트리만 종료한 후 실제 실행을 복구했다. 앱 8000 / Gateway 8642 / 콘솔 HTML은 HTTP 200이다. 일반 OSError 대신 포트 번호와 종료·재시도 방법을 안내하고 CMD에는 기다려도 재시작되지 않는다는 문구를 추가했다. 포트 충돌 회귀 테스트를 추가했으며 관련 테스트 10건 통과. 합성 응답·외부 전송 비활성 설정을 유지했다.
