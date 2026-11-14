import { z } from 'zod';

export const RuntimeState=z.enum(['idle','queued','running','done','waiting','failed','uncertain']);
export type RuntimeStatus=z.infer<typeof RuntimeState>;
export const RuntimeTapeSchema=z.object({
  version:z.literal('runtime.v1'),runId:z.string(),source:z.enum(['synthetic','fixture','gmail']),mode:z.enum(['normal','rework','timeout']),
  nodes:z.array(z.object({id:z.string(),name:z.string(),kind:z.enum(['agent','tool','human','checkpoint']),role:z.string(),x:z.number(),y:z.number(),taskId:z.string(),scope:z.string()})),
  edges:z.array(z.object({id:z.string(),source:z.string(),target:z.string(),kind:z.enum(['data','delegation','memory','rework']),label:z.string(),contract:z.string()})),
  tasks:z.array(z.object({id:z.string(),owner:z.string(),goal:z.string(),dependsOn:z.array(z.string())})),
  events:z.array(z.object({sequence:z.number(),atMs:z.number(),type:z.string(),nodeId:z.string(),status:RuntimeState,summary:z.string(),input:z.string().optional(),output:z.string().optional(),edgeId:z.string().optional(),memory:z.record(z.string(),z.string()).optional(),checkpoint:z.string().optional()})),
});
export type RuntimeTape=z.infer<typeof RuntimeTapeSchema>;
export type RuntimeFrame={status:Record<string,RuntimeStatus>;memory:Record<string,Record<string,string>>;input:Record<string,string>;output:Record<string,string>;attempts:Record<string,number>;checkpoint:string|null;sequence:number;events:RuntimeTape['events']};
export function runtimeFrame(tape:RuntimeTape,count:number):RuntimeFrame{
  const frame:RuntimeFrame={status:Object.fromEntries(tape.nodes.map(n=>[n.id,'idle' as const])),memory:{},input:{},output:{},attempts:{},checkpoint:null,sequence:0,events:[]};
  for(const e of tape.events.slice(0,Math.max(0,Math.min(count,tape.events.length)))){
    frame.sequence=e.sequence;frame.status[e.nodeId]=e.status;frame.events.push(e);
    if(e.input!==undefined)frame.input[e.nodeId]=e.input;
    if(e.output!==undefined)frame.output[e.nodeId]=e.output;
    if(e.memory)frame.memory[e.nodeId]={...frame.memory[e.nodeId],...e.memory};
    if(e.checkpoint)frame.checkpoint=e.checkpoint;
    if(e.status==='running')frame.attempts[e.nodeId]=(frame.attempts[e.nodeId]??0)+1;
  }
  return frame;
}
export const runtimeLabels:Record<RuntimeStatus,string>={idle:'미실행',queued:'위임 대기',running:'실행 중',done:'완료',waiting:'사람 대기',failed:'실패',uncertain:'저장 결과 확인 필요'};
