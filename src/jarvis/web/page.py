INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>Jarvis</title>
<style>
  :root{
    color-scheme: light dark;
    --bg:#eceef1; --card:#ffffff; --fg:#1b1e23; --muted:#6b7280; --line:#e4e6ea;
    --accent:#2f6fed; --user:#2f6fed; --bot:#f1f2f5; --chip:#f4f5f7;
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#1e1f22; --card:#2a2b2f; --fg:#e8eaed; --muted:#9aa0a6; --line:#3a3c41;
           --accent:#4a90ff; --user:#2f5fd0; --bot:#33353a; --chip:#3a3c41; }
  }
  :root[data-theme="light"]{ --bg:#eceef1; --card:#ffffff; --fg:#1b1e23; --muted:#6b7280; --line:#e4e6ea;
           --accent:#2f6fed; --user:#2f6fed; --bot:#f1f2f5; --chip:#f4f5f7; }
  :root[data-theme="dark"]{ --bg:#1e1f22; --card:#2a2b2f; --fg:#e8eaed; --muted:#9aa0a6; --line:#3a3c41;
           --accent:#4a90ff; --user:#2f5fd0; --bot:#33353a; --chip:#3a3c41; }
  *{ box-sizing:border-box; }
  html,body{ height:100%; }
  body{ margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; color:var(--fg);
        background:var(--bg); }
  #app{ position:fixed; left:50%; bottom:28px; transform:translateX(-50%); display:flex; flex-direction:column;
        align-items:center; gap:10px; z-index:20; }
  .mic{ width:76px; height:76px; border-radius:50%; border:1.5px solid var(--line); background:var(--card);
        color:var(--accent); display:flex; align-items:center; justify-content:center; cursor:pointer;
        transition:background .15s,border-color .15s,color .15s; }
  .mic svg{ width:30px; height:30px; }
  #app[data-state="listening"] .mic, #app[data-state="connecting"] .mic, #app[data-state="thinking"] .mic, #app[data-state="speaking"] .mic{
        background:var(--accent); border-color:var(--accent); color:#fff; }
  .status{ display:none; font-size:15px; color:var(--fg); }
  #app[data-view="menu"] .status{ display:block; }
  .caption{ display:none; font-size:12px; color:var(--muted); margin-top:-2px; }
  #app:not([data-state="idle"]) .caption{ display:block; }
  #app[data-state="thinking"] .mic svg{ animation:breathe 1.2s ease-in-out infinite; }
  @keyframes breathe{ 50%{ opacity:.35; } }

  .pop{ position:absolute; bottom:96px; left:50%; transform:translateX(-50%);
        display:flex; flex-direction:column; max-height:min(82vh,760px);
        background:var(--card); border:1px solid var(--line); border-radius:16px; padding:14px;
        width:320px; max-width:calc(100vw - 32px); }
  #app[data-view="chat"] .pop{ height:min(72vh,640px); }
  #app[data-full="true"] .pop{ width:min(780px,94vw); height:min(88vh,860px); }
  .pop[hidden]{ display:none; }
  .pop::after{ content:""; position:absolute; bottom:-7px; left:50%; transform:translateX(-50%) rotate(45deg);
        width:12px; height:12px; background:var(--card); border-right:1px solid var(--line); border-bottom:1px solid var(--line); }
  .view{ display:none; }
  #app[data-view="menu"] .view-menu{ display:flex; flex-direction:column; gap:4px; }
  #app[data-view="chat"] .view-chat{ display:flex; flex-direction:column; flex:1; min-height:0; }
  #app[data-view="input"] .view-input{ display:block; }
  #app[data-view="settings"] .view-settings{ display:flex; flex-direction:column; gap:9px; }

  .row{ display:flex; align-items:center; gap:12px; padding:11px 12px; border:0; background:transparent;
        color:var(--fg); border-radius:10px; cursor:pointer; font-size:15px; text-align:left; width:100%; }
  .row:hover{ background:var(--chip); }
  .row svg{ width:20px; height:20px; color:var(--fg); flex:0 0 auto; }

  .vhead{ display:flex; align-items:center; gap:8px; margin-bottom:8px; font-weight:600; font-size:14px; }
  .vhead button{ border:0; background:transparent; color:var(--muted); cursor:pointer; font-size:18px; padding:0 4px; }

  .log{ display:flex; flex-direction:column; gap:8px; flex:1; min-height:0; overflow-y:auto; padding:2px; }
  .log:empty::before{ content:"Say hello."; color:var(--muted); font-size:13px; }
  .msg{ max-width:88%; padding:8px 11px; border-radius:12px; white-space:pre-wrap; word-break:break-word; font-size:14px; }
  .user{ align-self:flex-end; background:var(--user); color:#fff; }
  .partial{ align-self:flex-end; background:var(--user); color:#fff; opacity:.7; font-style:italic; }
  .bot{ align-self:flex-start; background:var(--bot); }
  .meta{ font-size:11px; color:var(--muted); margin-bottom:4px; }
  .tool{ display:inline-block; border:1px solid var(--line); border-radius:6px; padding:0 6px; margin-right:4px; }
  .caret::after{ content:"▋"; color:var(--accent); animation:blink 1s steps(1) infinite; }
  @keyframes blink{ 50%{ opacity:0; } }

  form.composer{ display:flex; gap:8px; margin-top:10px; }
  form.composer input{ flex:1; min-width:0; background:transparent; border:1px solid var(--line); color:var(--fg);
        border-radius:10px; padding:9px 11px; outline:none; }
  form.composer input:focus{ border-color:var(--accent); }
  form.composer button{ border:1px solid var(--line); background:transparent; color:var(--fg); border-radius:10px; padding:9px 12px; cursor:pointer; }

  .view-settings label{ display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--muted); }
  .view-settings select,.view-settings input{ background:var(--bg); border:1px solid var(--line); color:var(--fg);
        border-radius:8px; padding:7px 9px; }
  .btnrow{ display:flex; gap:8px; }
  .btnrow button{ flex:1; border:1px solid var(--line); background:transparent; color:var(--fg); border-radius:9px; padding:8px; cursor:pointer; }
  .tabs{ display:flex; gap:2px; border-bottom:1px solid var(--line); margin:0 0 8px; }
  .tabs .tab{ flex:1; border:0; background:transparent; color:var(--muted); cursor:pointer; font-size:13px;
        padding:8px 4px; border-bottom:2px solid transparent; margin-bottom:-1px; }
  .tabs .tab[aria-selected="true"]{ color:var(--fg); border-bottom-color:var(--accent); }
  .tabpane{ display:none; flex-direction:column; gap:9px; min-height:196px; }
  .tabpane.active{ display:flex; }
  .pbar{ height:8px; border-radius:999px; background:var(--chip); overflow:hidden; }
  .pbar-fill{ height:100%; width:0%; background:var(--accent); border-radius:999px; transition:width .3s ease; }
  .pbar.indet .pbar-fill{ width:35%; transition:none; animation:indet 1.1s ease-in-out infinite; }
  @keyframes indet{ 0%{ transform:translateX(-130%); } 100%{ transform:translateX(330%); } }
</style>
</head>
<body>
<div id="app" data-view="chat" data-state="idle">
  <div class="pop" id="pop">
    <nav class="view view-menu">
      <span class="status" id="status">Ready</span>
      <button class="row" data-nav="chat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 12a8 8 0 0 1-11.5 7.2L3 21l1.8-6.5A8 8 0 1 1 21 12z"/></svg><span>Chat</span></button>
      <button class="row" data-nav="input"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M9 10h.01M12 10h.01M15 10h.01M18 10h.01M8 14h8"/></svg><span>Keyboard</span></button>
      <button class="row" data-nav="settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2 2 2 0 1 1-4 0 1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 15a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.5-2.6l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 4.6a2 2 0 1 1 4 0 1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 21 11a2 2 0 1 1 0 4z"/></svg><span>Settings</span></button>
    </nav>

    <section class="view view-chat">
      <div class="vhead"><button data-nav="menu">&#8249;</button><span>Chat</span><button id="btn-full" title="Full screen" style="margin-left:auto">&#10530;</button></div>
      <div class="log" id="log"></div>
      <form class="composer" id="composer" autocomplete="off"><input id="text" type="text" placeholder="Message Jarvis" /><button type="submit">Send</button></form>
    </section>

    <section class="view view-input">
      <form class="composer" id="quickform" autocomplete="off"><input id="quicktext" type="text" placeholder="Type a message…" /><button type="submit">Send</button></form>
    </section>

    <section class="view view-settings">
      <div class="vhead"><button data-nav="menu">&#8249;</button><span>Settings</span></div>
      <div class="tabs" id="settings-tabs">
        <button class="tab" type="button" data-tab="brain" aria-selected="true">Brain</button>
        <button class="tab" type="button" data-tab="speech" aria-selected="false">Speech</button>
        <button class="tab" type="button" data-tab="voice" aria-selected="false">Voice</button>
      </div>
      <div class="tabbody">
        <div class="tabpane active" data-pane="brain">
          <label>Response brain <select id="s-mode"><option value="local">On-device</option><option value="api">API</option></select></label>
          <div id="s-local-row">
            <label>On-device model <select id="s-local"></select></label>
            <div id="brain-info" style="font-size:11px;color:var(--muted);margin-top:6px"></div>
            <div class="btnrow" id="brain-actions" style="display:none">
              <button id="s-brain-download" style="display:none">Download model</button>
            </div>
            <div id="brain-progress-wrap" style="display:none;margin-top:8px">
              <div class="pbar" id="brain-bar"><div class="pbar-fill" id="brain-bar-fill"></div></div>
              <div id="brain-progress" style="font-size:11px;color:var(--muted);margin-top:6px"></div>
            </div>
          </div>
        </div>
        <div class="tabpane" data-pane="speech">
          <label>Speech recognition <select id="s-asr"></select></label>
          <div id="asr-info" style="font-size:11px;color:var(--muted)"></div>
          <div class="btnrow" id="asr-actions" style="display:none">
            <button id="s-asr-install" style="display:none">Install NVIDIA runtime</button>
            <button id="s-asr-download" style="display:none">Download model</button>
          </div>
          <div id="asr-progress-wrap" style="display:none">
            <div class="pbar" id="asr-bar"><div class="pbar-fill" id="asr-bar-fill"></div></div>
            <div id="asr-progress" style="font-size:11px;color:var(--muted);margin-top:6px"></div>
          </div>
        </div>
        <div class="tabpane" data-pane="voice">
          <label>Microphone <select id="s-mic"></select></label>
          <div id="mic-info" style="font-size:11px;color:var(--muted)"></div>
          <label>TTS engine <select id="s-tts-backend"><option value="chatterbox">Chatterbox (natural)</option><option value="kokoro">Kokoro (fast)</option></select></label>
          <label>Voice <select id="s-voice"></select></label>
          <label>Max spoken sentences <input id="s-cap" type="number" min="1" max="10" /></label>
        </div>
      </div>
      <div class="btnrow"><button id="s-save">Save</button><button id="s-preview">Preview</button></div>
    </section>
  </div>

  <button class="mic" id="mic" aria-label="Talk">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4"/></svg>
  </button>
  <span class="caption" id="caption"></span>
</div>

<script>
const app=document.getElementById('app'), pop=document.getElementById('pop'), log=document.getElementById('log');
const statusEl=document.getElementById('status'), micBtn=document.getElementById('mic');
const composer=document.getElementById('composer'), input=document.getElementById('text');
const quickform=document.getElementById('quickform'), quicktext=document.getElementById('quicktext');

const WS_PORT = location.protocol==='https:' ? 8444 : 8767;
const WS_URL = (location.protocol==='https:'?'wss':'ws')+'://'+location.hostname+':'+WS_PORT;
const LABELS={idle:'Ready',connecting:'Connecting…',listening:'Listening',thinking:'Thinking',speaking:'Speaking'};

let ws=null,micStream=null,audioCtx=null,micSrc=null,procNode=null,muteGain=null;
let streaming=false,partialBubble=null,partialText="";
let botBubble=null,botText="",userCommitted=false;
let spoke=false,silenceMs=0,awaitingFinal=false;
let audioQueue=[],playing=false,currentAudio=null;
// Client-side end-of-utterance fallback. Kept above the server's own endpointing
// so a natural pause inside a sentence doesn't split it into several messages.
let endpointMs=1200;
let asrCatalog=null, asrPoll=null, brainCatalog=null;
let micDeviceId=''; try{ micDeviceId=localStorage.getItem('jarvis.micDeviceId')||''; }catch(e){}

function state(s){ app.dataset.state=s; statusEl.textContent=LABELS[s]||s; const c=document.getElementById('caption'); if(c) c.textContent=LABELS[s]||s; }
function view(v){ app.dataset.view=v; pop.hidden=(v==='none'); if(v!=='chat') app.dataset.full='false'; if(v==='input') quicktext.focus(); }
function el(c){const d=document.createElement('div');d.className='msg '+c;return d;}
function notice(t){ if(app.dataset.view==='none') view('chat'); const d=el('bot'); d.textContent=t; log.appendChild(d); log.scrollTop=log.scrollHeight; }
function addUser(t){const d=el('user');d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ensureBot(){ if(botBubble) return botBubble; botBubble=el('bot'); const m=document.createElement('div');m.className='meta';m.style.display='none';botBubble._meta=m;botBubble.appendChild(m); const s=document.createElement('span');botBubble._s=s;botBubble.appendChild(s); botBubble.classList.add('caret'); log.appendChild(botBubble); log.scrollTop=log.scrollHeight; return botBubble; }
function appendBot(t){ const b=ensureBot(); botText+=t; b._s.textContent=botText; log.scrollTop=log.scrollHeight; }
function addTool(n){ const b=ensureBot(); b._meta.style.display='block'; const s=document.createElement('span'); s.className='tool'; s.textContent=n; b._meta.appendChild(s); }
function finishBot(){ if(botBubble) botBubble.classList.remove('caret'); }
function resetTurn(){ partialBubble=null; partialText=""; botBubble=null; botText=""; userCommitted=false; }
function setPartial(t){ if(!partialBubble){ partialBubble=el('partial'); log.appendChild(partialBubble); } partialBubble.textContent=t; partialText=t; log.scrollTop=log.scrollHeight; }
function commitPartial(){ if(partialBubble && partialText.trim()){ partialBubble.remove(); addUser(partialText.trim()); userCommitted=true; } else if(partialBubble){ partialBubble.remove(); } partialBubble=null; partialText=""; }
function enqueueAudio(b64){ if(!b64) return; audioQueue.push(b64); if(!playing) playNext(); }
function playNext(){ if(!audioQueue.length){ playing=false; if(streaming&&!botBubble) state('listening'); return; } playing=true; state('speaking'); currentAudio=new Audio('data:audio/wav;base64,'+audioQueue.shift()); currentAudio.onended=playNext; currentAudio.play().catch(()=>{playing=false;}); }
function stopAudio(){ audioQueue=[]; playing=false; if(currentAudio){currentAudio.pause(); currentAudio=null;} }

async function sendText(t){ if(!t.trim()) return; resetTurn(); addUser(t); userCommitted=true; ensureBot(); state('thinking');
  try{ const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})}); const d=await r.json();
    if(d.error) appendBot('Error: '+d.error); else { appendBot(d.reply||''); (d.tools||[]).forEach(addTool); enqueueAudio(d.audio); } }
  catch(e){ appendBot('Error: '+e.message); }
  finishBot(); resetTurn(); if(!playing) state('idle'); }
function onFinalize(){ commitPartial(); if(userCommitted){ ensureBot(); state('thinking'); } try{ ws.send(JSON.stringify({type:'finalize'})); }catch(e){} }
function onWs(ev){ const d=JSON.parse(ev.data);
  if(d.type==='partial'){ stopAudio(); if(botBubble){ finishBot(); botBubble=null; botText=""; } setPartial(d.text); }
  else if(d.type==='transcript'){ if(!userCommitted&&d.text.trim()){ commitPartial(); addUser(d.text.trim()); userCommitted=true; } else commitPartial(); ensureBot(); state('thinking'); }
  else if(d.type==='thinking'){ ensureBot(); state('thinking'); }
  else if(d.type==='assistant_delta'){ appendBot(d.text); state('speaking'); }
  else if(d.type==='tool'){ addTool(d.name); }
  else if(d.type==='audio'){ enqueueAudio(d.audio); }
  else if(d.type==='done'){ if(!botText&&d.text) appendBot(d.text); finishBot(); resetTurn(); if(!playing) state(streaming?'listening':'idle'); }
  else if(d.type==='speech_started'){ stopAudio(); }
  else if(d.type==='error'){ notice(d.text||'Voice error'); stopMic(); } }

function startPCM(){ audioCtx=new (window.AudioContext||window.webkitAudioContext)({sampleRate:16000}); const inRate=audioCtx.sampleRate||16000, ratio=inRate/16000; micSrc=audioCtx.createMediaStreamSource(micStream);
  procNode=audioCtx.createScriptProcessor(2048,1,1); muteGain=audioCtx.createGain(); muteGain.gain.value=0;
  procNode.onaudioprocess=e=>{ if(!ws||ws.readyState!==1) return; const f=e.inputBuffer.getChannelData(0);
    // Browsers may ignore the requested 16 kHz rate (notably on Windows); feed the
    // recognizer exactly 16 kHz or it decodes garbage. Linear resample when needed.
    const n=Math.max(1,Math.round(f.length/ratio)); const pcm=new Int16Array(n); let sum=0;
    for(let i=0;i<n;i++){ const pos=i*ratio, i0=Math.floor(pos), a=f[i0]||0, b=f[i0+1]!==undefined?f[i0+1]:a;
      const s=Math.max(-1,Math.min(1,a+(b-a)*(pos-i0))); sum+=s*s; pcm[i]=s<0?s*0x8000:s*0x7FFF; }
    const rms=Math.sqrt(sum/n), frameMs=n*1000/16000;
    if(rms>0.012){ spoke=true; silenceMs=0; awaitingFinal=false; } else if(spoke){ silenceMs+=frameMs; if(silenceMs>endpointMs&&!awaitingFinal){ awaitingFinal=true; spoke=false; onFinalize(); } }
    ws.send(pcm.buffer); };
  micSrc.connect(procNode); procNode.connect(muteGain); muteGain.connect(audioCtx.destination); }
async function startMic(){ if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){ notice('Microphone needs a secure context (HTTPS). Open '+location.href.replace(/^http:/,'https:')+'.'); return; }
  state('connecting');
  const base={echoCancellation:true,noiseSuppression:true,autoGainControl:true};
  try{ micStream=await navigator.mediaDevices.getUserMedia({audio: micDeviceId?Object.assign({},base,{deviceId:{exact:micDeviceId}}):base}); }
  catch(e){ if(micDeviceId){ try{ micStream=await navigator.mediaDevices.getUserMedia({audio:base}); }catch(e2){ notice('Microphone unavailable: '+e2.message); state('idle'); return; } } else { notice('Microphone unavailable: '+e.message); state('idle'); return; } }
  streaming=true; if(app.dataset.view==='none') view('chat');
  try{ ws=new WebSocket(WS_URL); ws.binaryType='arraybuffer'; ws.onopen=()=>{ state('listening'); startPCM(); }; ws.onmessage=onWs; ws.onerror=()=>{ notice('Voice connection failed — is the streaming service running?'); stopMic(); }; ws.onclose=()=>{ if(streaming){ notice('Voice connection closed.'); stopMic(); } }; }
  catch(e){ notice('Streaming unavailable: '+e.message); stopMic(); } }
function stopMic(){ streaming=false; if(ws){ try{ws.send(JSON.stringify({type:'reset'}));ws.close();}catch(e){} ws=null; }
  if(procNode){procNode.disconnect();procNode.onaudioprocess=null;procNode=null;} if(micSrc){micSrc.disconnect();micSrc=null;}
  if(muteGain){muteGain.disconnect();muteGain=null;} if(audioCtx){audioCtx.close();audioCtx=null;} if(micStream){micStream.getTracks().forEach(t=>t.stop());micStream=null;}
  state('idle'); stopAudio(); }

micBtn.onclick=()=>{ streaming?stopMic():startMic(); };
document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>{ view(b.dataset.nav); if(b.dataset.nav==='settings') loadSettings(); });
document.getElementById('btn-full').onclick=()=>{ app.dataset.full = app.dataset.full==='true'?'false':'true'; };
composer.onsubmit=e=>{ e.preventDefault(); const t=input.value; input.value=''; sendText(t); };
quickform.onsubmit=e=>{ e.preventDefault(); const t=quicktext.value; quicktext.value=''; sendText(t); };
document.addEventListener('keydown',e=>{ if(e.key==='Escape'){ if(streaming){ stopMic(); } else { app.dataset.view==='chat' ? view('menu') : view('none'); } } });
document.addEventListener('click',e=>{ const v=app.dataset.view; if((v==='menu'||v==='input'||v==='settings') && !app.contains(e.target)) view('none'); });

let settingsTab='brain';
function showTab(name){ settingsTab=name||settingsTab; document.querySelectorAll('#settings-tabs .tab').forEach(b=>b.setAttribute('aria-selected', b.dataset.tab===settingsTab?'true':'false')); document.querySelectorAll('.tabpane').forEach(p=>p.classList.toggle('active', p.dataset.pane===settingsTab)); if(settingsTab==='voice') loadMics(); if(settingsTab==='brain') loadBrain(); }
async function loadMics(){ const sel=document.getElementById('s-mic'); if(!sel) return;
  let devs=[]; try{ devs=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='audioinput'); }catch(e){}
  if(devs.length && devs.every(d=>!d.label)){ try{ const st=await navigator.mediaDevices.getUserMedia({audio:true}); st.getTracks().forEach(t=>t.stop()); devs=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='audioinput'); }catch(e){} }
  sel.innerHTML=''; const add=(v,t)=>{const o=document.createElement('option');o.value=v;o.textContent=t;sel.appendChild(o);};
  add('','System default');
  devs.forEach((d,i)=>{ if(!d.deviceId||d.deviceId==='default'||d.deviceId==='communications') return; const o=document.createElement('option'); o.value=d.deviceId; o.textContent=d.label||('Microphone '+(i+1)); if(d.deviceId===micDeviceId) o.selected=true; sel.appendChild(o); });
  const cur=devs.find(d=>d.deviceId===micDeviceId), info=document.getElementById('mic-info');
  info.textContent = cur ? ('Using: '+cur.label) : (micDeviceId ? 'Saved microphone is unavailable — using system default.' : ''); }
document.getElementById('s-mic').onchange=()=>{ micDeviceId=document.getElementById('s-mic').value; try{ localStorage.setItem('jarvis.micDeviceId', micDeviceId); }catch(e){} loadMics(); };
document.querySelectorAll('#settings-tabs .tab').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
window.jarvisOpenSettings=function(tab){ view('settings'); loadSettings(); if(tab) showTab(tab); };
window.jarvisToggleMic=function(){ streaming?stopMic():startMic(); };
window.jarvisCancel=function(){ if(streaming) stopMic(); };
async function loadSettings(){ const d=await (await fetch('/settings')).json();
  document.getElementById('s-mode').value=d.response_mode;
  document.getElementById('s-local-row').style.display=d.response_mode==='local'?'block':'none';
  const v=document.getElementById('s-voice'); v.innerHTML=''; (d.voices||[]).forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;if(x===d.tts_voice)o.selected=true;v.appendChild(o);});
  document.getElementById('s-tts-backend').value=d.tts_backend||'kokoro'; v.disabled=(d.tts_backend==='chatterbox');
  document.getElementById('s-cap').value=d.max_spoken_sentences; loadAsr(); loadBrain(); }
async function saveSettings(){ const sel=document.getElementById('s-asr').value, nemo=sel.indexOf('nemo:')===0?sel.slice(5):'';
  const body={ response_mode:document.getElementById('s-mode').value, local_model:document.getElementById('s-local').value, asr_backend:nemo?'nemotron':'sherpa', nemo_model:nemo, tts_backend:document.getElementById('s-tts-backend').value, tts_voice:document.getElementById('s-voice').value, max_spoken_sentences:parseInt(document.getElementById('s-cap').value||'3',10) };
  try{ await fetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); }catch(e){} }
async function loadAsr(){ try{ asrCatalog=await (await fetch('/asr/models')).json(); }catch(e){ return; }
  const d=asrCatalog, sel=document.getElementById('s-asr'), info=document.getElementById('asr-info');
  sel.innerHTML=''; const add=(v,t)=>{const o=document.createElement('option');o.value=v;o.textContent=t;sel.appendChild(o);};
  add('sherpa','Sherpa Zipformer (built-in, offline)');
  const streaming=(d.models||[]).filter(m=>m.streaming);
  if(d.runtime_installed){ streaming.forEach(m=>add('nemo:'+m.name, m.label+(m.size_mb?' — '+m.size_mb+' MB':'')+(m.downloaded?' (installed)':''))); }
  else { add('nemo:__missing__','NVIDIA Nemotron — runtime not installed'); if(sel.lastChild) sel.lastChild.disabled=true; }
  const active=d.active||{};
  if(active.backend==='nemotron'&&active.nemo_model) { const want=streaming.find(m=>m.name===active.nemo_model||m.repo===active.nemo_model); if(want) sel.value='nemo:'+want.name; }
  if(!d.runtime_installed) info.textContent='NVIDIA NeMo-Speech runtime not found. Install it to use Nemotron models.';
  else if(!streaming.length) info.textContent='No ASR models reported by nemo-speech.';
  updateAsrActions(); }
function updateAsrActions(){ const d=asrCatalog||{}, sel=document.getElementById('s-asr').value;
  const install=document.getElementById('s-asr-install'), dl=document.getElementById('s-asr-download'), actions=document.getElementById('asr-actions'), info=document.getElementById('asr-info');
  install.style.display = d.runtime_installed?'none':'block';
  actions.style.display = (!d.runtime_installed||sel.indexOf('nemo:')===0)?'flex':'none';
  let need=false, m=null;
  if(d.runtime_installed&&sel.indexOf('nemo:')===0){ m=(d.models||[]).find(x=>'nemo:'+x.name===sel); need=!!m&&!m.downloaded&&!asrBusy; }
  dl.style.display = need?'block':'none';
  if(m) dl.textContent='Download '+m.label+(m.size_mb?' ('+m.size_mb+' MB)':'');
  if(d.runtime_installed&&sel.indexOf('nemo:')===0&&m&&m.downloaded) info.textContent='Active: '+m.label+' — downloaded.';
  else if(sel==='sherpa') info.textContent='Using the built-in Sherpa Zipformer (no download).'; }
let asrBusy=false;
function fmtMB(b){ return (b/1048576).toFixed(1)+' MB'; }
function asrControls(enabled){ ['s-asr','s-asr-install','s-asr-download','s-local','s-brain-download'].forEach(id=>{ const el=document.getElementById(id); if(el) el.disabled=!enabled; }); }
async function runAsrJob(url,body){ if(asrBusy) return; asrBusy=true; asrControls(false);
  const p=document.getElementById('asr-progress'), bar=document.getElementById('asr-bar'), fill=document.getElementById('asr-bar-fill'), wrap=document.getElementById('asr-progress-wrap');
  const finish=()=>{ asrBusy=false; asrControls(true); updateAsrActions(); };
  try{ const r=await (await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json();
    if(r.error||!r.started){ wrap.style.display='block';
      if(r.installed){ p.textContent='Already installed — no download needed.'; loadAsr(); setTimeout(()=>{ wrap.style.display='none'; }, 2500); }
      else p.textContent=r.error||'could not start';
      finish(); return; } }
  catch(e){ wrap.style.display='block'; p.textContent='error: '+e.message; finish(); return; }
  if(asrPoll) clearInterval(asrPoll);
  wrap.style.display='block'; bar.classList.remove('indet'); fill.style.background='var(--accent)'; fill.style.width='0%'; p.textContent='Starting…';
  asrPoll=setInterval(async()=>{ let s={}; try{ s=await (await fetch('/asr/status')).json(); }catch(e){ return; }
    const verb = s.kind==='install' ? 'Installing NVIDIA runtime… ' : ('Downloading '+(s.label||'model')+'… ');
    if(s.running){
      const total=s.bytes_total||0, done=s.bytes_done||0;
      let pct=null, note='';
      if(total>0 && done>0){ pct=Math.round(100*done/total); note='  ('+fmtMB(done)+' / '+fmtMB(total)+')'; }
      else if(typeof s.percent==='number'){ pct=s.percent; }
      if(pct!=null){ bar.classList.remove('indet'); fill.style.width=Math.max(0,Math.min(100,pct))+'%'; p.textContent=verb+pct+'%'+note; }
      else { bar.classList.add('indet'); fill.style.width=''; p.textContent=verb.replace(/\.\.\. $/,'…'); }
    } else if(s.error){ bar.classList.remove('indet'); fill.style.background='var(--muted)'; fill.style.width='100%'; p.textContent='Failed: '+s.error; clearInterval(asrPoll); asrPoll=null; finish(); }
    else { bar.classList.remove('indet'); fill.style.width='100%'; p.textContent=(s.kind==='install'?'NVIDIA runtime installed.':'Download complete.'); clearInterval(asrPoll); asrPoll=null; finish(); loadAsr(); setTimeout(()=>{ wrap.style.display='none'; }, 3000); }
  }, 1000); }
document.getElementById('s-asr').onchange=()=>{ updateAsrActions(); saveSettings();
  const d=asrCatalog||{}, sel=document.getElementById('s-asr').value;
  if(sel.indexOf('nemo:')===0){ const m=(d.models||[]).find(x=>'nemo:'+x.name===sel);
    if(m&&!m.downloaded&&!asrBusy) runAsrJob('/asr/pull',{name:m.name,repo:m.repo,size:m.size,label:m.label}); } };
document.getElementById('s-asr-install').onclick=()=>runAsrJob('/asr/install',{});
document.getElementById('s-asr-download').onclick=()=>{ const d=asrCatalog||{}, sel=document.getElementById('s-asr').value; if(sel.indexOf('nemo:')===0){ const m=(d.models||[]).find(x=>'nemo:'+x.name===sel)||{}; runAsrJob('/asr/pull',{name:sel.slice(5),repo:m.repo,size:m.size,label:m.label}); } };
async function loadBrain(){ try{ brainCatalog=await (await fetch('/brain/models')).json(); }catch(e){ return; }
  const d=brainCatalog, sel=document.getElementById('s-local');
  sel.innerHTML=''; (d.models||[]).forEach(m=>{ const o=document.createElement('option'); o.value=m.repo; o.textContent=m.label+(m.size_mb?' — '+m.size_mb+' MB':'')+(m.downloaded?' (installed)':''); if(m.repo===d.active) o.selected=true; sel.appendChild(o); });
  updateBrainActions(); }
function updateBrainActions(){ const d=brainCatalog||{}, sel=(document.getElementById('s-local')||{}).value||'', m=(d.models||[]).find(x=>x.repo===sel);
  const dl=document.getElementById('s-brain-download'), actions=document.getElementById('brain-actions'), info=document.getElementById('brain-info');
  const need=!!m&&!m.downloaded&&!asrBusy;
  dl.style.display=need?'block':'none'; actions.style.display=need?'flex':'none';
  if(m) dl.textContent='Download '+m.label+(m.size_mb?' ('+m.size_mb+' MB)':'');
  if(m&&m.downloaded) info.textContent='Installed: '+m.label;
  else if(m) info.textContent='Not downloaded yet — selecting it starts the download.';
  else info.textContent=''; }
async function runBrainJob(body){ if(asrBusy) return; asrBusy=true; asrControls(false);
  const p=document.getElementById('brain-progress'), bar=document.getElementById('brain-bar'), fill=document.getElementById('brain-bar-fill'), wrap=document.getElementById('brain-progress-wrap');
  const finish=()=>{ asrBusy=false; asrControls(true); updateBrainActions(); };
  try{ const r=await (await fetch('/brain/pull',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json();
    if(r.error||!r.started){ wrap.style.display='block';
      if(r.installed){ p.textContent='Already downloaded — no download needed.'; loadBrain(); setTimeout(()=>{wrap.style.display='none';},2500); }
      else p.textContent=r.error||'could not start';
      finish(); return; } }
  catch(e){ wrap.style.display='block'; p.textContent='error: '+e.message; finish(); return; }
  if(asrPoll) clearInterval(asrPoll);
  wrap.style.display='block'; bar.classList.remove('indet'); fill.style.background='var(--accent)'; fill.style.width='0%'; p.textContent='Starting…';
  asrPoll=setInterval(async()=>{ let s={}; try{ s=await (await fetch('/brain/status')).json(); }catch(e){ return; }
    const verb='Downloading '+(s.label||'model')+'… ';
    if(s.running){ const total=s.bytes_total||0, done=s.bytes_done||0; let pct=null,note='';
      if(total>0&&done>0){ pct=Math.round(100*done/total); note='  ('+fmtMB(done)+' / '+fmtMB(total)+')'; }
      if(pct!=null){ bar.classList.remove('indet'); fill.style.width=Math.max(0,Math.min(100,pct))+'%'; p.textContent=verb+pct+'%'+note; }
      else { bar.classList.add('indet'); fill.style.width=''; p.textContent=verb.replace(/\.\.\. $/,'…'); } }
    else if(s.error){ bar.classList.remove('indet'); fill.style.background='var(--muted)'; fill.style.width='100%'; p.textContent='Failed: '+s.error; clearInterval(asrPoll); asrPoll=null; finish(); }
    else { bar.classList.remove('indet'); fill.style.width='100%'; p.textContent='Download complete.'; clearInterval(asrPoll); asrPoll=null; finish(); loadBrain(); setTimeout(()=>{wrap.style.display='none';},3000); } }, 1000); }
document.getElementById('s-local').onchange=()=>{ updateBrainActions(); saveSettings();
  const d=brainCatalog||{}, m=(d.models||[]).find(x=>x.repo===document.getElementById('s-local').value);
  if(m&&!m.downloaded&&!asrBusy) runBrainJob({repo:m.repo,size:m.size,label:m.label}); };
document.getElementById('s-brain-download').onclick=()=>{ const d=brainCatalog||{}, m=(d.models||[]).find(x=>x.repo===document.getElementById('s-local').value)||{}; runBrainJob({repo:m.repo,size:m.size,label:m.label}); };
document.getElementById('s-mode').onchange=()=>{ document.getElementById('s-local-row').style.display=document.getElementById('s-mode').value==='local'?'block':'none'; };
document.getElementById('s-tts-backend').onchange=()=>{ document.getElementById('s-voice').disabled=document.getElementById('s-tts-backend').value==='chatterbox'; };
document.getElementById('s-save').onclick=saveSettings;
document.getElementById('s-preview').onclick=async()=>{ await saveSettings(); try{ const r=await (await fetch('/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'Hi, this is how I sound.'})})).json(); enqueueAudio(r.audio); }catch(e){} };
fetch('/health').catch(()=>{});
fetch('/settings').then(r=>r.json()).then(d=>{ if(d.endpointing_ms) endpointMs=Math.max(1000,parseInt(d.endpointing_ms,10)+200); }).catch(()=>{});
// Preview hooks (docs/screenshots): ?view=menu|chat|input|settings&state=listening&theme=dark
const _q=new URLSearchParams(location.search);
if(_q.get('theme')) document.documentElement.dataset.theme=_q.get('theme');
if(_q.get('state')) state(_q.get('state'));
if(_q.get('view')) view(_q.get('view'));
</script>
</body>
</html>
"""
