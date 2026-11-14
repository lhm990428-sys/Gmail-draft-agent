import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Play, RotateCcw } from 'lucide-react';
import { dataMode, demoApi } from './api';
import type { Snapshot } from './domain';
import { scenarios } from './scenario-catalog';
import { Badge, Confirm, Heading, Jump, Panel } from './components';

type Feedback={decision:string;note:string};
const storageKey='hermes.mock.review.v1';
function loadFeedback():Record<string,Feedback>{
  try{
    const value:unknown=JSON.parse(localStorage.getItem(storageKey)??'{}');
    if(!value||typeof value!=='object'||Array.isArray(value))return {};
    return Object.fromEntries(Object.entries(value).filter(([,v])=>v&&typeof v==='object'&&typeof v.decision==='string'&&typeof v.note==='string'));
  }catch{return {};}
}
export function Scenarios({data,refresh,notify}:{data:Snapshot;refresh:()=>Promise<void>;notify:(s:string)=>void}){
  const [params,setParams]=useSearchParams();const selected=scenarios.find(s=>s.id===params.get('case'))??scenarios[0];
  const [pending,setPending]=useState(false);const [open,setOpen]=useState(false);const [error,setError]=useState('');
  const [feedback,setFeedback]=useState(loadFeedback);const client=useQueryClient();
  const current=feedback[selected.id]??{decision:'unreviewed',note:''};
  const change=(patch:Partial<Feedback>)=>setFeedback(prev=>({...prev,[selected.id]:{...current,...patch}}));
  const saveFeedback=()=>{try{localStorage.setItem(storageKey,JSON.stringify(feedback));notify('검수 의견을 이 브라우저에 저장했습니다. 실제 배포 승인이 아닙니다.');}catch{setError('이 브라우저에 의견을 저장하지 못했습니다. 저장소 권한을 확인해 주세요.');}};
  const start=async()=>{
    setPending(true);setError('');
    try{await client.cancelQueries({queryKey:['snapshot']});await demoApi.loadScenario(selected.id);await refresh();setOpen(false);notify('합성 시나리오를 준비했습니다. 아래 단계별 상세 화면으로 이동하세요.');}
    catch(e){setError(e instanceof Error?e.message:'시나리오 준비 실패');}finally{setPending(false);}
  };
  const active=data.demoScenario===selected.id;
  return <><Heading eyebrow="REVIEW WORKBENCH / DEPTH 2" title="시나리오 검수" description="합성 시나리오를 선택하고 상세 화면을 따라가며, 제품 흐름을 유지할지 수정할지 결정하세요."/><div className="method-note">시나리오 시작은 현재 탭의 합성 메일·실행·릴리스 변경을 초기화합니다. 실제 서비스에는 영향이 없으며 검수 의견은 별도로 보관됩니다. 페이지 새로고침 시 합성 상태는 기본값으로 돌아갑니다.</div><div className="scenario-layout"><section className="scenario-list" aria-label="검수 시나리오 목록">{scenarios.map((s,i)=><button key={s.id} aria-pressed={selected.id===s.id} className={selected.id===s.id?'selected':''} onClick={()=>{setParams({case:s.id});setError('');}}><span className="scenario-index">{String(i+1).padStart(2,'0')}</span><div><small>{s.group}</small><strong>{s.title}</strong><span>{feedback[s.id]?.decision&&feedback[s.id]?.decision!=='unreviewed'?'검수 의견 있음':'미검수'}</span></div></button>)}</section><div className="scenario-main"><Panel title={selected.title} subtitle={selected.description} action={<Badge value={active?'시나리오 적용됨':'미시작'}/>}><div className="scenario-decision"><span className="eyebrow">이 시나리오에서 결정할 것</span><h3>{selected.decision}</h3><p>{active?'현재 이 시나리오가 적용되었습니다. 각 단계를 클릭해 판단하고 결과 상태를 확인하세요.':'먼저 아래 버튼으로 합성 데이터를 준비하세요. 선택만으로 데이터가 바뀌지는 않습니다.'}</p><button className="primary" onClick={()=>setOpen(true)} disabled={pending||dataMode!=='mock'}>{active?<RotateCcw size={14}/>:<Play size={14}/>} {active?'시나리오 다시 시작':'이 시나리오 시작'}</button>{error&&<p className="inline-error" role="alert">{error}</p>}</div></Panel><Panel title="단계별 화면과 예상 결과" subtitle="자동 완료 체크가 아니라, 사용자가 직접 확인할 검수 기준입니다."><ol className="scenario-steps">{selected.steps.map((step,i)=><li key={i}><span>{i+1}</span><div><h3>{step.title}</h3><p>{step.expected}</p>{active?<div className="scenario-primary-links"><Jump to={step.to}>상세 화면으로 이동</Jump>{step.detailTo&&<Jump to={step.detailTo}>상세 원장으로 이동</Jump>}</div>:<small>시나리오를 시작하면 이동할 수 있습니다.</small>}</div></li>)}</ol></Panel><Panel title="검수 의견 · 제품 의사결정" subtitle="이 브라우저에만 저장됩니다. 실제 메일 처리나 배포 승인과는 별개입니다."><div className="feedback-form"><label htmlFor="review-decision">화면·흐름에 대한 판단</label><select id="review-decision" value={current.decision} onChange={e=>change({decision:e.target.value})}><option value="unreviewed">미검수</option><option value="keep">현재 흐름 유지</option><option value="change">수정 필요</option><option value="hold">추가 확인 후 판단</option></select><label htmlFor="review-note">검수 메모</label><textarea id="review-note" value={current.note} onChange={e=>change({note:e.target.value})} placeholder="헷갈리는 단계, 필요한 근거, 바꾸고 싶은 버튼·화면을 적어 주세요. 비밀 키나 실제 메일 개인정보는 입력하지 마세요."/><button onClick={saveFeedback}>검수 의견 저장</button></div></Panel></div></div><Confirm open={open} onOpenChange={setOpen} title="합성 시나리오를 시작할까요?" description="현재 탭의 합성 변경 사항이 초기화됩니다. 실제 메일·서비스·배포는 변경하지 않습니다. 기존 검수 의견은 유지됩니다." pending={pending} button="초기화 후 시나리오 시작" onConfirm={()=>void start()}><div className="confirmation-detail"><strong>{selected.title}</strong><p>{selected.description}</p></div></Confirm></>;
}
