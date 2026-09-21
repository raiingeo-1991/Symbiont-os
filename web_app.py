#!/usr/bin/env python3
"""Local browser UI for Arseni."""
from __future__ import annotations
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from symbiont_core import Symbiont

ROOT = Path(__file__).resolve().parent
LOCK = threading.RLock()
BOT = None

def bot():
    global BOT
    with LOCK:
        if BOT is None:
            BOT = Symbiont(ROOT)
        return BOT

PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Арсений</title><style>
:root{--ink:#edf5ef;--muted:#9eaea5;--line:#2a3b31;--panel:#111a15;--panel2:#19271f;--accent:#8be7ae;--green:#52c77d}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 0 0,#244631,transparent 38%),#08100c;color:var(--ink);font:16px/1.45 Segoe UI,Arial,sans-serif}.shell{max-width:1180px;margin:auto;padding:28px 20px;display:grid;grid-template-columns:280px 1fr;gap:18px}.side,.chat{background:#111a15ee;border:1px solid var(--line);border-radius:22px;box-shadow:0 24px 70px #0007}.side{padding:22px;min-height:630px}.brand{display:flex;gap:12px;align-items:center;margin-bottom:28px}.orb{width:44px;height:44px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#d5ffe5,#59c981 37%,#174b30 72%);box-shadow:0 0 28px #68d99288}.brand h1{font-size:20px;margin:0}.brand p{margin:1px 0 0;color:var(--muted);font-size:13px}.online{color:var(--accent);font-size:13px;margin:0 0 26px}.online:before{content:'●';margin-right:7px}.stat{padding:14px 0;border-top:1px solid var(--line)}.stat b{display:block;font-size:13px;color:var(--muted);font-weight:500}.stat span{display:block;margin-top:4px}.hint{margin-top:30px;color:var(--muted);font-size:13px}.chat{min-height:630px;display:flex;flex-direction:column;overflow:hidden}.top{padding:20px 25px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between}.top strong{font-size:17px}.badge{font-size:12px;border:1px solid #386246;color:var(--accent);padding:5px 9px;border-radius:99px}.messages{padding:25px;display:flex;gap:16px;flex-direction:column;flex:1;overflow:auto}.message{max-width:78%;padding:14px 16px;border-radius:16px;background:var(--panel2);white-space:pre-wrap}.message.you{margin-left:auto;background:#1d5133;border-bottom-right-radius:4px}.message small{display:block;color:var(--muted);font-size:11px;margin-bottom:5px}.composer{padding:18px;border-top:1px solid var(--line);display:flex;gap:10px}.composer input{min-width:0;flex:1;background:#0b120e;border:1px solid #35463c;border-radius:13px;padding:14px 15px;color:var(--ink);font:inherit;outline:none}.composer input:focus{border-color:var(--accent)}button{border:0;background:var(--green);color:#06130a;border-radius:13px;padding:0 20px;font:600 15px inherit;cursor:pointer}button:hover{background:var(--accent)}.typing{color:var(--muted);font-size:13px}@media(max-width:720px){.shell{display:block;padding:12px}.side{min-height:auto;margin-bottom:12px}.side .stat,.hint{display:none}.chat{min-height:72vh}.message{max-width:90%}}
</style></head><body><main class="shell"><aside class="side"><div class="brand"><i class="orb"></i><div><h1 id="name">Арсений</h1><p>Личный цифровой спутник</p></div></div><p class="online">Локально работает</p><div class="stat"><b>Модель</b><span id="model">Проверяем…</span></div><div class="stat"><b>Память</b><span id="memory">—</span></div><div class="stat"><b>Версия ядра</b><span id="core">—</span></div><p class="hint">Ваши сообщения остаются на этом компьютере. Арсений использует локальную модель.</p><p><a href="/memory" style="color:#8be7ae;text-decoration:none;font-weight:600">Открыть память →</a></p></aside><section class="chat"><header class="top"><strong>Диалог с Арсением</strong><span class="badge">личная память</span></header><div id="messages" class="messages"><div class="message"><small>Арсений</small>Привет. Я готов к разговору. Что для вас сейчас важно?</div></div><form class="composer" id="form"><input id="text" autocomplete="off" placeholder="Напишите Арсению…" autofocus><button>Отправить</button></form></section></main><script>
const msgs=document.querySelector('#messages'),input=document.querySelector('#text');function add(text,who){const x=document.createElement('div');x.className='message '+(who==='Вы'?'you':'');x.innerHTML='<small>'+who+'</small>';x.append(document.createTextNode(text));msgs.append(x);msgs.scrollTop=msgs.scrollHeight;return x}async function status(){try{const d=await (await fetch('/api/status')).json();name.textContent=d.name||'Арсений';model.textContent=d.model||'не подключена';memory.textContent=(d.memory_count||0)+' записей';core.textContent='v'+(d.core||'—')}catch(e){model.textContent='нет соединения'}}status();document.querySelector('#form').addEventListener('submit',async e=>{e.preventDefault();const text=input.value.trim();if(!text)return;add(text,'Вы');input.value='';input.disabled=true;const wait=add('Думаю…','Арсений');wait.classList.add('typing');try{const d=await (await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})})).json();wait.remove();add(d.response||d.error||'Не удалось получить ответ.','Арсений');status()}catch(err){wait.remove();add('Не удалось связаться с Арсением.','Арсений')}finally{input.disabled=false;input.focus()}});
</script></body></html>'''

MEMORY_PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Память Арсения</title><style>body{margin:0;background:#08100c;color:#edf5ef;font:16px/1.45 Segoe UI,Arial,sans-serif}.wrap{max-width:900px;margin:auto;padding:32px 20px}a{color:#8be7ae;text-decoration:none}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}h1{margin:0;font-size:28px}.sub{color:#9eaea5;margin:6px 0 0}.list{display:grid;gap:12px}.card{background:#111a15;border:1px solid #2a3b31;border-radius:16px;padding:17px}.kind{display:inline-block;color:#8be7ae;border:1px solid #386246;border-radius:99px;padding:3px 9px;font-size:12px;margin-bottom:9px}.text{white-space:pre-wrap;font-size:17px}.meta{color:#9eaea5;font-size:12px;margin-top:10px}.empty{color:#9eaea5;padding:25px;border:1px dashed #2a3b31;border-radius:16px}</style></head><body><main class="wrap"><header class="top"><div><h1>Память Арсения</h1><p class="sub">Сохранённое остаётся на этом компьютере.</p></div><a href="/">← Чат</a></header><section id="list" class="list"><p class="empty">Загружаю память…</p></section></main><script>const names={principle:'принцип',preference:'предпочтение',open_loop:'незакрытое дело',dialog:'диалог',general:'запись'};fetch('/api/memories').then(r=>r.json()).then(d=>{const list=document.querySelector('#list');list.innerHTML='';if(!d.memories||!d.memories.length){list.innerHTML='<p class="empty">Пока нет сохранённых записей. Напишите Арсению в чате — сообщение появится здесь.</p>';return}d.memories.forEach(m=>{const x=document.createElement('article');x.className='card';x.innerHTML='<span class="kind">'+(names[m.kind]||m.kind)+'</span><div class="text"></div><div class="meta">Важность: '+m.importance+' из 10</div>';x.querySelector('.text').textContent=m.text;list.append(x)})}).catch(()=>document.querySelector('#list').innerHTML='<p class="empty">Не удалось загрузить память.</p>');</script></body></html>'''
class App(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def output(self, data, code=HTTPStatus.OK):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if urlparse(self.path).path == '/api/memories':
            try:
                records = get_arseniy().memory.all_memories(limit=100)
                self.send_json({'memories': [{'text': r['text'], 'kind': r['kind'], 'importance': r['importance']} for r in records]})
            except Exception as error:
                self.send_json({'error': str(error)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if urlparse(self.path).path == '/memory':
            raw = MEMORY_PAGE.encode('utf-8'); self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(raw)))
            self.end_headers(); self.wfile.write(raw); return
        if urlparse(self.path).path == '/api/status':
            try:
                state = bot().status(); llm = state.get('llm', {})
                self.output({'name':state['agent']['name'],'core':state['core'],'memory_count':state['memory_count'],'model':llm.get('model') if llm.get('available') else 'не подключена'})
            except Exception as e: self.output({'error':str(e)},HTTPStatus.SERVICE_UNAVAILABLE)
        elif urlparse(self.path).path == '/':
            raw=PAGE.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        else: self.send_error(404)
    def do_POST(self):
        if urlparse(self.path).path != '/api/chat': self.send_error(404); return
        try:
            text=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode('utf-8')).get('text','').strip()
            if not text: self.output({'error':'Введите сообщение.'},HTTPStatus.BAD_REQUEST); return
            with LOCK:
                a=bot();a.remember(text,kind='dialog',importance=5);answer=a.speak(text)
            self.output({'response':answer.get('response','Не удалось сформировать ответ.')})
        except Exception as e: self.output({'error':'Ошибка: '+str(e)},HTTPStatus.INTERNAL_SERVER_ERROR)

if __name__ == '__main__':
    print('Арсений открыт: http://127.0.0.1:8765')
    ThreadingHTTPServer(('127.0.0.1',8765),App).serve_forever()

