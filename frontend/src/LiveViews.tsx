import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from './api';
import type { Snapshot } from './domain';
import { Badge, Empty, Heading, Jump, Panel, number, percent } from './components';

type Props={data:Snapshot};
export function LiveOverview({data}:Props){
  const release=data.releases[0];
  return <><Heading eyebrow="LOCAL OPERATIONS" title="오늘의 운영 상태" description="실제 저장된 실행과 측정 근거만 표시합니다. 합성 입력과 실제 메일은 실행 기록에서 구분합니다."/><div className="metrics-grid">{[['실행',number(data.metrics.executions)],['기술 성공률',data.metrics.executions?percent(data.metrics.successes/data.metrics.executions):'N/A'],['총 토큰',number(data.metrics.tokens)],['추정 비용',data.metrics.cost===null?'N/A':`$${data.metrics.cost.toFixed(4)}`]].map(([k,v])=><div className="metric" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><Panel title="현재 릴리스 판단"><Badge value={release.decision}/><p className="padded">운영 배포용 평가·shadow·복구 근거가 완결되기 전에는 승격하지 않습니다.</p><Jump to="/operations">동일 릴리스의 근거 확인</Jump></Panel><Panel title="검토 대기"><div className="table-wrap"><table><thead><tr><th>메일</th><th>상태</th><th>검토</th></tr></thead><tbody>{data.mails.map(m=><tr key={m.id}><td>{m.subject}<small>{m.source==='fixture'?'합성 입력':'Gmail 입력'}</small></td><td><Badge value={m.status}/></td><td><Jump to={`/?mail=${m.id}`}>메일 작업실</Jump></td></tr>)}</tbody></table>{!data.mails.length&&<Empty>아직 실행한 메일이 없습니다. 상단에서 합성 테스트 실행을 시작하세요.</Empty>}</div></Panel></>;
}
export function LiveObserve({data}:Props){
  return <><Heading eyebrow="OBSERVE / MEASURED LEAVES" title="운영 관측" description="provider가 보고한 leaf usage만 합산합니다. 누락 값은 N/A, 비용은 고정 가격표에 따른 추정입니다."/><div className="metrics-grid">{[['총 토큰',number(data.metrics.tokens)],['추정 비용',data.metrics.cost===null?'N/A':`$${data.metrics.cost.toFixed(4)}`],['p95 준비 지연',data.metrics.p95===null?'N/A':`${data.metrics.p95.toFixed(2)}s`],['서버 조회 대사',percent(data.metrics.coverage)]].map(([k,v])=><div className="metric" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><Panel title="Agent별 실제 호출"><div className="table-wrap"><table><thead><tr><th>Agent</th><th>호출</th><th>평균 지연</th><th>모델</th><th>상세</th></tr></thead><tbody>{data.agents.map(a=><tr key={a.id}><td>{a.name}</td><td>{a.calls}</td><td>{a.calls?`${a.latency.toFixed(2)}s`:'N/A'}</td><td>{a.model}</td><td><Jump to={`/observe/${a.id}`}>trace 표본</Jump></td></tr>)}</tbody></table></div></Panel></>;
}
export function LiveConfiguration({data}:Props){
  return <><Heading eyebrow="LOCAL PROFILE / RIGHTS" title="환경과 연결" description="현재 실행 정책과 3단계 점검 근거를 구분합니다. 키는 서버의 Windows 자격 증명 관리자에 보관합니다."/><Panel title="현재 정책"><dl className="detail-facts"><div><dt>모델</dt><dd>{data.capabilities?.modelMode} / {data.agents[0]?.model}</dd></div><div><dt>실제 메일 외부 반출</dt><dd>{data.capabilities?.realMailExport?'명시적 로컬 정책 허용':'차단 · 별도 동의 필요'}</dd></div><div><dt>Gmail Draft 쓰기</dt><dd>{data.capabilities?.gmailDraftWrite?'정책 허용 · compose 및 승인 추가 검증':'차단 · readonly OAuth'}</dd></div><div><dt>발송</dt><dd>Broker API에 발송 메서드 없음</dd></div></dl></Panel><Panel title="연결 점검 근거"><div className="table-wrap"><table><thead><tr><th>대상</th><th>마지막 근거</th><th>내용</th></tr></thead><tbody>{data.dependencies.map(d=><tr key={d.id}><td>{d.name}</td><td>{d.status==='ready'?'이전 점검 통과':'현재 근거 없음'}</td><td>{d.description}</td></tr>)}</tbody></table></div></Panel></>;
}
export function LiveDiagnose({data}:Props){
  return <><Heading eyebrow="DIAGNOSE / EVIDENCE" title="에이전트 건강 진단" description="7개 건강 차원의 측정 근거를 구분합니다. 미검증을 정상으로 바꾸지 않으며 LLM 가설은 판단실에서 확인합니다."/><Panel title="7개 건강 차원"><div className="health-grid">{data.health.map(h=><div key={h.id}><strong>{h.label}</strong> <Badge value={h.status}/><p>{h.value}</p><small>{h.target}</small></div>)}</div></Panel>{data.incidents.map(i=><Panel title={i.title} key={i.id}><div className="padded"><p>{i.cause}</p><p>{i.action}</p><Jump to={`/runs/${i.runId}`}>실패 실행 근거</Jump></div></Panel>)}<Jump to="/operations">동일 릴리스의 평가·관측·진단 판단실</Jump></>;
}
export function OpsActions({refresh,notify}:{refresh:()=>Promise<void>;notify:(s:string)=>void}){
  const [pending,setPending]=useState('');
  async function invoke(kind:string){setPending(kind);try{const result=kind==='eval'?await api.evaluate():kind==='diagnose'?await api.diagnose():await api.flush();await refresh();notify(kind==='eval'?'개발용 합성 회귀 평가 완료 · holdout/배포 검증과 별도':kind==='diagnose'?'운영 근거에 대한 가설 갱신 완료':`이벤트 대사 ${'delivered' in result?result.delivered:0}건`);}catch(e){notify(e instanceof Error?e.message:'운영 작업 실패');}finally{setPending('');}}
  return <div className="toolbar"><button disabled={!!pending} onClick={()=>void invoke('eval')}>{pending==='eval'?'평가 실행 중…':'개발 회귀 평가 · 합성 2건'}</button><button disabled={!!pending} onClick={()=>void invoke('diagnose')}>{pending==='diagnose'?'진단 중…':'건강 진단 갱신'}</button><button disabled={!!pending} onClick={()=>void invoke('flush')}>이벤트 전송·대사</button><span className="muted">평가·진단은 모델 호출 비용이 발생할 수 있습니다.</span></div>;
}
export function LiveDetail({kind,data}:{kind:string;data:Snapshot}){
  const {id}=useParams();
  const agent=data.agents.find(a=>a.id===id);const dependency=data.dependencies.find(d=>d.id===id);const incident=data.incidents.find(i=>i.id===id);
  const value=kind==='dependency'?dependency:kind==='diagnosis'?incident:agent;
  if(!value)return <Empty><h1>상세 항목을 찾을 수 없습니다</h1><Link to="/">메일 작업실로 이동</Link></Empty>;
  const related=data.runs.filter(r=>r.spans.some(s=>s.agentId===id));
  return <><Heading eyebrow="ACTUAL LOCAL EVIDENCE" title={agent?`${agent.name} · ${kind==='observe'?'관측 상세':'계약 상세'}`:dependency?.name??incident!.title} description="현재 API 응답의 근거만 표시합니다. 측정되지 않은 품질·건강 상태는 추정하지 않습니다."/><Panel title="등록·관측 근거"><pre className="padded">{JSON.stringify(value,null,2)}</pre></Panel>{agent&&<Panel title="연결된 실제 실행">{related.map(r=><div className="padded" key={r.id}><code>{r.id}</code> <Badge value={r.status}/> <Jump to={`/runs/${r.id}`}>Trace 상세</Jump></div>)}{!related.length&&<Empty>이 agent의 관측된 호출이 없습니다.</Empty>}</Panel>}<Jump to="/operations">릴리스 판단 근거</Jump></>;
}
