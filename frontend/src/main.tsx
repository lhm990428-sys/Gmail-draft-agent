import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { dataMode } from './api';
import { SessionGate } from './session';
import './styles.css';
import '@xyflow/react/dist/style.css';

async function boot(){
  if(dataMode==='mock'){
    const {worker}=await import('./mocks/browser');
    await worker.start({onUnhandledRequest:'bypass',quiet:true});
  }
  const client=new QueryClient({defaultOptions:{queries:{retry:1,staleTime:15000,refetchOnWindowFocus:false}}});
  ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><BrowserRouter><SessionGate><App/></SessionGate></BrowserRouter></QueryClientProvider></React.StrictMode>);
}
void boot().catch(()=>{document.getElementById('root')!.textContent='목업 초기화에 실패했습니다. 페이지를 새로고침해 주세요.';});
