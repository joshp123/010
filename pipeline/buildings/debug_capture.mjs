// Written by AI on 2026-10-25 by model GPT-6.1 Sol.
import fs from 'node:fs';
const [port, output] = process.argv.slice(2);
let tab;
for (let attempt = 0; attempt < 200; attempt++) {
  try { tab = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t => t.type === 'page' && t.url.includes('/debug/')); if(tab)break; } catch {}
  await new Promise(r => setTimeout(r, 100));
}
if(!tab)throw new Error('Chromium did not open debug page');
const socket = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((resolve,reject) => {socket.onopen=resolve;socket.onerror=reject;});
let sequence=0;const pending=new Map();
socket.onmessage=e=>{const response=JSON.parse(e.data);if(response.id){const promise=pending.get(response.id);pending.delete(response.id);if(response.error)promise.reject(response.error);else promise.resolve(response.result);}};
function call(method,params={}) {const id=++sequence;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});}
await call('Page.enable');
await call('Runtime.enable');
await call('Emulation.setDeviceMetricsOverride',{width:2500,height:2500,deviceScaleFactor:1,mobile:false});
await call('Page.navigate',{url:tab.url});
let ready=false;let lastValue;
for(let attempt=0;attempt<600;attempt++) {
  const result=await call('Runtime.evaluate',{expression:'JSON.stringify({ready:window.renderComplete===true,failed:document.title==="FAILED",body:document.body.innerText,url:location.href,title:document.title})',returnByValue:true});
  const value=JSON.parse(result.result.value);
  lastValue=value;
  if(value.failed)throw new Error(value.body);
  if(value.ready){ready=true;break;}
  await new Promise(r=>setTimeout(r,100));
}
if(!ready)throw new Error('Debug renderer did not report READY: '+JSON.stringify(lastValue));
await new Promise(r=>setTimeout(r,250));
const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
fs.writeFileSync(output,Buffer.from(shot.data,'base64'));
socket.close();
