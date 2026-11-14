import { useEffect, useState, type ReactNode } from 'react';
import { dataMode } from './api';

let csrf='';
let boot:Promise<boolean>|null=null;
export function csrfToken(){return csrf;}
async function initialize(){
  const existing=await fetch('/api/v1/session',{credentials:'same-origin'});
  if(existing.ok){csrf=(await existing.json()).csrf;return true;}
  const token=new URLSearchParams(location.hash.slice(1)).get('console');
  if(!token)return false;
  history.replaceState(null,'',location.pathname+location.search);
  const response=await fetch('/api/v1/session/bootstrap',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
  if(!response.ok)return false;
  csrf=(await response.json()).csrf;return true;
}
export function SessionGate({children}:{children:ReactNode}){
  const [ready,setReady]=useState(dataMode==='mock');const [pending,setPending]=useState(dataMode==='api');
  useEffect(()=>{
    if(dataMode==='mock')return;
    boot??=initialize();void boot.then(ok=>{setReady(ok);setPending(false);}).catch(()=>setPending(false));
    const expired=()=>{csrf='';setReady(false);};window.addEventListener('hermes-auth-required',expired);
    return ()=>window.removeEventListener('hermes-auth-required',expired);
  },[]);
  if(ready)return children;
  return <main className="loading"><h1>Hermes 로컬 콘솔</h1><p>{pending?'이 브라우저의 접근 권한을 확인하고 있습니다.':'로컬 콘솔 로그인이 필요합니다. 프로젝트 실행기로 다시 열어주세요.'}</p>{!pending&&<p>API 키를 브라우저에 입력하지 않습니다. 프로젝트 폴더의 콘솔 실행기를 사용하세요.</p>}</main>;
}
