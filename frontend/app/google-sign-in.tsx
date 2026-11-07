'use client';
import Script from 'next/script';
import {useEffect,useRef,useState} from 'react';

export type Account={id?:string;name:string;role:string;email?:string;auth_method?:string;csrf_token?:string};
declare global {
 interface Window {google?:{accounts:{id:{initialize:(options:{client_id:string;nonce:string;callback:(response:{credential:string})=>void;auto_select:boolean})=>void;renderButton:(element:HTMLElement,options:{theme:string;size:string;shape:string;text:string})=>void;disableAutoSelect:()=>void}}}}
}

export default function GoogleSignIn({clientId,onAuthenticated}:{clientId:string;onAuthenticated:(account:Account)=>Promise<void>}){
 const element=useRef<HTMLDivElement>(null),callback=useRef(onAuthenticated);
 const [loaded,setLoaded]=useState(false),[refresh,setRefresh]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('');
 callback.current=onAuthenticated;
 useEffect(()=>{
  if(!loaded||!element.current||!window.google)return;
  let cancelled=false;
  async function mount(){
   try{
    const response=await fetch('/api/auth/challenge',{credentials:'same-origin'});
    const challenge=await response.json();
    if(!response.ok)throw Error(challenge.detail||'Unable to start Google sign-in');
    if(cancelled||!element.current||!window.google)return;
    window.google.accounts.id.initialize({client_id:clientId,nonce:challenge.nonce,auto_select:false,callback:async({credential})=>{
     setBusy(true);setError('');
     try{
      const result=await fetch('/api/auth/google',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential})});
      const account=await result.json();
      if(!result.ok)throw Error(account.detail||'Google sign-in was rejected');
      await callback.current(account);
     }catch(e){setError((e as Error).message);setRefresh(value=>value+1)}finally{setBusy(false)}
    }});
    element.current.replaceChildren();
    window.google.accounts.id.renderButton(element.current,{theme:'outline',size:'large',shape:'rectangular',text:'signin_with'});
   }catch(e){if(!cancelled)setError((e as Error).message)}
  }
  mount();
  return()=>{cancelled=true};
 },[clientId,loaded,refresh]);
 return <div className="google-sign-in"><Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" onLoad={()=>setLoaded(true)} onReady={()=>setLoaded(true)} onError={()=>setError('Google sign-in could not load. Check your connection and browser settings.')}/><div ref={element}/>{busy&&<p className="subtle">Verifying your workspace membership…</p>}{error&&<p role="alert" className="error">{error}</p>}</div>
}
