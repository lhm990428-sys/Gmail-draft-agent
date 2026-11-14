# Hermes Agent Console

실제 구현에 재사용할 React / TypeScript 화면 목업입니다. 모든 데이터와 외부 동작은 합성입니다.

```powershell
npm ci
npm run dev
npm run build
npm run test:e2e
```

http://127.0.0.1:5173/ 에서 확인합니다. 서버는 loopback에만 노출됩니다.

상세 화면과 정상/실패/복구 검수는 http://127.0.0.1:5173/scenarios 에서 시작합니다. 시나리오 준비 시 현재 탭의 합성 변경만 초기화되며 실제 서비스는 변경하지 않습니다. 상세 URL 직접 접근, 브라우저 뒤로 가기, 목록 복귀를 지원합니다.

주 작업 공간은 `/` 메일 작업실, `/operations` LLMOps 판단실, `/supervision` 실행 감독입니다. 기존 기능별 화면은 보조 원장으로 유지합니다. 감독 화면은 최신 합성 기록을 먼저 표시하며 재생/정지/시점 복원으로 task·공개 메모리·node/edge를 함께 검사합니다. 실제 LangGraph/SSE가 아닙니다.

API 연결은 `.env.local`에 `VITE_DATA_MODE=api`를 설정하고 개발 서버를 재시작합니다. `/api`는 `127.0.0.1:8000`으로 proxy됩니다. 아직 백엔드는 없으므로 이 모드는 연결 오류를 표시합니다. 키·토큰·OAuth 비밀을 VITE 환경변수에 넣지 마세요.

- `src/domain.ts`: schema/type 계약
- `src/api.ts`: 실제 fetch adapter
- `src/mocks/`: MSW 합성 HTTP 응답
- `src/pages.tsx`, `src/components.tsx`: 재사용 화면
- `src/details.tsx`: 뎁스 2 상세 화면 8종
- `src/Workspaces.tsx`, `src/workspaces.css`: 메일·LLMOps 통합 작업 공간
- `src/RuntimeConsole.tsx`, `src/runtime.ts`: typed 실행 그래프와 이벤트→상태 reducer
- `src/mocks/runtime-data.ts`: 정상/재작성/도구 실패의 합성 이벤트
- `src/mocks/runtime-journal.ts`: 초기 기록을 보존하고 사람 수정/저장/대사를 append하는 세션 원장
- `src/scenarios.tsx`, `src/scenario-catalog.ts`: 10개 검수 시나리오와 브라우저 전용 검수 의견
- `src/tokens.css`, `src/styles.css`: 화면 토큰/반응형 규칙
- `tests/console.spec.ts`: UI/흐름 회귀 시험
- `tests/depth2.spec.ts`: 상세 레이아웃/연결/충돌/대사/복구/릴리스/검수 의견 시험
- `tests/workspaces.spec.ts`: 같은 URL의 업무 완료, release 맥락 유지, 과거 메모리 복원, 태스크/엣지와 오류 분기 시험

환경에 Chrome 경로가 다르면 `PLAYWRIGHT_CHROME_PATH`를 설정합니다. 테스트는 headless Chrome을 사용합니다. 합성 상태는 새로고침 시 초기화됩니다. 검수 절차와 범위는 `docs/06-frontend-review.md`를 참고하세요.
