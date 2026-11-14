import type { ReactNode } from 'react';
import { useRef } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip, AreaChart, Area } from 'recharts';
import type { Snapshot } from './domain';

const labels:Record<string,string>={healthy:'정상',HEALTHY:'정상',degraded:'주의',DEGRADED:'주의',UNHEALTHY:'장애',disabled:'비활성',waiting:'검토 대기',reviewed:'검토 완료', draft_saved:'초안 저장',rejected:'검토 종료',review:'검토 대기',success:'성공',failed:'실패',error:'오류',passed:'통과',regression:'회귀',pending:'진행 중',PASS:'통과',FAIL:'미달',UNKNOWN:'근거 부족',READY_FOR_APPROVAL:'승인 가능',IMPROVE_REQUIRED:'개선 필요',DEBUG_REQUIRED:'디버그 필요',HOLD:'보류',REPLY_REQUIRED:'회신 필요',REVIEW_REQUIRED:'주의 검토',NO_REPLY:'회신 불필요',low:'낮음',medium:'중간',high:'높음',candidate:'후보',baseline:'기준',promoted:'승격 완료',ready:'합성 정상',unknown:'미확인'};
export const label=(value:string)=>labels[value]??value;
export function Badge({value}:{value:string}){
  const tone=['healthy','HEALTHY','PASS','success','passed','draft_saved','READY_FOR_APPROVAL','promoted','ready'].includes(value)?'good':['failed','error','FAIL','UNHEALTHY','DEBUG_REQUIRED'].includes(value)?'bad':['degraded','DEGRADED','regression','REVIEW_REQUIRED','IMPROVE_REQUIRED','medium','high'].includes(value)?'warn':'neutral';
  return <span className={`badge ${tone}`}><span className="status-dot"/>{label(value)}</span>;
}
export function Heading({eyebrow,title,description,action}:{eyebrow:string;title:string;description:string;action?:ReactNode}){return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;}
export function Panel({title,subtitle,action,children,className=''}:{title:string;subtitle?:string;action?:ReactNode;children:ReactNode;className?:string}){return <section className={`panel ${className}`}><div className="panel-heading"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>{children}</section>;}
export function Empty({children}:{children:ReactNode}){return <div className="empty">{children}</div>;}
export function Jump({to,children}:{to:string;children:ReactNode}){return <Link className="jump" to={to}>{children}<ArrowUpRight size={14}/></Link>;}
export function Confirm({open,onOpenChange,title,description,children,onConfirm,pending,button='확인'}:{open:boolean;onOpenChange:(v:boolean)=>void;title:string;description:string;children?:ReactNode;onConfirm:()=>void;pending:boolean;button?:string}){
  const returnFocus=useRef<HTMLElement|null>(null);
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="dialog-content" onOpenAutoFocus={()=>{returnFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;}} onCloseAutoFocus={e=>{e.preventDefault();returnFocus.current?.focus();}}><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description}</Dialog.Description>{children}<div className="dialog-actions"><button onClick={()=>onOpenChange(false)} disabled={pending}>취소</button><button className="primary" onClick={onConfirm} disabled={pending}>{pending?'처리 중…':button}</button></div><Dialog.Close className="dialog-close" aria-label="닫기" disabled={pending}><X size={18}/></Dialog.Close></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
export function Trend({data,metric='executions'}:{data:Snapshot['trend'];metric?:'executions'|'tokens'|'latency'|'cost'}){
  const names={executions:'실행 건수',tokens:'토큰',latency:'p95 지연(초)',cost:'비용(USD)'};
  return <div className="chart" role="img" aria-label={`${names[metric]} · 합성 추이`}><ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{top:15,right:15,bottom:0,left:0}}><CartesianGrid strokeDasharray="3 4" vertical={false} stroke="#e7ebf0"/><XAxis dataKey="time" axisLine={false} tickLine={false} tick={{fontSize:11,fill:'#657287'}}/><YAxis axisLine={false} tickLine={false} tick={{fontSize:11,fill:'#657287'}} width={54} tickFormatter={v=>v>=1000?`${v/1000}k`:String(v)}/><Tooltip formatter={value=>[Number(value).toLocaleString(),names[metric]]}/><Area type="monotone" dataKey={metric} stroke="#3267d6" fill="#edf3ff" strokeWidth={2} isAnimationActive={false}/></AreaChart></ResponsiveContainer></div>;
}
export const number=(v:number|null)=>v===null?'N/A':v.toLocaleString('en-US');
export const percent=(v:number|null)=>v===null||!Number.isFinite(v)?'N/A':(v*100).toFixed(1)+'%';
