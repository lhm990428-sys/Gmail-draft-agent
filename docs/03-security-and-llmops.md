# 보안 및 LLMOps v0.2 — Trace / Eval / Observe / Diagnose / Release

문서 상태: v0.2 · 1단계 사용자 승인 완료  
기준일: 2026-10-05  
숫자는 벤치마크를 위한 승인된 초기 목표값이다. 실제 하네스 구현/측정/배포는 수행하지 않았다. 2단계 화면 목업의 숫자는 별도 합성 값이다.

## 1. 하나의 운영 단위

**LLMOps Control System = Event Capture + LangSmith Trace/Experiments/Feedback/Dashboards + Health Probes + Diagnose + Release Rule Engine + Evidence Store.**

하나의 `release_id`를 기준으로 어떤 agent/prompt/model/tool/policy가 실행됐는지, 어떤 이벤트가 발생했는지, 무엇을 얼마만큼 잘했는지, 현재 정상인지, 배포할 수 있는지를 조회한다. LangSmith를 전체 AI 실행·평가·관측의 중심으로 사용한다. 일반 API·승인·gateway·설정·배포 이벤트도 명시적으로 계측한다.

LangSmith의 기능을 대체할 별도 평가 플랫폼을 만들지 않는다. 로컬 Event Store는 이벤트 수집의 내구성·감사·오프라인 복구를 제공하고, Diagnosis/Release Rule Engine은 LangSmith 데이터와 probe 결과를 읽어 제품 정책에 맞는 결정을 내린다. 이 추가 모듈들은 별도 계측·테스트 대상이다.

| 구성 | 책임 | 저장/조회 |
|---|---|---|
| Event Capture | 모든 정의된 실행/운영 경계의 event·span 작성 | 로컬 append-only Event Store |
| Trace Project | root→supervisor→worker→LLM/tool trace | LangSmith dev/staging/prod |
| Dataset/Experiment | 버전된 inputs/reference와 run 결과 비교 | LangSmith datasets/experiments |
| Feedback | 코드/judge/사람 점수와 comment·evidence | LangSmith run feedback |
| Observe | latency/tokens/cost/errors/quality 시계열 | LangSmith + local metrics/probes |
| Diagnose | rule 기반 건강 점검 + agent 원인 가설 | HealthReport + incident trace |
| Release Gate | 고정 manifest의 gate 판정 | ReleaseDecision + 승인/승격 이벤트 |

계약/리전에 따라 제공되는 dashboard, alert, 자동화 기능이 달라질 수 있다. 3단계에서 사용 가능한 기능을 확인하고, 제품 gate와 probe는 SDK 데이터 집계를 통해서도 동작하도록 한다. 유료 기능 이용이나 새 외부 서비스를 본 설계 승인만으로 도입하지 않는다.

## 2. 전체 이벤트와 상세 이력

### 2.1 추적 범위

“모든 이벤트”는 본 시스템에 등록한 업무·운영 이벤트 계약의 **100% 수집 목표**를 뜻한다. 미계측 OS 작업이나 Gmail 내부 이벤트까지 자동 추적한다는 뜻이 아니다. 메일 내용 전체나 모델의 비공개 reasoning을 무조건 수집하지 않는다. 대신 공개된 계획·근거·행동·입출력 snapshot/diff·오류·평가·승인의 상세 이력을 정책 범위에서 보관한다.

| 영역 | 필수 이벤트 예시 | 이력 정보 |
|---|---|---|
| 접수/인증 | request.received, auth.allowed/denied, run.admitted/rejected | 주체·범위·검색식 해시·manifest |
| 업무 상태 | run.started/completed/failed/cancelled, state.transition | 이전/이후 상태, revision, 원인 event |
| 감독 | supervisor.plan, plan.validated/rejected, supervisor.decision | 계획 DAG·근거·결과 refs·budget |
| 위임 | task.queued/dispatched/joined, agent.started/completed/failed | agent@version, parent task, 의존성 |
| 모델 | llm.started/chunk/completed/failed | input/output refs, 모델/설정, usage, TTFT |
| 도구 | tool.requested/allowed/denied/started/completed/failed | redacted args/result, HTTP 상태, request ID |
| 복구 | retry.scheduled, task.timeout, checkpoint.saved/resumed | attempt, backoff, checkpoint ref |
| 검토 | review.requested/edited/approved/rejected/expired | 주체, 시간, diff, draft/recipient hash |
| 쓰기 | write.intent/confirmed/uncertain/reconciled | 멱등키, 외부 ID, 대사 결과 |
| 평가 | eval.scheduled/completed/failed, feedback.created | dataset/evaluator 버전, 점수, 근거 |
| 진단 | probe.result, diagnosis.created, incident.opened/resolved | window, 차원 상태, 증거·원인 후보 |
| 운영 | registry.changed, config.changed, release.gated/approved/deployed/rolled_back | 변경 전후 버전, 승인자, target 환경 |
| 계측 | telemetry.batch_failed/recovered, telemetry.gap_detected | outbox lag, 재전송, 누락 대상 |

streaming 사용 시 chunk sequence·시각·크기·hash를 수집한다. chunk 원문은 승인된 artifact 정책으로만 저장한다. 인프라/전송 상태는 별도 telemetry stream에서 batch 단위로 기록해 “전송 이벤트의 전송 이벤트”가 무한 생성되지 않게 한다.

### 2.2 공통 EventEnvelope

```json
{
  "schema_version": "event.v1",
  "event_id": "<uuid>",
  "event_type": "agent.completed",
  "occurred_at": "<UTC ISO-8601>",
  "ingested_at": "<UTC ISO-8601>",
  "execution_id": "<workflow execution>",
  "workflow_thread_id": "<workflow continuation>",
  "trace_id": "<LangSmith trace>",
  "span_id": "<LangSmith run>",
  "parent_span_id": "<parent run>",
  "task_id": "<task>",
  "parent_task_id": "<delegating task>",
  "attempt": 1,
  "sequence": 18,
  "causation_event_id": "<event that caused this>",
  "agent_id": "triage",
  "agent_version": "0.1.0",
  "release_id": "<manifest digest>",
  "environment": "staging",
  "actor_ref": "<pseudonymized actor>",
  "status": "success",
  "duration_ms": 1840,
  "input_ref": "<protected artifact>",
  "output_ref": "<protected artifact>",
  "change_ref": "<optional diff>",
  "usage": {
    "input_tokens": 1200,
    "output_tokens": 100,
    "cache_read_tokens": 0,
    "reasoning_tokens": null,
    "total_cost": null,
    "cost_currency": null,
    "source": "provider"
  },
  "error": null,
  "redaction_policy_version": "redact.v1"
}
```

위 JSON의 duration/usage 값은 스키마 설명용 예시다. LLM event에는 provider/model/settings/prompt commit/provider request ID를 추가하고, tool event에는 tool/version/resource scope를 추가한다. root와 자식 span 모두에 release/agent/model/prompt/policy metadata를 명시한다. 자동 상속을 가정하지 않는다. raw Gmail ID는 가명 참조와 암호화된 로컬 매핑으로 연결한다.

### 2.3 손실·전송·완전성

1. boundary event와 state/artifact reference를 가능한 동일 로컬 트랜잭션으로 저장한다. 외부 쓰기는 durable write.intent가 저장된 이후에만 시작한다.
2. Outbox가 LangSmith SDK를 통해 span/event/feedback를 전송한다. 인증 실패, 429, 네트워크 장애는 제한 재시도 및 backlog 알림으로 남긴다.
3. 전송은 at-least-once로 설계하고 event_id/안정된 span ID에 따른 dedup·재전송을 검증한다. 전달 확인과 서버 조회 대사 전에는 완전성을 선언하지 않는다.
4. 1개의 event가 항상 1개의 span일 필요는 없다. event→span/event projection mapping을 보관해 모든 필수 event가 연결되는지 검사한다.
5. instrumentation coverage는 사전에 정의한 경계 검사로, delivery coverage는 원장과 LangSmith mapping 대사로 각각 검증한다. 잘못 계측된 코드의 이벤트 개수만 맞다고 100%로 판정하지 않는다.
6. 시작 후 종료 없는 작업은 heartbeat·process restart·timeout으로 `incomplete` 또는 crash 추정 event를 추가한다. 알 수 없는 결과를 success로 바꾸지 않는다.
7. 필수 원장 저장 실패/overflow는 새 실행·Gmail 쓰기를 차단한다. LangSmith만 일시 장애일 때는 내구성 확보된 읽기·초안 생성은 허용하되 delivery gate 완료 전 운영 승격은 보류한다.
8. 원장 수정은 correction event로 이력을 남긴다. 민감 artifact 보존 만료/삭제는 tombstone event로 남기며 append-only를 영구 개인정보 보관 근거로 삼지 않는다.

운영자가 execution ID로 계획→위임→모델/도구→재시도→수정→승인→쓰기→평가→진단을 탐색할 수 있어야 한다. 승인 대기 뒤 새 trace segment도 같은 workflow thread에 연결한다.

## 3. Eval — 점수 기반 평가

### 3.1 평가 단위와 데이터

- agent 단위: Context 추출, Triage, Risk, Draft, Critic을 독립 입력으로 평가.
- supervisor 단위: agent 선택, 의존성, 충돌 처리, 재작업, 이관, 예산 준수.
- system 단위: 실제 graph 전체를 실행하고 결과와 trajectory를 평가.
- release 단위: 고정 manifest에 대한 baseline/candidate 실험, 안전 fault test, 운영 window 결합.

제안 holdout 300건: 명확한 회신 120, 회신 불필요 80, 모호한 요청 50, 악성/위험 50. 한국어/영어·긴 스레드·자동 알림·발신자 혼동을 층화한다. 민감 주제는 겹치는 별도 tag로 최소 60건 확보하고 위험 라우팅 점수를 따로 산출한다. 학습/프롬프트 개발 세트와 분리한다. 운영 실패는 사람의 비식별화·라벨 검수 후 dev regression set에 추가하며 잠긴 holdout에 자동 합치지 않는다.

대표 비결정 사례는 3회 반복하고 평균/분산과 최악 결과를 보고한다. 각 반복의 gate 충족 여부를 남기고 결과가 불안정하면 HOLD다. 실행 실패를 점수 계산에서 제외하지 않는다.

### 3.2 Feedback keys와 평가기

| Key / 대상 | 점수·평가 방식 | 제안 통과 기준 |
|---|---|---|
| context_fact_f1 / Context | 사람 reference facts 대비 precision/recall/F1; 근거 매핑 검사 | F1 ≥0.90 |
| triage_correct / Triage | label exact-match 0/1; 혼동행렬 summary | reply precision ≥0.90, recall ≥0.85 |
| risk_escalation / Risk | 위험 reference에 대해 REVIEW_REQUIRED 0/1 | 위험 recall ≥0.95 |
| dispatch_appropriate / Supervisor | 사람 reference의 허용 agent/DAG와 비교 0/1 | ≥0.95 |
| supervisor_control / Supervisor | 누락 필수 단계·순환·예산·scope 위반 코드 검사 0/1 | 1.00 |
| draft_grounding / Draft | 공개 사실을 evidence refs로 대조 + 독립 judge | ≥0.90 |
| draft_completeness / Draft | reference 요청별 충족 rubric | ≥0.85 |
| draft_tone / Draft | 언어/격식/서명 rubric | ≥0.80 |
| critic_detection_recall / Critic | 의도적으로 결함을 넣은 별도 세트 탐지율 | ≥0.90 |
| schema_valid / 전체 | schema·필수 필드 코드 검사 0/1 | 1.00 |
| policy_safe / 전체 | 승인 우회/Send/정보 노출/불허 tool 코드+fault test | 위반 0 |
| draft_quality / release | 0.50×grounding + 0.30×completeness + 0.20×tone | ≥0.85 |

주관 rubric은 0~4 등급을 0~1로 정규화한다. judge는 생성 agent와 구분해 evaluator prompt/model/version, score, 이유, 근거를 기록한다. 초기 50건을 사람이 교차평가하고 큰 불일치(정규화 차이 >0.25)는 annotation queue로 보낸다. judge timeout/형식 오류/미측정은 `null`과 평가 실패로 기록하고 0이나 1로 대체하지 않는다.

label이 REPLY_REQUIRED인데 REVIEW_REQUIRED로 abstain하면 자동 분류 recall에서는 FN으로 집계한다. 추가로 사람 이관을 포함한 처리 recall·review rate·abstention rate를 보고해 “다 검토로 보내기”가 높은 품질로 보이지 않게 한다. case별, agent별, release별 결과를 모두 남긴다. 지표별 n과 95% 신뢰구간을 제공하며 클래스 표본 부족 시 gate는 UNKNOWN이다.

### 3.3 LangSmith 연결

dataset version/split을 고정하고 SDK 평가 실험을 실행한다. code evaluator, 독립 LLM judge, summary evaluator 결과를 LangSmith experiment와 feedback에 기록한다. baseline과 candidate는 동일 입력·rubric·부하 조건에서 비교한다. 주요 점수의 악화가 3%p를 넘으면 회귀 gate 실패다. 안전 hard gate는 평균 점수로 상쇄할 수 없다.

online에서는 구조/권한 검사를 전수 평가하고 내용 judge는 허용된 비식별 데이터의 10%를 초기 샘플로 평가한다. 위험/오류 이벤트 자체는 샘플링하지 않는다. LangSmith에 원문을 보낼 수 없으면 로컬 승인된 evaluator가 필요한 내용을 읽고 점수와 마스킹된 증거만 LangSmith에 기록한다. 내용 평가가 불가능하면 평가 불가를 표시한다.

## 4. Observe — 운영 관측

| 지표 | 집계/정의 | 운영/출시 기준 제안 |
|---|---|---|
| input/output/cache/reasoning tokens | provider usage를 leaf LLM span에서만 합산 | unknown ratio 0; 없으면 N/A |
| total tokens / cost | supervisor+모든 worker+retry; Ops judge/diagnose 비용은 별도 및 총합 | 메일 20,000 token 상한; 평균 cost는 baseline +20% 이내 |
| first-token latency | streaming LLM의 첫 token 시각−호출 시작 | 비streaming은 N/A |
| model latency | model start→end; p50/p95/p99 | agent별 baseline 대비 +20% 경고 |
| preparation active-time | 접수→초안 준비, 사람 대기 제외, 병렬 wall-time 유지 | p95 ≤30초 |
| full cycle / human wait | 승인 대기와 저장 시간 분리 | 대기 24시간이면 stale review 표시; 자동 승인 없음 |
| queue/tool/retry latency | 대기·도구·backoff·attempt별 시간 | tool 실패 원인별 경고 |
| workflow success rate | 기술적 실패 없이 결과를 낸 완료/실패 실행 중 완료 비율 | ≥0.98 |
| write confirmed rate | 승인된 쓰기 요청 중 확인된 성공 비율 | ≥0.98, uncertain 0 |
| duplication / scope violation | duplicate 또는 정책 우회 횟수 | 0 |
| trace delivery coverage | 전송/대사 완료 필수 projections ÷ 필수 projections | release 대상 완료 batch 1.00 |
| outbox lag / lost events | 미확인 전송 age와 missing boundaries | lag p95 ≤60초, loss 0 |
| metadata completeness | 필수 버전/agent/task context가 있는 spans 비율 | 1.00 |
| quality feedback / edit ratio | score 분포, 거절, 원문→승인 초안 수정 정도 | 거절·급증은 Diagnose trigger |
| escalation/loop/budget | 재위임, reviewer 이관, 최대 턴 초과, 예산 중단 | 위임 제한 준수 1.00 |
| dependencies | read-only probe: token refresh, checkpoint, registry, SDK/API 상태 | 필수 dependency 모두 ready |

성공률에서 NO_REPLY와 정상 사람 거절은 성공 처리하며, 승인 대기 실행은 별도 집계하고 분모에 넣지 않는다. 취소도 사용자 취소/기술 중단을 구분한다. 자동 기술 중단은 실패로 포함한다. 비용 산정은 provider/model과 가격표 버전을 기록하고 unknown price는 미측정으로 둔다. parent span 집계와 leaf usage를 이중 합산하지 않는다.

ObserveWindow는 초기 기준 24시간 또는 최소 200 staging/shadow 완료 실행으로 제안한다. 시간·표본·traffic 종류를 함께 표시하며 무트래픽을 건강함으로 판정하지 않는다. 짧은 장애 감지는 5분/15분 window, release 품질 판단은 충분한 표본 window를 사용한다. 자체 probe는 secret 값을 출력하지 않는다.

LangSmith 기본 dashboard로 token/cost/latency/error/feedback을 보고, 모든 agent가 포함되도록 agent_id/release_id/environment를 필터·그룹으로 사용한다. top-N 기본 화면만으로 전체 agent coverage를 보장하지 않는다. p95·원장 누락·프로브 등 필요한 집계는 SDK/local metrics를 연결해 동일 운영 콘솔에 제공한다.

## 5. Diagnose — 건강 진단

### 5.1 상태와 책임

Rule Engine이 차원별 `HEALTHY / DEGRADED / UNHEALTHY / UNKNOWN`을 계산한다. Diagnose Agent는 고정된 결과와 evidence를 읽어 원인 후보, 영향 범위, 재현 방법, 권고 조치를 작성한다. 근거 없는 원인을 확정 진단으로 표현하지 않는다.

진단 차원: quality, reliability, performance, cost/budget, safety, observability, dependencies. 종합 점수로 안전/계측 실패를 숨기지 않는다. 모든 주요 차원이 healthy이고 증거가 충분할 때만 전체 HEALTHY다. hard violation이면 UNHEALTHY, 미측정 필수 항목이면 UNKNOWN, soft degradation이면 DEGRADED다.

| 차원 | HEALTHY | DEGRADED / UNHEALTHY | UNKNOWN |
|---|---|---|---|
| Quality | 모든 agent/system score와 회귀 기준 PASS | 점수 또는 회귀 기준 FAIL → DEGRADED | 필수 평가 실패·표본 부족 |
| Reliability | 성공률 ≥0.98, 미확정 쓰기·중단 실행 0 | 비율 미달 → DEGRADED; 미확정 쓰기·복원 결함 → UNHEALTHY | 실행 결과 대사 미완료 |
| Performance | preparation p95 ≤30초 | 초과 → DEGRADED | 완료 표본 부족 |
| Cost/Budget | 비용 기준과 작업 상한 충족 | 비용 미달 → DEGRADED; runtime 상한 통제 결함 → UNHEALTHY | usage/가격 정보 없음 |
| Safety | hard violation 0, 차단 통제 검증 | 미승인 쓰기·Send·secret 유출 → UNHEALTHY | 필수 safety test 미실행 |
| Observability | coverage/metadata 1.00, lag 기준 충족 | lag 초과 → DEGRADED; 확인된 누락·저장 결함 → UNHEALTHY | 서버 전송 대사 진행 중 |
| Dependencies | 인증·checkpoint·registry probe 모두 ready | 필수 probe 실패 → UNHEALTHY | probe 미실행 또는 만료 |

건강 상태의 종합 우선순위는 UNHEALTHY → UNKNOWN → DEGRADED → HEALTHY다. Release 판정은 별도의 gate 우선순위를 적용하며 건강 문구만으로 승격하지 않는다.

### 5.2 Trigger와 분류 예시

| 관측 | 진단 | 증거 | 권고 |
|---|---|---|---|
| Triage 점수 하락, 도구 정상 | QUALITY_REGRESSION | 실패 사례·label 비교·prompt diff | Triage prompt/model 개선 실험 |
| 응답 지연+특정 worker retry 급증 | LATENCY_DEGRADATION | 해당 agent span·429·queue/backoff | 병렬성/timeout/provider 설정 실험 |
| Gmail 401/403 | DEPENDENCY_AUTH_FAILURE | 마스킹된 HTTP 상태·refresh probe | OAuth 범위/만료 디버그 |
| 오래된 checkpoint / 실행 미종료 | STUCK_EXECUTION | task heartbeat·checkpoint·parent trace | 재개 경로 디버그 |
| 예상 위임 횟수 초과 | SUPERVISOR_LOOP | plan revisions·task DAG·budget | 감독 정책/프롬프트 개선 |
| 원장 대비 전송 누락 | OBSERVABILITY_GAP | outbox·event/span mapping | telemetry 복구; 승격 보류 |
| 미승인 write 실행 또는 금지 Send 호출 | SAFETY_VIOLATION | actor·intent·tool trace | 해당 write 기능 차단·디버그 |
| 미허용 행동 시도 후 Broker 차단 | POLICY_BLOCKED | policy denial·actor·intent | 정상 통제 증거; 반복 시 incident 조사 |
| 계측은 정상이나 표본 부족 | INSUFFICIENT_EVIDENCE | n, window, 미완료 Eval | 추가 staging/shadow; HOLD |

진단은 매 실행 finalize의 기본 체크, 짧은 집계 window, release candidate 평가 완료, 운영자 수동 요청에서 수행한다. 반복 incident는 원인 유형/agent/release로 묶고 resolution event와 수정 release를 연결한다. Diagnose 자체의 usage/latency/error도 관측한다. 일상 LLM 진단 호출은 중복 incident 억제와 일별 예산으로 제한한다.

### 5.3 HealthReport 계약

`report_id, release_id, registry_snapshot, window, sample_counts, dimension_statuses, violations[], suspected_causes[], confidence, trace_refs[], event_refs[], experiment_refs[], reproduction_ref, recommended_actions[], generated_at, rule_version, diagnosis_agent_version`.

UI에서 진단 문장 하나에서 관련 leaf trace·event·실험 사례로 이동할 수 있어야 한다. Diagnose Agent는 실제 코드/설정 변경, Gmail 행동, release 승격을 수행하지 않는다.

## 6. Release Gate — 배포·디버그·개선 판단

gate 각각은 `PASS / FAIL / UNKNOWN`과 value/threshold/evidence를 갖는다. 모든 gate가 같은 manifest/dataset/evaluator 및 관측 window를 가리켜야 한다.

| Gate | 통과 조건 |
|---|---|
| Integrity | manifest 잠금, 필수 계약 테스트, 등록 agent 모두 검증 |
| Safety | 승인 우회/Send/secret 유출/잘못된 수신자/duplicate 0 |
| Evidence | holdout ≥300, 위험 tag ≥60, staging/shadow ≥200, 반복 안정성 및 평가 완료 |
| Quality | 3.2 최소 점수 모두 통과, 주요 지표 회귀 ≤3%p |
| Reliability | 성공/확인된 write 성공 ≥0.98, auth/uncertain write/stuck 오류 해소 |
| Performance/Cost | preparation p95 ≤30초, 비용 baseline +20% 이내, 예산 준수 |
| Observability | 필수 이벤트 대사 1.00, 누락/메타데이터 미비 없음, 지연 기준 충족 |
| Recovery | dry-run replay, checkpoint resume, 중복 방지, rollback 검증 |

판정 우선순위:

1. 안전/기술/계측 결함 확인 → `DEBUG_REQUIRED` (운영 중 안전 위반은 즉시 해당 쓰기 경로 차단).
2. 위 결함이 없지만 필수 증거 UNKNOWN → `HOLD`.
3. 증거 충분 + 품질/성능/비용 gate FAIL → `IMPROVE_REQUIRED`.
4. 모두 PASS → `READY_FOR_APPROVAL`.

서로 다른 실패가 동시에 있으면 primary decision과 모든 secondary reason을 기록한다. 숫자 임계값은 versioned configuration이며 Supervisor/Diagnose가 자동 완화하지 않는다.

ReleaseDecision: decision_id, release_id, baseline_id, gate_results, health_report_id, reasons, evidence refs, rule_version, target_environment, approved_by, approval_time, deployment_result. 후보 판정과 운영자 승인은 분리된 상태다.

경로는 dev → staging → shadow(실제 메일 쓰기 없음) → 승인된 소규모 canary → 승인된 local production이다. canary는 제한된 라벨/최대 처리 건수와 Draft 쓰기만 허용한다. 승격은 서명된/해시 고정 manifest를 사용하고 새 실행에 적용한다. 진행 중 실행은 시작 manifest를 유지한다. rollback은 마지막 승인 manifest로 새 실행을 되돌리고 기록한다. 이미 생성한 Gmail Draft를 무조건 삭제하지 않는다.

## 7. 보안과 상세 데이터

### 7.1 권한 경계

- Supervisor/전문 agent는 Gmail OAuth token을 소유하지 않는다. Tool Broker만 자격증명을 읽고 역할·resource scope·승인 해시를 검증한다.
- 읽기는 `gmail.readonly`, Draft 저장은 필요한 `gmail.compose`를 검토한다. **gmail.compose는 Google 권한상 발송도 포함한다. “초안 전용 OAuth scope”가 있다고 가정하지 않는다.**
- 따라서 Broker에서 drafts.create/get/list 등의 허용 작업만 노출하고 messages.send/drafts.send 경로를 금지한다. agent에게 범용 HTTP/SDK credential 접근을 제공하지 않는다.
- Gmail과 LangSmith 자격증명·환경을 dev/staging/prod로 구분한다. 로컬 token은 OS secret store 또는 접근 통제된 암호화 저장소에서 관리한다.
- Gateway 기본 거부/허용 사용자, localhost API 인증, 사용자 CSRF/session/expiry 검증은 연동 단계에서 구현·검수한다.
- 메일 원문은 비신뢰 데이터이며 Registry/정책/툴/승인 지시를 바꿀 수 없다.

### 7.2 데이터 등급

| 등급 | 로컬 저장 | LangSmith |
|---|---|---|
| 시각·버전·status·usage·점수 | 전수 이벤트 | 전수 redacted trace/event |
| 계획/근거·tool args/result | 최소화·redaction; snapshot/diff | 비식별 범위만 |
| 이메일 본문/초안/수신자 | 승인된 암호화 artifact, ACL·보존 정책 | 기본 비반출; 합성/명시 승인된 비식별 본문만 |
| token/key/cookie/비공개 reasoning | 수집하지 않음 | 수집하지 않음 |

모든 nested span, error stack, judge input, callback, metadata에서 redaction 정책을 적용한다. 전체 이력은 “발생과 변경을 빠짐없이 추적”하는 뜻이며 비밀 원문을 복제하는 뜻이 아니다. 민감 원문 없는 재현은 synthetic fixture와 snapshot reference를 사용하고, 실제 원문 접근은 인가된 로컬 검토로 제한한다.

보존 제안: 민감 artifact 7일, 상세 이벤트 90일, release 승인/증거 metadata 1년. 조직 요구 및 LangSmith 계약의 실제 보존 가능 범위를 검토하고 3단계에서 확정한다. LangSmith dataset에 편입된 사례는 별도 삭제/보존 대상이며 trace 삭제만으로 처리됐다고 보지 않는다.

## 8. 6단계 시연과 검수 증거

| 시연 | 주입/조작 | 기대 관찰·결정 |
|---|---|---|
| 정상 supervised 실행 | 합성 회신 스레드 | Supervisor→worker 병렬/순차→Critic→승인; leaf까지 추적 |
| agent 확장 | fake Knowledge agent 등록/비활성화 | 동일 task/event/eval 계약; 불허 agent dispatch 거부 |
| score 회귀 | Triage/Draft prompt 악화 | experiment 하락, IMPROVE_REQUIRED |
| tool 장애 | Gmail 401/timeout fixture | attempt/error/probe 연결, DEBUG_REQUIRED |
| 감독 이상 | loop/예산 초과 fixture | runtime 상한·이관, supervisor 진단 |
| 추적 장애 | LangSmith 전송 실패 fixture | durable outbox, HOLD; 누락 결함 확인 시 DEBUG_REQUIRED |
| 건강한 후보 | 전체 gate PASS 증거 | READY_FOR_APPROVAL; 사람 승인 뒤 승격 event |
| 복구 | 승인 대기 restart / 쓰기 응답 유실 | stale 승인 차단, UNCERTAIN_WRITE 대사, duplicate 0 |

시연 자료에는 측정된 값·실험 ID·trace/event 링크·판정 JSON과 사람 검수 결과를 포함한다. 실제 secret/받은편지함 대신 테스트 계정과 합성 fixture로 시작한다.

## 9. 공식 근거

- [LangSmith Observability concepts](https://docs.langchain.com/langsmith/observability-concepts): nested runs, thread 연결, metadata/feedback와 수동 계측.
- [Custom instrumentation](https://docs.langchain.com/langsmith/annotate-code): 비LLM API/운영 경계도 명시적으로 trace 구성.
- [Log LLM calls](https://docs.langchain.com/langsmith/log-llm-trace): 모델 식별, usage_metadata, 비용·TTFT 계측 조건.
- [Evaluation types](https://docs.langchain.com/langsmith/evaluation-types): offline/online, code/judge/summary/composite 평가 방식.
- [Dashboards](https://docs.langchain.com/langsmith/dashboards), [Alerts](https://docs.langchain.com/langsmith/alerts): 지표 그룹·관측/알림 및 제공 환경 차이.
- [Gmail OAuth scopes](https://developers.google.com/workspace/gmail/api/auth/scopes): readonly/compose의 실제 권한 범위.

위 근거는 기반 기능의 지원 범위를 확인한 것이다. 본 문서의 수치, 수집 원장, 진단 규칙, 승인 gate는 제품 설계 제안이다.
