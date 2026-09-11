INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>Jarvis</title>
<style>
  :root{
    color-scheme: light dark;
    --bg:#f4f5f7; --card:#ffffff; --fg:#1a1c1f; --muted:#6b7280;
    --line:#e3e5e9; --accent:#2f6fed; --user:#2f6fed; --bot:#eef1f6;
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#111315; --card:#17191d; --fg:#e8eaed; --muted:#9aa0a6; --line:#26282d; --accent:#5b8cff; --user:#2f5fd0; --bot:#22252b; }
  }
  *{ box-sizing:border-box; }
  html,body{ height:100%; }
  body{ margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:transparent; color:var(--fg); }
  #app{ position:fixed; right:16px; bottom:16px; z-index:20; }
  .pill{ display:flex; align-items:center; gap:10px; background:var(--card); border:1px solid var(--line); border-radius:999px; padding:8px 12px 8px 14px; }
  .dot{ width:9px; height:9px; border-radius:50%; background:var(--muted); flex:0 0 auto; }
  .dot.listening{ background:#22a06b; }
  .dot.thinking{ background:#d99100; }
  .dot.speaking{ background:var(--accent); }
  .dot.error{ background:#c0392b; }
  .mic{ display:inline-flex; align-items:center; justify-content:center; width:44px; height:44px; border-radius:50%;
        border:1px solid var(--line); background:var(--card); color:var(--fg); cursor:pointer; font-size:18px; }
  .mic.active{ background:var(--accent); color:#fff; border-color:var(--accent); }
  .iconbtn{ display:inline-flex; align-items:center; justify-content:center; width:34px; height:34px; border-radius:8px;
        border:1px solid transparent; background:transparent; color:var(--muted); cursor:pointer; font-size:15px; }
  .iconbtn:hover{ background:var(--bot); color:var(--fg); }
  .iconbtn.on{ color:var(--fg); border-color:var(--line); }
  .panel{ display:none; flex-direction:column; width:380px; max-width:calc(100vw - 24px); height:560px; max-height:calc(100vh - 40px);
        background:var(--card); border:1px solid var(--line); border-radius:16px; overflow:hidden; }
  #app[data-expanded="true"] .panel{ display:flex; }
  #app[data-expanded="true"] .pill{ display:none; }
  .head{ display:flex; align-items:center; gap:8px; padding:10px 12px; border-bottom:1px solid var(--line); }
  .head .title{ font-weight:600; font-size:14px; }
  .head .status{ margin-left:auto; font-size:12px; color:var(--muted); margin-right:4px; }
  .log{ flex:1; overflow-y:auto; padding:14px; display:flex; flex-direction:column; gap:8px; }
  .log:empty::before{ content:"Say hello."; color:var(--muted); font-size:13px; }
  .msg{ max-width:82%; padding:8px 11px; border-radius:12px; white-space:pre-wrap; word-break:break-word; font-size:14px; }
  .user{ align-self:flex-end; background:var(--user); color:#fff; }
  .partial{ align-self:flex-end; background:var(--user); color:#fff; opacity:.7; font-style:italic; }
  .bot{ align-self:flex-start; background:var(--bot); }
  .meta{ font-size:11px; color:var(--muted); margin-bottom:4px; }
  .tool{ display:inline-block; border:1px solid var(--line); border-radius:6px; padding:0 6px; margin-right:4px; }
  .caret::after{ content:"▋"; color:var(--accent); animation:blink 1s steps(1) infinite; }
  @keyframes blink{ 50%{ opacity:0; } }
  .composer{ display:none; gap:8px; padding:10px 12px; border-top:1px solid var(--line); }
  #app[data-keyboard="true"] .composer{ display:flex; }
  .composer input{ flex:1; min-width:0; background:transparent; border:1px solid var(--line); color:var(--fg); border-radius:9px; padding:9px 11px; outline:none; }
  .composer button{ border:1px solid var(--line); background:transparent; color:var(--fg); border-radius:9px; padding:9px 12px; cursor:pointer; }
  .dock{ display:flex; align-items:center; justify-content:center; gap:14px; padding:12px; border-top:1px solid var(--line); }
  .sheet{ position:absolute; right:0; bottom:76px; width:340px; max-width:calc(100vw - 24px); background:var(--card);
        border:1px solid var(--line); border-radius:14px; padding:14px; display:none; flex-direction:column; gap:10px; }
  .sheet.open{ display:flex; }
  .sheet label{ display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--muted); }
  .sheet select,.sheet input{ background:var(--bg); border:1px solid var(--line); color:var(--fg); border-radius:8px; padding:7px 9px; }
  .sheet .row{ display:flex; gap:8px; }
  .sheet .row button{ flex:1; border:1px solid var(--line); background:transparent; color:var(--fg); border-radius:9px; padding:8px; cursor:pointer; }
  .hint{ margin:0 0 10px; text-align:center; font-size:11px; color:var(--muted); }
  svg{ width:16px; height:16px; display:block; }
</style>
</head>
<body>
<div id="app" data-expanded="false" data-keyboard="false" data-state="idle">

  <div class="pill" id="pill">
    <span class="dot" id="pill-dot"></span>
    <button class="mic" id="pill-mic" aria-label="Talk">◉</button>
  </div>

  <section class="panel">
    <header class="head">
      <button class="iconbtn" id="btn-chat" title="Chat" aria-label="Chat">☰</button>
      <span class="title">Jarvis</span>
      <span class="status" id="status">idle</span>
      <button class="iconbtn" id="btn-keyboard" title="Keyboard" aria-label="Keyboard">⌨</button>
      <button class="iconbtn" id="btn-settings" title="Settings" aria-label="Settings">⚙</button>
      <button class="iconbtn" id="btn-collapse" title="Collapse" aria-label="Collapse">⌄</button>
    </header>
    <div class="log" id="log"></div>
    <form class="composer" id="composer" autocomplete="off">
      <input id="text" type="text" placeholder="Message Jarvis" />
      <button type="submit">Send</button>
    </form>
    <div class="dock">
      <button class="mic" id="mic" aria-label="Talk">◉</button>
    </div>
    <p class="hint" id="hint">Tap the mic and speak</p>

    <div class="sheet" id="sheet">
      <label>Response brain
        <select id="s-mode"><option value="local">On-device</option><option value="api">API</option></select>
      </label>
      <label id="s-local-row">On-device model <select id="s-local"></select></label>
      <label>Voice <select id="s-voice"></select></label>
      <label>TTS engine <select id="s-tts-backend"><option value="chatterbox">Chatterbox (natural)</option><option value="kokoro">Kokoro (fast)</option></select></label>
      <label>Max spoken sentences <input id="s-cap" type="number" min="1" max="10" /></label>
      <div class="row">
        <button id="s-save">Save</button>
        <button id="s-preview">Preview voice</button>
      </div>
      <div class="row"><button id="s-close">Close settings</button></div>
    </div>
  </section>
</div>

<script>
const app=document.getElementById('app'), log=document.getElementById('log');
const statusEl=document.getElementById('status'), dot=document.getElementById('pill-dot');
const micBtn=document.getElementById('mic'), pillMic=document.getElementById('pill-mic');
const sheet=document.getElementById('sheet'), composer=document.getElementById('composer'), input=document.getElementById('text');

const WS_PORT = location.protocol==='https:' ? 8444 : 8767;
const WS_URL = (location.protocol==='https:'?'wss':'ws')+'://'+location.hostname+':'+WS_PORT;

let ws=null,micStream=null,audioCtx=null,micSrc=null,procNode=null,muteGain=null;
let streaming=false,partialBubble=null,partialText="";
let botBubble=null,botText="",userCommitted=false;
let spoke=false,silenceMs=0,awaitingFinal=false;
let audioQueue=[],playing=false,currentAudio=null;

function state(s,label){ app.dataset.state=s; statusEl.textContent=label||s; dot.className='dot '+s; }
function el(c){const d=document.createElement('div');d.className='msg '+c;return d;}
function addUser(t){const d=el('user');d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function ensureBot(){ if(botBubble) return botBubble; botBubble=el('bot'); const m=document.createElement('div');m.className='meta';m.style.display='none';botBubble._meta=m;botBubble.appendChild(m); const s=document.createElement('span');botBubble._s=s;botBubble.appendChild(s); botBubble.classList.add('caret'); log.appendChild(botBubble); log.scrollTop=log.scrollHeight; return botBubble; }
function appendBot(t){ const b=ensureBot(); botText+=t; b._s.textContent=botText; log.scrollTop=log.scrollHeight; }
function addToolTool(n){ const b=ensureBot(); b._meta.style.display='block'; const s=document.createElement('span'); s.className='tool'; s.textContent=n; b._meta.appendChild(s); }
function finishBot(){ if(botBubble) botBubble.classList.remove('caret'); }
function resetTurn(){ partialBubble=null; partialText=""; botBubble=null; botText=""; userCommitted=false; }
function setPartial(t){ if(!partialBubble){ partialBubble=el('partial'); log.appendChild(partialBubble); } partialBubble.textContent=t; partialText=t; log.scrollTop=log.scrollHeight; }
function commitPartial(){ if(partialBubble && partialText.trim()){ partialBubble.remove(); addUser(partialText.trim()); userCommitted=true; } else if(partialBubble){ partialBubble.remove(); } partialBubble=null; partialText=""; }

function enqueueAudio(b64){ if(!b64) return; audioQueue.push(b64); if(!playing) playNext(); }
function playNext(){ if(!audioQueue.length){ playing=false; if(streaming&&!botBubble) state('listening','listening'); return; } playing=true; state('speaking','speaking'); currentAudio=new Audio('data:audio/wav;base64,'+audioQueue.shift()); currentAudio.onended=playNext; currentAudio.play().catch(()=>{playing=false;}); }
function stopAudio(){ audioQueue=[]; playing=false; if(currentAudio){currentAudio.pause(); currentAudio=null;} }

async function sendText(t){ if(!t.trim()) return; resetTurn(); addUser(t); userCommitted=true; ensureBot(); state('thinking','thinking');
  try{ const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})}); const d=await r.json();
    if(d.error) appendBot('Error: '+d.error); else { appendBot(d.reply||''); (d.tools||[]).forEach(addToolTool); enqueueAudio(d.audio); } }
  catch(e){ appendBot('Error: '+e.message); }
  finishBot(); resetTurn(); if(!playing) state('idle','idle'); }

function onFinalize(){ commitPartial(); if(userCommitted){ ensureBot(); state('thinking','thinking'); } try{ ws.send(JSON.stringify({type:'finalize'})); }catch(e){} }

function onWs(ev){ const d=JSON.parse(ev.data);
  if(d.type==='partial'){ stopAudio(); if(botBubble){ finishBot(); botBubble=null; botText=""; } setPartial(d.text); }
  else if(d.type==='transcript'){ if(!userCommitted&&d.text.trim()){ commitPartial(); addUser(d.text.trim()); userCommitted=true; } else commitPartial(); ensureBot(); state('thinking','thinking'); }
  else if(d.type==='thinking'){ ensureBot(); state('thinking','thinking'); }
  else if(d.type==='assistant_delta'){ appendBot(d.text); state('speaking','speaking'); }
  else if(d.type==='tool'){ addToolTool(d.name); }
  else if(d.type==='audio'){ enqueueAudio(d.audio); }
  else if(d.type==='done'){ if(!botText&&d.text) appendBot(d.text); finishBot(); resetTurn(); if(!playing) state(streaming?'listening':'idle', streaming?'listening':'idle'); }
  else if(d.type==='speech_started'){ stopAudio(); }
}

function startPCM(){ audioCtx=new (window.AudioContext||window.webkitAudioContext)({sampleRate:16000}); micSrc=audioCtx.createMediaStreamSource(micStream);
  procNode=audioCtx.createScriptProcessor(2048,1,1); muteGain=audioCtx.createGain(); muteGain.gain.value=0;
  procNode.onaudioprocess=e=>{ if(!ws||ws.readyState!==1) return; const f=e.inputBuffer.getChannelData(0); const pcm=new Int16Array(f.length); let sum=0;
    for(let i=0;i<f.length;i++){ const s=Math.max(-1,Math.min(1,f[i])); sum+=s*s; pcm[i]=s<0?s*0x8000:s*0x7FFF; }
    const rms=Math.sqrt(sum/f.length);
    if(rms>0.012){ spoke=true; silenceMs=0; awaitingFinal=false; } else if(spoke){ silenceMs+=128; if(silenceMs>450&&!awaitingFinal){ awaitingFinal=true; spoke=false; onFinalize(); } }
    ws.send(pcm.buffer); };
  micSrc.connect(procNode); procNode.connect(muteGain); muteGain.connect(audioCtx.destination); }

async function startMic(){ if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){ addUser('Microphone needs HTTPS. Open '+location.href.replace(/^http:/,'https:')+'.'); return; }
  try{ micStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}}); }
  catch(e){ addUser('Microphone unavailable: '+e.message); return; }
  streaming=true; micBtn.classList.add('active'); pillMic.classList.add('active'); state('connecting','connecting');
  try{ ws=new WebSocket(WS_URL); ws.binaryType='arraybuffer'; ws.onopen=()=>{ state('listening','listening'); startPCM(); }; ws.onmessage=onWs; ws.onerror=()=>addUser('(streaming unavailable)'); }
  catch(e){ addUser('Streaming unavailable: '+e.message); } }

function stopMic(){ streaming=false; if(ws){ try{ws.send(JSON.stringify({type:'reset'}));ws.close();}catch(e){} ws=null; }
  if(procNode){procNode.disconnect();procNode.onaudioprocess=null;procNode=null;} if(micSrc){micSrc.disconnect();micSrc=null;}
  if(muteGain){muteGain.disconnect();muteGain=null;} if(audioCtx){audioCtx.close();audioCtx=null;} if(micStream){micStream.getTracks().forEach(t=>t.stop());micStream=null;}
  micBtn.classList.remove('active'); pillMic.classList.remove('active'); state('idle','idle'); stopAudio(); }

function toggleMic(){ streaming?stopMic():startMic(); }
micBtn.onclick=toggleMic; pillMic.onclick=()=>{ app.dataset.expanded='true'; toggleMic(); };

document.getElementById('btn-chat').onclick=()=>{ app.dataset.expanded='true'; };
document.getElementById('btn-collapse').onclick=()=>{ app.dataset.expanded='false'; sheet.classList.remove('open'); };
document.getElementById('btn-keyboard').onclick=()=>{ const on=app.dataset.keyboard==='true'; app.dataset.keyboard=on?'false':'true'; document.getElementById('btn-keyboard').classList.toggle('on',!on); if(!on) input.focus(); };
document.getElementById('btn-settings').onclick=()=>{ sheet.classList.toggle('open'); if(sheet.classList.contains('open')) loadSettings(); };
document.getElementById('s-close').onclick=()=>sheet.classList.remove('open');
document.getElementById('s-mode').onchange=()=>{ document.getElementById('s-local-row').style.display=document.getElementById('s-mode').value==='local'?'flex':'none'; };
document.getElementById('s-tts-backend').onchange=()=>{ document.getElementById('s-voice').disabled=document.getElementById('s-tts-backend').value==='chatterbox'; };
composer.onsubmit=e=>{ e.preventDefault(); const t=input.value; input.value=''; sendText(t); };

async function loadSettings(){ const d=await (await fetch('/settings')).json();
  document.getElementById('s-mode').value=d.response_mode;
  const lm=document.getElementById('s-local'); lm.innerHTML=''; (d.local_models||[]).forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m.split('/').pop();if(m===d.local_model)o.selected=true;lm.appendChild(o);});
  document.getElementById('s-local-row').style.display=d.response_mode==='local'?'flex':'none';
  const v=document.getElementById('s-voice'); v.innerHTML=''; (d.voices||[]).forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;if(x===d.tts_voice)o.selected=true;v.appendChild(o);});
  document.getElementById('s-tts-backend').value=d.tts_backend||'kokoro'; v.disabled=(d.tts_backend==='chatterbox');
  document.getElementById('s-cap').value=d.max_spoken_sentences; }
async function saveSettings(){ const body={ response_mode:document.getElementById('s-mode').value, local_model:document.getElementById('s-local').value, tts_backend:document.getElementById('s-tts-backend').value, tts_voice:document.getElementById('s-voice').value, max_spoken_sentences:parseInt(document.getElementById('s-cap').value||'3',10) };
  try{ await fetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); }catch(e){} }
document.getElementById('s-save').onclick=saveSettings;
document.getElementById('s-preview').onclick=async()=>{ await saveSettings(); try{ const r=await (await fetch('/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'Hi, this is how I sound.'})})).json(); enqueueAudio(r.audio); }catch(e){} };

fetch('/health').catch(()=>{});
</script>
</body>
</html>
"""
