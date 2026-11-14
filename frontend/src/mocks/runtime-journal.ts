import type { Mail } from '../domain';
import type { RuntimeTape } from '../runtime';
import { runtimeTape } from './runtime-data';

type Action=Omit<RuntimeTape['events'][number],'sequence'|'atMs'>;
export class RuntimeJournal{
  private origins=new Map<string,Mail>();
  private actions=new Map<string,Action[]>();
  constructor(mails:Mail[]){this.reset(mails);}
  reset(mails:Mail[]){this.origins.clear();this.actions.clear();mails.forEach(m=>this.register(m));}
  register(mail:Mail){if(!this.origins.has(mail.runId))this.origins.set(mail.runId,structuredClone(mail));}
  append(runId:string,action:Action){this.actions.set(runId,[...this.actions.get(runId)??[],structuredClone(action)]);}
  read(mail:Mail,mode:RuntimeTape['mode']):RuntimeTape{
    this.register(mail);const origin=this.origins.get(mail.runId)!;
    const tape=runtimeTape(mode==='rework'?{...origin,status:'waiting'}:origin,mode);
    if(mode==='normal')for(const action of this.actions.get(mail.runId)??[]){const sequence=tape.events.length+1;tape.events.push({...structuredClone(action),sequence,atMs:(sequence-1)*550});}
    return tape;
  }
}
