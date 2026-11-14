import { z } from 'zod';
import { DecisionResponseSchema, MailSchema, RunResponseSchema, SnapshotSchema, ReleaseSchema, CaseDetailSchema, ManifestSchema, ReleaseEvidenceSchema } from './domain';
import type { ReviewAction } from './domain';
import { RuntimeTapeSchema } from './runtime';
import { csrfToken } from './session';

export const dataMode = import.meta.env.VITE_DATA_MODE === 'api' ? 'api' : 'mock';
export class ApiError extends Error {
  constructor(message:string, public status:number){super(message);this.name='ApiError';}
}
async function request<T>(url:string,schema:z.ZodType<T>,init?:RequestInit):Promise<T>{
  const response=await fetch('/api/v1'+url,{credentials:'same-origin',...init,headers:{'Content-Type':'application/json',...(dataMode==='api'?{'X-CSRF-Token':csrfToken()}:{}),...init?.headers}});
  if(response.status===401&&dataMode==='api')window.dispatchEvent(new Event('hermes-auth-required'));
  if(!response.ok){
    const body=await response.json().catch(()=>({detail:'요청을 처리하지 못했습니다.'}));
    throw new ApiError(body.detail??'요청 오류',response.status);
  }
  return schema.parse(await response.json());
}
export const api={
  mailbox:()=>request('/mailbox',MailboxSchema),
  mailboxControl:(paused:boolean)=>request('/mailbox/control',MailboxSchema,{method:'POST',body:JSON.stringify({paused})}),
  snapshot:(signal?:AbortSignal)=>request('/snapshot',SnapshotSchema,{signal}),
  saveDraft:(id:string,revision:number,body:string)=>request(`/reviews/${id}/draft`,MailSchema,{method:'PUT',body:JSON.stringify({revision,body})}),
  review:(id:string,revision:number,action:ReviewAction)=>request(`/reviews/${id}/decision`,DecisionResponseSchema,{method:'POST',body:JSON.stringify({revision,action})}),
  startRun:(source='fixture')=>request('/runs',RunResponseSchema,{method:'POST',body:JSON.stringify({query:'label:agent-test',maxItems:10,...(dataMode==='api'?{source}:{})})}),
  promote:(id:string)=>request(`/releases/${id}/promote`,ReleaseSchema,{method:'POST',body:JSON.stringify({target:'canary'})}),
  reconcile:(id:string)=>request(`/reviews/${id}/reconcile`,DecisionResponseSchema,{method:'POST'}),
  retryRun:(id:string)=>request(`/runs/${id}/retry`,RunResponseSchema,{method:'POST'}),
  caseDetail:(id:string,signal?:AbortSignal)=>request(`/evaluations/cases/${id}`,CaseDetailSchema,{signal}),
  manifest:(id:string,signal?:AbortSignal)=>request(`/releases/${id}/manifest`,ManifestSchema,{signal}),
  runtime:(id:string,mode:string,signal?:AbortSignal)=>request(`/runs/${id}/runtime?mode=${encodeURIComponent(mode)}`,RuntimeTapeSchema,{signal}),
  releaseEvidence:(id:string,signal?:AbortSignal)=>request(`/releases/${id}/evidence`,ReleaseEvidenceSchema,{signal}),
  evaluate:()=>request('/ops/evaluate',RunResponseSchema,{method:'POST'}),
  diagnose:()=>request('/ops/diagnose',RunResponseSchema,{method:'POST'}),
  flush:()=>request('/ops/flush',z.object({status:z.string(),delivered:z.number(),failed:z.number().optional()}),{method:'POST'}),
};
export const demoApi={
  loadScenario:(id:string)=>dataMode==='mock'?request('/mock/scenario',SnapshotSchema,{method:'POST',body:JSON.stringify({id})}):Promise.reject(new ApiError('검수 시나리오는 mock 모드에서만 사용할 수 있습니다.',403)),
};
export const MailboxSchema=z.object({enabled:z.boolean(),paused:z.boolean(),running:z.boolean(),lastChecked:z.string().nullable(),lastSuccess:z.string().nullable(),nextCheck:z.string().nullable(),error:z.string().nullable(),pollSeconds:z.number(),windowHours:z.number(),costCap:z.boolean(),limitReason:z.string().nullable().optional(),items:z.array(z.object({id:z.string(),messageId:z.string(),threadId:z.string(),sender:z.string(),address:z.string(),subject:z.string(),receivedAt:z.string(),status:z.string(),decision:z.string().optional(),reason:z.string().nullable().optional(),runId:z.string().nullable()}))});
