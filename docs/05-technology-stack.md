# 기술스택 · 화면 계약

상태: 2단계 구현 기준 · 목업 검수 대기 / 2026-10-05

## 확정한 구현 스택

| 경계 | 기술 | 이유 / 연결 원칙 |
|---|---|---|
| 로컬 웹 콘솔 | Node.js 24 LTS, React 19, TypeScript, Vite 8 | 운영 콘솔 SPA, 배포 산출물은 정적 파일 |
| 탐색 / 서버 상태 | React Router 7, TanStack Query 5 | URL로 실행·사례 연결, 조회·변경·오류 상태 일관화 |
| UI | CSS 변수 기반 자체 디자인 시스템, Radix Dialog, Lucide | 모달 접근성, 의미 있는 아이콘; 외부 폰트 없이 시스템 한국어 폰트 |
| 시각화 | Recharts 3, React Flow 12 | 지표와 감독/전문 에이전트 토폴로지; SVG 기반 |
| DTO / 목업 | Zod 4, MSW 2 | 실제 HTTP 계약을 가로채는 합성 응답; 화면에서 mock 데이터 직접 접근하지 않음 |
| 프론트 검증 | TypeScript, Playwright | 빌드, 사용자 행동, 반응형 렌더 검증 |
| 백엔드 | Python 3.12, FastAPI, Pydantic 2, Uvicorn, uv | DTO 검증 REST API; 인증·비밀은 서버에서만 처리 |
| 하네스 | LangGraph Python, 버전된 agent registry / 정책 runtime | Supervisor + 전문 subgraph; interrupt, checkpoint, 제한 재작업 |
| LLM 연동 | LangChain provider adapter + 서버 model alias registry | supervisor/worker/writer/judge/diagnose 역할 분리, 모델 변경 시 UI 불변 |
| LLMOps | LangSmith Python SDK + 자체 Ops Aggregator / Gate Engine | trace·eval 원본과 local event ledger 대사; health와 배포 규칙은 결정론적 |
| 로컬 영속화 | SQLite WAL, SQLAlchemy 2, Alembic | event ledger / outbox / manifest / 승인 기록; LangGraph SQLite checkpoint 분리 |
| 확장 DB | PostgreSQL + LangGraph Postgres checkpoint | 다중 worker 전환 시 저장 adapter 교체, 화면 계약 유지 |
| Gmail | Google API Python Client + google-auth OAuth, 서버 Tool Broker | 읽기·Draft 저장만; send 메서드 차단; 사용자 승인과 최신성 검증 |
| Gateway | Hermes Gateway adapter, 서버 REST 명령 / 이벤트 인터페이스 | 콘솔과 gateway는 동일 application service 사용; gateway 제품 버전은 3단계 실측 |
| 실시간 상태 | REST + SSE (백엔드 단계) | Query cache 갱신; 실행·이벤트 cursor로 누락 복구 |
| 로컬 운영 | loopback 전용 서버, Windows PowerShell; Hermes 필요 시 WSL2 | 외부 공개 배포 없음, 서버 secret 저장소와 승인된 환경변수 |

프론트의 정확한 버전은 `frontend/package-lock.json`이 기준이다. 백엔드 패키지 버전은 3단계 호환성 시험 후 `uv.lock`으로 고정한다. 미검증 라이브러리 조합이나 Hermes 버전을 설치된 것처럼 표현하지 않는다.

LLM 공급자·구체 모델 ID, Hermes 제품/버전, OAuth 동의 화면, LangSmith 리전·데이터 반출 정책은 사용자 비용/보안 선택이 필요하므로 3단계 승인 항목이다. 기술 경계와 adapter는 확정했지만 이 값들을 임의 확정하지 않는다. 화면에는 실제 모델 ID를 받을 DTO가 있으므로 선택에 따른 UI 재작성은 필요 없다.

## 디자인 계약

후속 변경: UI Slop 및 분산된 사용 흐름 피드백에 따라 [작업 흐름 중심 재설계](09-workflow-redesign.md)가 화면 구성의 최신 기준이다. 기술스택은 유지한다. 아래 초기 디자인 계약은 이전 버전의 배경이다.

- 목적: 운영자가 메일을 검토하고, 에이전트의 품질·운영 증거를 확인해 배포 또는 개선을 결정한다.
- 구성: 왼쪽 고정 탐색, 상단 환경/목업 표시. 첫 화면은 승인 대기와 품질 이슈가 우선. 메일은 목록과 원문·편집 초안, 실행은 span과 이벤트를 함께 탐색한다.
- 색: 흰 작업면 / 저채도 회색 바탕 / 청색 선택·행동 / 녹색 통과 / 황갈색 검토·회귀 / 적색 오류. 색과 함께 상태 텍스트를 항상 표시한다.
- 타이포그래피: 시스템 한국어 sans, 지표는 tabular numerals, 기술 ID는 monospace. 짧은 모서리와 얇은 경계; 장식적인 gradient/hero 없음.
- 반응형: 좁은 화면은 탐색이 가로 스크롤, split pane은 세로로 쌓음. 표만 자체 가로 스크롤. 핵심 승인 버튼은 계속 접근 가능.
- 필수 상태: 로딩, 통신 오류/재시도, 검색 결과 없음, 선택, 저장 중, 저장 완료, revision 충돌, 승인/거절 확인, 품질 미달/증거 부족으로 승격 차단.
- 완료 기준: 9개 화면 탐색, 초안 수정/저장/승인/거절, trace→event와 Eval→Diagnose→Release 근거 연결, 승격 게이트 차단/허용, desktop/mobile 실렌더 검증.

## 개발로 이어지는 방식

동일 컴포넌트·CSS·라우트를 유지하고 `VITE_DATA_MODE=api`로 MSW만 끈다. `/api/v1` 프록시 대상에 백엔드를 연결한다. 승인·보안 검증은 서버에서도 재검증해야 하며 목업이 보안 구현의 증거는 아니다. 합성 데이터는 실제 품질 측정이나 연결 상태가 아니다.
