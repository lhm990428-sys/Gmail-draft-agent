# Gmail Reply Triage Agent

Supervisor가 전문 에이전트를 계획·위임·검토하는 LangGraph 기반 로컬 에이전트 환경입니다. 첫 업무는 Gmail 회신 필요 분류와 초안 생성이며, LangSmith 중심 LLMOps가 전체 이벤트 이력·Eval·Observe·Diagnose·Release 판단을 연결합니다.

## 현재 단계

**2026-11-02 최신 변경:** 사용자 지시로 기존 화이트톤을 유지하고 자동 Gmail 처리 구현·검증을 진행했습니다. 블랙톤 목업과 누적 $1 예산 통제는 취소했습니다. [실제 Gmail 자동 처리 안내](docs/18-automatic-gmail-review.md)가 최신 기준입니다.

- [x] 1. 설계 및 PRD v0.2 — 사용자 승인 완료
- [x] 2. 화면 목업 — 작업 흐름 중심 재설계, 사용자 승인 완료 (2026-11-01)
- [x] 3. Tool 셋업 및 연동 — 연결 점검 후 사용자가 4단계 진행 승인 (2026-11-02)
- [ ] 4. 구축 — 실제 로컬 실행본 구현, 개발 검증 후 사용자 검수 대기
- [ ] 5. 기능 검증
- [ ] 6. LangSmith LLMOps 진단 시연

## 설계 문서

- [PRD](docs/01-prd.md)
- [아키텍처](docs/02-architecture.md)
- [보안 및 LLMOps](docs/03-security-and-llmops.md)
- [설계 승인 요약](docs/04-approval-review.md)
- [기술스택 및 디자인 계약](docs/05-technology-stack.md)
- [목업 검수 가이드](docs/06-frontend-review.md)
- [프론트엔드 API 계약](docs/07-api-contract.md)
- [뎁스 2 상세 화면·시나리오 검수](docs/08-depth2-scenarios.md)
- [작업 흐름 재설계](docs/09-workflow-redesign.md)
- [3단계 셋업·연동 현황](docs/10-tool-setup.md)
- [처음 하는 계정·키 발급 안내](docs/11-account-setup-guide.md)
- [실제 연결 점검 결과](docs/12-integration-check.md)
- [4단계 구축 기록](docs/13-build-progress.md)
- [실제 앱 실행·검수 안내](docs/14-runtime-review.md)

## 실제 앱 실행 (4단계)

**현재 사용자 승인: 실제 Gmail + 실제 OpenAI 자동 처리.** 최근 72시간 INBOX와 새 수신을 수집하며 비용 절약 profile(분류 1회, 필요 시 초안·Critic 각 1회)을 사용합니다. 누적 금액 상한은 없습니다. LangSmith 신규 전송은 사용자 요청으로 재개했습니다. Gmail 저장·발송은 계속 꺼져 있습니다. [사용·일시정지·검수 방법](docs/18-automatic-gmail-review.md)을 먼저 확인하세요.

프로젝트 폴더의 **`Open-Console.cmd`를 더블클릭**합니다. Hermes Gateway와 로컬 서버가 시작되면 인증된 브라우저가 열립니다. 약 1분까지 걸릴 수 있습니다. 화면 주소는 `http://127.0.0.1:8000/`이며, 처음 로그인하려면 실행기가 열어 준 탭을 사용합니다. 종료할 때 실행 창에서 `Ctrl+C`를 누릅니다.

메일 작업실 상단의 실제 Gmail 목록은 자동 갱신됩니다. 메일을 선택하거나 실행 버튼을 눌러야 처리되는 구조가 아닙니다. 일시정지는 화면 버튼으로 제어하고 종료는 실행 창 Ctrl+C를 사용합니다. 실제 provider 토큰·추정 비용을 로컬에서 관측하며 일일 호출 상한은 UTC 날짜별 100회입니다.

현재 Gmail 인증은 readonly입니다. 승인된 최근 수신 본문을 OpenAI로 전송해 처리하며, Gmail Draft 쓰기는 꺼져 있습니다. 실제 Gmail 메일의 검토 완료는 앱 안의 기록만 변경합니다. LangSmith의 기존 trace를 유지하고, 대기 기록과 새 이벤트를 metadata·usage·점수 중심으로 전송·서버 조회 대사합니다.

운영 판정은 현재 **HOLD**입니다. 개발용 합성 2건의 평가와 개발 테스트는 정식 holdout·shadow·복구 인증을 대신하지 않습니다. Canary 기능은 로컬 manifest 활성화 기록만 지원하며 외부 운영 서버에 코드를 배포하지 않습니다. [기능 범위와 검수 안내](docs/14-runtime-review.md)

## 목업 실행

```powershell
cd frontend
npm ci
npm run dev
```

브라우저에서 http://127.0.0.1:5173/ 를 엽니다. 현재는 합성 데이터이며 실제 Gmail/LLM/LangSmith 호출, Draft 저장, 배포는 하지 않습니다. 동작 상태는 브라우저 새로고침 시 초기화됩니다.

상세 화면·정상/실패/복구 흐름은 http://127.0.0.1:5173/scenarios 에서 검수할 수 있습니다. 시나리오별 검수 의견은 브라우저에만 저장되며 실제 메일/배포 승인이 아닙니다.

2026-10-29 재설계: 주 탐색을 **메일 작업실(`/`) / LLMOps 판단실(`/operations`) / 실행 감독(`/supervision`)**으로 통합했습니다. 메일과 릴리스 맥락을 유지하면서 근거·과정·결과를 확인합니다. 실행 감독은 합성 이벤트에 연결된 node/edge/task/public-memory 검사기이며 실제 LangGraph 연동이 아닙니다. 기존 상세 원장은 보조 탐색으로 유지합니다. [재설계 계약 및 검수 안내](docs/09-workflow-redesign.md)

`npm run build`는 TypeScript 검사와 production 번들 빌드, `npm run test:e2e`는 화면/사용자 흐름 검증입니다. 테스트는 기본적으로 Windows Chrome 경로를 사용하며 다른 환경에서는 `PLAYWRIGHT_CHROME_PATH`를 지정합니다.

## 기본 안전 원칙

각 단계 완료 후 사용자가 직접 검수합니다. 사용자의 4단계 진행 승인에 따라 실제 하네스·백엔드·프론트 연동을 구현했습니다. 5단계 정식 기능 검증과 6단계 LLMOps 진단 시연은 아직 사용자 승인 전입니다.

MVP는 사람 승인 후 Gmail Draft만 저장합니다. gmail.compose 권한에 발송이 포함되므로 Tool Broker에서 발송 경로를 차단하도록 설계합니다. Supervisor와 Diagnose는 권한/배포 승인을 스스로 변경할 수 없습니다.
