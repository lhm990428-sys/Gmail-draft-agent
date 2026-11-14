# Console API contract · v1

기준 DTO: `frontend/src/domain.ts`의 Zod schema. mock 구현: `frontend/src/mocks/browser.ts`. API adapter: `frontend/src/api.ts`. 경로와 JSON 필드는 향후 FastAPI/Pydantic에서도 동일하게 제공한다.

| Method / path | 입력 | 응답 | 실패 |
|---|---|---|---|
| GET `/api/v1/snapshot` | 승인된 workspace 범위 | SnapshotSchema | 401/403 인증·범위, 503 의존성 |
| PUT `/api/v1/reviews/{id}/draft` | `{revision, body}` | MailSchema, revision 증가 | 404 없음, 409 stale/종료, 400 빈 초안 |
| POST `/api/v1/reviews/{id}/decision` | `{revision, action: approve/reject}` | `{id,status,draftId}` | 409 stale/처리됨, 400 미허용 action/초안 없음 |
| POST `/api/v1/runs` | `{query,maxItems}` | `{id}` (201) | 400 미허용 범위, 429 예산/동시성 |
| POST `/api/v1/releases/{id}/promote` | `{target:canary}` | ReleaseSchema | 409 게이트 미통과/이미 승격, 403 승인 권한 |
| GET `/api/v1/evaluations/cases/{id}` | 사례 ID | CaseDetailSchema · 입력/reference/기준·후보/rubric | 404 사례 없음 |
| GET `/api/v1/releases/{id}/manifest` | release ID | ManifestSchema · graph/policy/가격표/agent 고정 버전 | 404 release 없음 |
| POST `/api/v1/reviews/{id}/reconcile` | 불확실한 저장 intent가 있는 검토 ID | DecisionResponseSchema | 409 대사 대상 없음/상태 변경 |
| POST `/api/v1/runs/{id}/retry` | 실패 run ID · 사람 확인 | 새 `{id}` (201) | 404 없음, 409 실패 상태 아님 |

mock 전용 `POST /api/v1/mock/scenario`는 `{id}`로 검수 preset을 준비하고 SnapshotSchema를 반환한다. API 모드에서는 frontend adapter가 거부한다. 실제 서버에 이 엔드포인트를 노출하지 않는다. Snapshot의 선택 필드 `demoScenario`도 목업 가이드 표시용이다.

## 통합 작업실 / 감독 그래프 추가 계약

- GET `/api/v1/runs/{id}/runtime?mode=normal|rework|timeout`: `runtime.v1` 합성 event tape. `nodes`(id/kind/taskId/scope/position), `edges`(data/delegation/memory/rework 및 payload contract), `tasks`(owner/dependsOn/goal), `events`(sequence/atMs/nodeId/status/input/output/public memory delta/checkpoint)를 제공한다. 현재 모드 분기는 목업 전용이다.
- GET `/api/v1/releases/{id}/evidence`: release ID를 고정한 experiment, 운영 관측 창, nullable metrics, 건강 판정·원인 가설·증거·다음 행동을 반환한다. 다른 버전의 운영 수치를 같은 릴리스에 섞지 않는다. 미완료 후보는 null/N/A와 Unknown/Hold를 유지한다.
- 현재 runtime은 REST로 합성 기록을 가져와 타이머로 재생한다. 실제 SSE 연결이나 실제 에이전트 메모리 조회가 아니다. `source=synthetic`을 UI에서 상시 표시한다.
- 향후 실제 event ingest는 run/release/task/agent/attempt correlation, event sequence 중복·gap·out-of-order, reconnect/cursor 재개, checkpoint hash/version, 공개 상태 redaction을 서버에서 검증해야 한다. 연결 실패/누락 시 정상·live로 표시하면 안 된다.
- runtime 메모리는 허용된 task context, 구조화 결과, 공개 state/checkpoint만 포함한다. 모델 내부 추론·API key·OAuth token을 노출하지 않는다. UI의 과거 시점 재생은 그 시점까지의 delta만 적용하며 미래 상태를 미리 보여 주지 않는다.
- mock `RuntimeJournal`은 초기 실행 자료를 복제하고 이후 사람/저장 action을 순서대로 추가한다. 원래 agent 출력은 사람 편집으로 덮어쓰지 않는다. Broker의 `uncertain`은 실패 확정이나 성공 확정이 아니라 저장 결과 대사가 필요한 상태다. 대사 후에도 과거 cursor의 상태는 uncertain으로 유지되어야 한다.

실제 대사는 재저장이 아니라 승인된 intent의 결과 확인이어야 한다. 실제 재실행은 parent run ID, actor, 권한·예산·의존성 재검증과 새 run ID를 기록해야 한다. 목업의 ‘의존성 복구 가정’을 실제 probe 성공으로 간주하지 않는다.

실패 응답: `{detail: string}`. missing metric은 null/N/A로 표현하고 성공·0으로 치환하지 않는다. Snapshot의 `schemaVersion`은 `console.v1`. ID는 화면에 노출 가능한 opaque 값이며 secret이나 메일 본문을 URL에 넣지 않는다.

실제 서버 필수 검증:

- loopback bind, origin allowlist, session/auth 및 CSRF 보호. VITE 변수에 비밀을 넣지 않음.
- 승인 요청의 actor, revision, draft hash, 최신 thread/message ID 재검증. 외부 draft 저장 intent와 결과는 영속화하고 불확실한 결과를 대사.
- Gmail send/drafts.send 경로는 Broker에서 차단. 사람 승인 없는 외부 쓰기 금지.
- release manifest 고정, 모든 gate PASS 및 충분한 관측 증거를 서버에서 재검증. API가 UI disabled 상태를 신뢰하지 않음.
- 생성된 run ID에서 registry/graph/prompt/model/가격표/dataset/evaluator/release 버전을 모두 연결.
- local event ledger + LangSmith trace correlation. 필수 이벤트 누락, 토큰 결측, outbox backlog를 health/release에 반영.
- SSE 재개 cursor와 조회 cache invalidation, 장기 실행 중 상태 갱신. 대량 이력은 서버 범위 제한/페이지 조회로 확장하되 현 화면 컴포넌트 유지.

mock은 브라우저 메모리 상태를 바꾸며 페이지 재로드 시 초기화된다. revision과 gate 거부는 HTTP handler에서도 수행하나 실제 OAuth, durability, 정확히 한 번 저장, 보안 및 배포의 구현 증거가 아니다.

참고: [LangSmith 평가 종류](https://docs.langchain.com/langsmith/evaluation-types)는 offline/online 및 code/judge/summary 평가를 설명한다. 본 제품의 건강 판정·출시 gate는 이 증거에 자체 정책을 적용하는 계층이며 LangSmith가 자동 배포 승인한다는 의미가 아니다.
