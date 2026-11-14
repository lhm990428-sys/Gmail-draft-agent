# 실제 연결 점검 결과

기준일: 2026-11-02 (Asia/Seoul). **3단계 점검 후 사용자가 4단계 진행을 승인했다.** 아래는 연결 점검 당시의 증거다. 실제 업무 하네스와 새 LangSmith v2 조회·Eval 연동 결과는 [4단계 구축 기록](13-build-progress.md)을 참조한다.

## 요약

| 대상 | 실제 결과 | 확인 범위 |
|---|---|---|
| Hermes v0.22.5 | 로컬 점검 통과 (11월 1일) | 임시 loopback Gateway liveness, 무인증 401, 임시 인증키 200, 프로세스 종료 |
| LangGraph / SQLite | 로컬 점검 통과 (11월 1일) | 중단, 파일 저장, checkpointer 재구성 후 재개 |
| Gmail | 실제 연결 통과 | 사용자 readonly OAuth, labels.list 응답, 라벨 19개 |
| LangSmith US | 실제 연결 통과 | 합성 trace 쓰기→조회, 연결 점수 쓰기→조회 |
| OpenAI GPT-5.4 mini | 실제 연결 통과 | 충전 후 합성 요청 1회 성공, 입력 17 / 출력 5토큰 |

Gmail 본문 조회 0, Draft 쓰기 0, 발송 경로 사용 0. 실제 메일을 OpenAI/LangSmith로 전송하지 않았다. OpenAI는 기존 저장 키 사용을 요청한 사용자 지시에 따라 점검했다. 최초 두 번의 429 이후 사용자가 충전 완료를 알렸고, 합성 요청 1회로 연결 성공을 확인했다. 비용은 API 응답에서 확인하지 못해 null이며, 0으로 표시하지 않는다.

## 증거

- `.local/reports/probe-gmail.json`: UTC 2026-11-01 16:59:43 → KST 2026-11-02 01:59:43. `status=pass`, `scope=gmail.readonly`, `operation=labels.list`, `label_count=19`.
- `.local/reports/probe-langsmith.json`: UTC 2026-11-01 16:59:49 → KST 2026-11-02 01:59:49. `status=pass`, `trace_readback=true`, `feedback_readback=true`.
- LangSmith project: `hermes-mail-dev-setup`.
- LangSmith run: `3fcce3c4-798a-49d3-aaf8-ec8267c9d1d0`.
- LangSmith feedback: `bf273bb9-51c6-44e4-a39f-c147de75de26`, key `setup_connectivity`, score 1.0. **이 점수는 SDK 연결 성공 확인이며 업무 품질 Eval이 아니다.**
- OpenAI 초기 실패: UTC 2026-11-01 17:02:06 → KST 2026-11-02 02:02:06. `status=failed`, `category=RateLimitError`, `http_status=429`. 허용된 세부 오류 코드는 확인되지 않았다. 해당 보고서는 후속 성공 결과로 갱신됐다.
- `.local/reports/probe-openai.json`: 최종 UTC 2026-11-01 17:06:29 → KST 2026-11-02 02:06:29. `status=pass`, 요청 alias `gpt-5.4-mini`, 실제 모델 `gpt-5.4-mini-2026-03-17`, 입력 17 / 출력 5토큰, 왕복 지연 5,203ms, `cost=null`. 단일 연결 확인 결과이며 성능 벤치마크가 아니다.

원격에 보낸 LangSmith 입력·출력은 빈 객체이며 metadata는 합성/환경/스키마 식별자다. API 키·OAuth token·메일 본문은 report에 포함하지 않는다. 로컬 보고서는 이후 재점검 시 갱신되므로 이 문서는 해당 확인 시각의 결과다.

## 남은 작업

1. 사용자에게 3단계 점검 결과를 검수받는다. OpenAI의 초기 429는 충전 후 재점검에서 해소됐다. 운영 비용/호출 예산과 정확한 역할별 모델 manifest 고정은 후속 구축 대상이다.
2. LangSmith는 점검에 성공했으나 SDK가 `read_run`과 partition key 없는 feedback 작성에 대한 사용 중단 예정 경고를 반환했다. 4단계 실제 운영 계측 구현에서는 project UUID/start_time을 포함한 `client.runs.retrieve` / feedback 계약으로 전환한다. 이 경고는 이번 성공 응답과 대사를 무효화하지 않는다. 새 API 경로의 실제 동작은 아직 점검하지 않았다.
3. 모든 실제 연결 점검과 3단계 검수가 끝난 후 사용자 승인으로 4단계 구축에 들어간다.

## 이번 코드 보완과 검증

OpenAI 진단을 위해 실패 report에 확인 시각, 숫자 HTTP 상태와 허용 목록의 오류 코드만 추가했다. SDK 메시지·응답 본문·헤더는 숨긴다. 실패도 보고서를 갱신한다. backend 테스트 **9건 통과**. 화면/업무 하네스는 변경하지 않았다.

## 근거

- [OpenAI 오류 코드](https://developers.openai.com/api/docs/guides/error-codes): 429는 호출 제한 또는 quota/과금 한도 관련 상태일 수 있으므로 구분이 필요하다.
- [LangSmith run 조회 전환](https://docs.langchain.com/langsmith/smithdb-sdk-migration-runs)
- [LangSmith feedback 전환](https://docs.langchain.com/langsmith/smithdb-sdk-migration-feedback)
