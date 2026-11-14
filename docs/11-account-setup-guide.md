# 처음 하는 계정·API 키 발급

2026-11-01 사용자 선택: Nous Research Hermes Agent, OpenAI GPT-5.4 mini, LangSmith US. 이 문서는 3단계 계정 설정 안내다. 실제 메일을 모델/LangSmith로 전송하는 승인은 포함하지 않는다.

## 1. OpenAI API

1. [OpenAI Platform](https://platform.openai.com/)에 로그인한다.
2. 프로젝트 선택 메뉴에서 실습용 프로젝트를 만든다. 예: `hermes-mail-study`.
3. Billing에서 API 사용 가능 상태와 결제/크레딧을 확인한다. 구매·충전은 본인이 금액을 확인하고 진행한다. 현재 구독 혜택이나 무료 크레딧은 계정 화면에서 확인하며, ChatGPT에 로그인된 것만으로 이 앱의 API 인증이 완료되는 것은 아니다.
4. 프로젝트의 API Keys에서 새 키를 만든다. 관리자용 Admin API Key가 아닌 애플리케이션용 프로젝트 키를 사용한다. 제한 권한을 선택했다면 Responses 요청 권한이 필요하다.
5. 키를 채팅, 노션, 코드, `VITE_` 변수에 붙이지 않는다. 본인 PowerShell에서 아래 숨김 입력으로 저장한다.

```powershell
# 이 프로젝트 루트 폴더에서 실행
.\tools\tool.ps1 secret-set openai-api-key
```

입력 중 글자가 보이지 않는 것이 정상이다. 붙여 넣은 뒤 Enter를 누른다. `stored`가 나오면 Windows 자격 증명 관리자에 저장된 것이다. PowerShell이 스크립트 실행을 차단하면 시스템 정책을 바꾸지 않고 다음처럼 직접 실행할 수 있다.

```powershell
.\backend\.venv\Scripts\python.exe -m mail_tools.cli secret-set openai-api-key
```

현재 연결 점검은 고정 합성 문장 1회, 최대 출력 64토큰, 자동 재시도 없음, `store=False`다. 사용량에 따른 비용이 발생한다. GPT-5.4 mini 공식 표시 단가는 입력 $0.75 / 출력 $4.50, 각각 100만 텍스트 토큰 기준이다. 계정의 실제 가격·접근 가능 여부는 실행 시점에 다시 확인한다. `store=False`는 모든 공급자 보존이 없다는 보장이 아니다. 대량 평가·실제 메일 처리는 이 점검에 포함하지 않는다.

프로젝트 사용량 알림과 예산 설정도 확인한다. 알림을 결제 차단 한도로 가정하지 않는다. 앱의 호출/토큰 예산과 실제 비용 gate는 4단계 구축 대상이다.

## 2. LangSmith US

1. [LangSmith US](https://smith.langchain.com/)에 가입한다. 이미 다른 리전의 계정이 있다면 그 사실을 먼저 알린다.
2. 실습용 개인 조직·워크스페이스를 사용한다. 유료 업그레이드나 스터디원 초대는 필수 단계가 아니다.
3. Settings → API Keys에서 키를 발급한다. 개인 실습은 PAT도 가능하다. 워크스페이스 범위 서비스 키를 사용할 수 있다면 필요한 워크스페이스로 제한한다.
4. **Tracing key만으로는 조회·평가 작업이 제한된다.** 이번 점검은 합성 trace 작성 → 서버에서 조회 → 점수 feedback 작성 → feedback 조회까지 하므로 읽기/쓰기 가능한 키를 사용한다. 운영 키·수집 전용 키 분리는 후속 구축에서 검토한다.
5. 워크스페이스가 여러 개거나 키에서 요구하면 Settings의 workspace UUID를 `config/local.toml`의 `langsmith_workspace_id`에 넣는다. 이름 대신 UUID를 사용한다. 키는 이 파일에 쓰지 않는다.
6. 다음 명령으로 키를 저장한다.

```powershell
.\tools\tool.ps1 secret-set langsmith-api-key
```

연결 점검의 project 이름은 `hermes-mail-dev-setup`이다. 키를 저장했다고 trace가 자동 전송되지는 않는다. 점검 실행 시에만 합성 trace와 `setup_connectivity=1` feedback을 기록한다. 이 점수는 연결 성공 여부이며 에이전트 품질 점수가 아니다. 입력·출력은 빈 객체, metadata는 고정된 합성/버전 정보만 보낸다. real-mail 데이터셋은 만들지 않는다. 유료 기능 이용 가능 여부, 사용량·보존 정책은 계정에서 별도 확인해야 한다.

## 3. Gmail 테스트 계정과 Google Cloud

기존 ChatGPT Gmail 연결은 이 로컬 앱의 OAuth 인증이 아니다. 토큰을 내보내거나 재사용하지 않는다. 실습에는 업무용 받은편지함 대신 테스트 Gmail 계정을 권장한다.

1. [Google Cloud Console](https://console.cloud.google.com/)에서 본인이 관리하는 실습 프로젝트를 생성/선택한다.
2. APIs & Services → Library에서 **Gmail API**를 활성화한다.
3. Google Auth Platform의 Branding/Audience/Data Access(화면에 따라 OAuth consent screen)에서 앱 정보를 설정한다. 개인 Gmail 실습은 보통 External/Testing으로 시작하고 사용할 테스트 계정을 Test users에 추가한다. Workspace 조직 정책으로 제한되면 관리자 확인이 필요하다.
4. 이 단계의 권한은 `https://www.googleapis.com/auth/gmail.readonly`만 사용한다. `gmail.modify`, 전체 Gmail, compose/send를 추가하지 않는다.
5. Clients 또는 Credentials → Create OAuth client ID → **Desktop app**을 선택한다. Web application, service account JSON과 다르다.
6. 클라이언트 JSON을 내려받아 본인 로컬의 안전한 위치에 보관한다. 노션·채팅에 첨부하지 않는다. 프로젝트에 복사할 필요는 없으며 JSON의 절대 경로만 아래 명령에 전달한다. JSON 자체를 출력하지 않는다.

```powershell
.\tools\tool.ps1 gmail-auth --client-config "C:\실제\다운로드\client_secret_....json" --test-account
```

브라우저에서 **테스트 Gmail 계정**인지 확인하고 앱·권한을 검토한 후 동의한다. Google이 앱을 차단하면 Test users/앱 설정/조직 정책을 확인한다. 경고를 무조건 우회하지 않는다. 인증 callback은 일회성 `127.0.0.1` 임의 포트이고 대기 한도는 180초다. refresh token을 포함한 인증 정보는 Windows 자격 증명 관리자에 저장한다. `token.json`은 만들지 않는다. Testing 상태의 갱신 토큰 수명/재인증 조건은 Google 정책에 따라 달라질 수 있다.

이후 연결 점검은 label ID/type의 개수만 확인한다. 이메일 주소·라벨 이름·메일 본문을 출력하지 않고, 받은편지함 내용·초안 저장·발송은 접근하지 않는다. OAuth readonly 권한 자체는 메일 조회가 가능하므로 계정 선택과 동의 범위를 확인해야 한다.

초안 저장이 필요한 실제 구축에서는 `gmail.compose` 추가 동의와 Draft-only Broker 검수가 필요하다. compose는 **발송도 포함**하므로 이 설정에서 미리 요청하지 않는다.

## 4. 저장 후 연결 확인

키 두 개를 저장했다면 채팅에 **“키 저장했어”**라고만 알려주면 된다. Gmail 인증도 했다면 **“Gmail 인증도 했어”**라고 알려준다. 키 값이나 인증 JSON을 전달하지 않는다.

아래 명령은 외부 연결을 실제로 수행하므로 준비 후 실행한다. OpenAI는 유료 합성 추론 1회, LangSmith는 합성 trace/feedback 쓰기·조회, Gmail은 label 메타데이터 읽기다.

```powershell
.\tools\tool.ps1 doctor
.\tools\tool.ps1 probe openai --allow-network
.\tools\tool.ps1 probe langsmith --allow-network
.\tools\tool.ps1 probe gmail --allow-network
```

`doctor`의 `present_not_validated`는 저장소에 값이 있다는 뜻이다. 연결 성공은 각 probe가 `pass`를 반환한 경우에만 인정한다. 실패 시 SDK 오류 본문은 비밀 유출을 막기 위해 숨기며 실패 category만 보여준다. 키 미저장/잘못된 키·권한·리전·workspace UUID·결제 상태·회사 네트워크 제한을 확인한다. raw traceback이나 `.env` 전체를 채팅에 보내지 않는다.

키 교체는 같은 `secret-set` 명령으로 덮어쓴다. 로컬 삭제는 `secret-delete`이고, 원격 키 폐기·Google 권한 회수는 각 서비스 계정 화면에서 별도로 해야 한다. 본인 계정으로 실행되는 코드도 같은 사용자 보안 저장소에 접근할 수 있으므로 keyring만으로 프로세스 격리가 되지는 않는다. Hermes에 범용 실행 도구와 Gmail 키 접근 권한을 함께 주지 않는 검증은 후속 구축 대상이다.

## 공식 근거

- [OpenAI 시작 안내](https://developers.openai.com/api/docs/quickstart)
- [API 키 보안](https://developers.openai.com/api/reference/overview)
- [GPT-5.4 mini 모델·가격](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [LangSmith 계정·키 유형](https://docs.langchain.com/langsmith/create-account-api-key)
- [LangSmith 민감 데이터 숨기기](https://docs.langchain.com/langsmith/mask-inputs-outputs)
- [Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Gmail scope 권한 범위](https://developers.google.com/workspace/gmail/api/auth/scopes)
