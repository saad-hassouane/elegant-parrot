"""Local web UI to test the PII gate with your real config.

    .venv/bin/python scripts/pii_playground.py [--port 8766] [--no-browser]

Binds 127.0.0.1 only. Uses the detectors from ~/.config/elegant-parrot/config.toml, so what you see
here is exactly what the hotkey will do. Nothing is logged or written to disk."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import time
import webbrowser
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corrector.config import Settings  # noqa: E402
from corrector.factory import build_gate  # noqa: E402
from corrector.generalizer import Generalizer  # noqa: E402
from corrector.anonymize import AnonymizePipeline, verify_audit_chain  # noqa: E402
from corrector.providers import OpenAICompatProvider  # noqa: E402
from corrector.providers import make_provider  # noqa: E402
from pii_gate.gate import TOKEN_RE, OutboundBlocked  # noqa: E402

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PII Gate Playground</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1c2330;--mut:#667085;--bd:#d9dde5;--acc:#2f6fed;--ok:#157f3b;--bad:#c0392b;--hl:#fde68a}
@media(prefers-color-scheme:dark){:root{--bg:#12151b;--card:#1b2029;--fg:#e6e9ef;--mut:#98a2b3;--bd:#2d3441;--acc:#6b9bff;--ok:#4ade80;--bad:#f87171;--hl:#665c1e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:20px;margin:0 0 4px}p.sub{color:var(--mut);margin:0 0 16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:0 0 8px}
textarea{width:100%;min-height:150px;resize:vertical;background:transparent;color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:10px;font:14px/1.5 ui-monospace,monospace}
.out{white-space:pre-wrap;word-break:break-word;font:14px/1.6 ui-monospace,monospace;min-height:60px}
mark{background:var(--hl);color:inherit;border-radius:3px;padding:0 2px}
.tok{background:color-mix(in srgb,var(--acc) 20%,transparent);border-radius:3px;padding:0 2px}
button{background:var(--acc);color:#fff;border:0;border-radius:8px;padding:8px 14px;font:inherit;cursor:pointer}
button.sec{background:transparent;color:var(--fg);border:1px solid var(--bd)}button:disabled{opacity:.5}
.row{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;align-items:center}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:4px 6px;border-bottom:1px solid var(--bd);vertical-align:top}
th{color:var(--mut);font-weight:500}code{font:13px ui-monospace,monospace}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;border:1px solid var(--bd)}
.ok{color:var(--ok);border-color:var(--ok)}.bad{color:var(--bad);border-color:var(--bad)}
.full{grid-column:1/-1}.mut{color:var(--mut)}
</style></head><body><main>
<h1>PII Gate Playground</h1>
<p class="sub">Runs your real gate config. Type text, see what is detected, what would be sent out, and whether it restores safely.</p>
<div class="card full"><h2>1 · Input</h2>
<textarea id="inp">Hi, I'm Marie Dupont (marie.dupont@acme.fr, +33 6 12 34 56 78). Please wire 1200 EUR to FR76 3000 6000 0112 3456 7890 189. Card 4111 1111 1111 1111. Server at 192.168.1.20, see https://intranet.acme.fr/doc. I recieve teh invoice yesterday.</textarea>
<div class="row"><button id="go">Protect</button><button class="sec" id="ex1">Example: FR</button><button class="sec" id="ex2">Example: EN</button><label class="mut"><input type="checkbox" id="strict"> strict (external) profile: also mask health / religion / roles / relations</label><span id="cfg" class="mut"></span></div></div>
<div class="grid" style="margin-top:14px">
<div class="card"><h2>2 · Detected</h2><div id="hl" class="out mut">—</div>
<table id="tbl" style="margin-top:10px"></table></div>
<div class="card"><h2>3 · Safe text (what leaves your machine)</h2><div id="safe" class="out mut">—</div>
<div class="row"><span id="outbound"></span></div></div>
<div class="card full"><h2>4 · Model output → restore</h2>
<p class="mut" style="margin:0 0 8px">Edit the text below to simulate a model mangling or dropping a placeholder, or send the safe text to your configured model.</p>
<textarea id="resp" placeholder="Run Protect first…"></textarea>
<div class="row"><button id="restore" disabled>Restore</button><button class="sec" id="llm" disabled>Send safe text to configured model</button><span id="llmst" class="mut"></span></div>
<div id="rest" class="out" style="margin-top:6px"></div><div id="probs"></div></div>
<div class="card full"><h2>5 · Layer 3 — local Llama generalizer (optional)</h2>
<p class="mut" style="margin:0 0 8px">Rewrites roles, relations and health/financial context into generic wording using the <b>local</b> Ollama model only, then verifies the result (no invented tokens, no vaulted value, detectors re-scan clean). Slow on CPU.</p>
<div class="row"><button class="sec" id="gen" disabled>Generalize safe text locally</button><span id="genst" class="mut"></span></div>
<div id="genout" class="out" style="margin-top:6px"></div><div id="genprobs"></div></div>
<div class="card full"><h2>6 · Anonymize for external transmission (automated checks)</h2>
<p class="mut" style="margin:0 0 8px">Runs strict masking → local rewrite → automated guardrails (0 placeholders, detectors clean, no digit runs, no proper-noun fingerprint). If every check passes the text is released automatically and the vault is destroyed; if any fails it stays local. The audit log stores no text. <b>These checks are heuristics, not a legal proof of anonymity — confirm with your DPO before skipping a DPA.</b></p>
<div class="row"><button id="anon">Run anonymization pipeline on the input above</button><span id="anonst" class="mut"></span><span id="aud" class="pill"></span></div>
<div id="checks"></div><div id="anontext" class="out" style="margin-top:6px"></div>
<div class="row"><button class="sec" id="send" disabled>Send released text to external model</button><span id="sendst" class="mut"></span></div>
<div id="reply" class="out"></div></div>
</main>
<script>
let sid=null;const $=id=>document.getElementById(id);
const EX={ex1:"Bonjour, je suis Karim Benali, mon email est karim.benali@societe.fr et mon IBAN FR76 3000 6000 0112 3456 7890 189. Appelez-moi au 06 12 34 56 78. J'ai recu votre message hier et je suis alé au magazin.",
ex2:"Hello, this is John Smith from Acme. Reach me at john.smith@acme.com or 415-555-0199. My SSN is 078-05-1120 and the server is 10.0.0.12. Teh report were finished yesterday."};
$('ex1').onclick=()=>$('inp').value=EX.ex1;$('ex2').onclick=()=>$('inp').value=EX.ex2;
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
async function api(p,b){const t0=performance.now();const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await r.json();j._rt=Math.round(performance.now()-t0);return j}
function lat(d){return d.ms!=null?d.ms+' ms server · '+d._rt+' ms round-trip':d._rt+' ms round-trip'}
$('go').onclick=async()=>{
  const text=$('inp').value;$('go').disabled=true;
  const d=await api('/api/protect',{text,strict:$('strict').checked});$('go').disabled=false;
  if(d.error){alert(d.error);return}
  sid=d.session;
  const hl=$('hl');hl.className='out';hl.replaceChildren();let pos=0;
  d.spans.forEach(s=>{hl.append(text.slice(pos,s.start));const m=el('mark',null,text.slice(s.start,s.end));m.title=s.kind;hl.append(m);pos=s.end});
  hl.append(text.slice(pos));if(!d.spans.length)hl.append('\n(nothing detected)');
  const t=$('tbl');t.replaceChildren();
  const h=el('tr');['Kind','Original','Token'].forEach(x=>h.append(el('th',null,x)));t.append(h);
  d.spans.forEach(s=>{const r=el('tr');r.append(el('td',null,s.kind));const c=el('td');c.append(el('code',null,s.text));r.append(c);const c2=el('td');c2.append(el('code',null,s.token));r.append(c2);t.append(r)});
  const sf=$('safe');sf.className='out';sf.replaceChildren();let p2=0;
  for(const m of d.safe_text.matchAll(/⟦[A-Z]+_[A-Z2-9]{5}⟧/g)){sf.append(d.safe_text.slice(p2,m.index));sf.append(el('span','tok',m[0]));p2=m.index+m[0].length}
  sf.append(d.safe_text.slice(p2));
  const ob=$('outbound');ob.replaceChildren();
  ob.append(el('span','pill '+(d.outbound_ok?'ok':'bad'),d.outbound_ok?'outbound check: clean':'outbound check: BLOCKED — '+d.outbound_problem));
  ob.append(el('span','pill',' ⏱ detect+mask: '+lat(d)));
  $('resp').value=d.safe_text;$('restore').disabled=false;$('llm').disabled=!d.outbound_ok;$('gen').disabled=false;$('genout').replaceChildren();$('genprobs').replaceChildren();$('genst').textContent='';
  $('rest').replaceChildren();$('probs').replaceChildren();
};
$('restore').onclick=async()=>{
  const d=await api('/api/restore',{session:sid,text:$('resp').value});
  if(d.error){alert(d.error+' — run Protect again');return}
  const r=$('rest');r.replaceChildren(d.text);const pr=$('probs');pr.replaceChildren();
  pr.append(el('span','pill '+(d.ok?'ok':'bad'),d.ok?'restore OK — safe to inject':'restore FAILED — would abort'));
  pr.append(el('span','pill',' ⏱ restore: '+lat(d)));
  d.problems.forEach(x=>pr.append(el('div','mut',x)));
  $('restore').disabled=true;sid=null;$('llm').disabled=true;
};
$('llm').onclick=async()=>{
  $('llmst').textContent='waiting for model…';$('llm').disabled=true;
  const d=await api('/api/llm',{session:sid,text:$('resp').value});
  $('llm').disabled=false;
  if(d.error){$('llmst').textContent='error: '+d.error;return}
  $('llmst').textContent='model: '+d.model+' ('+d.backend+') · ⏱ '+lat(d);$('resp').value=d.text;
};
$('gen').onclick=async()=>{
  $('genst').textContent='local model working… (can take a minute on CPU)';$('gen').disabled=true;
  const d=await api('/api/generalize',{session:sid});
  $('gen').disabled=false;
  if(d.error){$('genst').textContent='error: '+d.error;return}
  $('genst').textContent='model: '+d.model+' · ⏱ '+lat(d);
  $('genout').textContent=d.text;const g=$('genprobs');g.replaceChildren();
  g.append(el('span','pill '+(d.ok?'ok':'bad'),d.ok?'verified: safe to send onward':'verification FAILED — do not send'));
  d.problems.forEach(x=>g.append(el('div','mut',x)));
};
let job=null;
function audit(){fetch('/api/audit').then(r=>r.json()).then(a=>{const e=$('aud');e.className='pill '+(a.chain_ok?'ok':'bad');e.textContent='audit log: '+a.entries+' entries, chain '+(a.chain_ok?'intact':'BROKEN')})}
$('anon').onclick=async()=>{
  $('anon').disabled=true;$('anonst').textContent='running locally… (about a minute on CPU)';$('send').disabled=true;
  $('anontext').textContent='';$('reply').textContent='';$('sendst').textContent='';
  const d=await api('/api/anon/start',{text:$('inp').value});$('anon').disabled=false;
  const c=$('checks');c.replaceChildren();
  if(d.error){$('anonst').textContent='error: '+d.error;return}
  job=d.job;$('anonst').textContent='model: '+d.model+' · ⏱ '+lat(d);
  const names=Object.keys(d.checks);
  c.append(el('span','pill '+(names.length?'bad':'ok'),names.length?'KEPT LOCAL — '+names.length+' check(s) failed':'all automated checks passed — awaiting your review'));
  names.forEach(n=>c.append(el('div','mut',n+': '+d.checks[n])));
  if(d.status==='RELEASED'){$('anontext').textContent=d.text;$('send').disabled=false;c.append(el('div','mut','released after automated checks · vault destroyed'))}
  audit();
};
$('send').onclick=async()=>{$('send').disabled=true;$('sendst').textContent='sending the released text…';
  const d=await api('/api/anon/send',{job});
  if(d.error){$('sendst').textContent='error: '+d.error;return}
  $('sendst').textContent='sent';$('reply').textContent=d.reply;audit()};
audit();
fetch('/api/info').then(r=>r.json()).then(i=>{$('cfg').textContent='detectors: '+i.detectors.join(', ')+' · backend: '+i.backend+' · model: '+i.model});
</script></body></html>"""


def build(port: int, ttl: float = 600.0) -> ThreadingHTTPServer:
    settings = Settings.load()
    gate = build_gate(settings)
    from dataclasses import replace
    gate_strict = build_gate(replace(settings, backend="external", pii={**settings.pii, "special_category": "mask"}))
    provider = make_provider(settings)
    backend = settings.backend
    model = settings.ollama_model if backend == "local" else settings.external_model
    sessions: dict[str, tuple[object, float]] = {}
    masked: dict[str, str] = {}
    generalizer = Generalizer(settings)  # local Ollama only (refuses non-loopback URLs)
    pipe = AnonymizePipeline(gate_strict, generalizer)
    lock = threading.Lock()

    def sweep() -> None:
        now = time.time()
        for k in [k for k, (_, t) in sessions.items() if now - t > ttl]:
            sessions.pop(k)[0].close()  # type: ignore[attr-defined]

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:  # never log payloads
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if self.path == "/api/info":
                names = [type(getattr(d, "inner", d)).__name__ for d in getattr(gate.detector, "detectors", [gate.detector])]
                return self._json(200, {"detectors": names, "backend": backend, "model": model})
            if self.path == "/api/audit":
                ok, n = verify_audit_chain()
                return self._json(200, {"chain_ok": ok, "entries": n})
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            # Reject cross-site requests (a web page could otherwise POST to localhost).
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                return self._json(403, {"error": "forbidden"})
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                with lock:
                    sweep()
                    if self.path == "/api/protect":
                        t0 = time.perf_counter()
                        text = req["text"]
                        g = gate_strict if req.get("strict") else gate
                        s = g.session()
                        spans = sorted(g.detector.detect(text), key=lambda x: x.start)
                        safe = s.protect(text)
                        toks = TOKEN_RE.findall(safe)  # tokens appear in the same order as spans
                        rows = [{"kind": sp.kind, "start": sp.start, "end": sp.end, "text": text[sp.start:sp.end],
                                 "token": f"⟦{k}_{i}⟧"} for sp, (k, i) in zip(spans, toks)]
                        ok, prob = True, ""
                        try:
                            s.check_outbound(safe)
                        except OutboundBlocked as exc:
                            ok, prob = False, str(exc)
                        sid = secrets.token_urlsafe(16)
                        sessions[sid] = (s, time.time())
                        masked[sid] = safe
                        return self._json(200, {"session": sid, "safe_text": safe, "spans": rows,
                                                "outbound_ok": ok, "outbound_problem": prob,
                                                "ms": round((time.perf_counter() - t0) * 1000)})
                    if self.path == "/api/restore":
                        entry = sessions.pop(req["session"], None)
                        masked.pop(req["session"], None)
                        if not entry:
                            return self._json(404, {"error": "unknown or expired session"})
                        t0 = time.perf_counter()
                        r = entry[0].restore(req["text"])  # type: ignore[attr-defined]
                        entry[0].close()  # type: ignore[attr-defined]
                        return self._json(200, {"ok": r.ok, "text": r.text, "problems": r.problems,
                                                "ms": round((time.perf_counter() - t0) * 1000)})
                    if self.path == "/api/llm":
                        if req["session"] not in sessions:
                            return self._json(404, {"error": "unknown or expired session"})
                if self.path == "/api/anon/start":
                    j = pipe.start(req["text"])
                    return self._json(200, {"job": j.id, "status": j.status, "checks": j.checks, "kinds": j.kinds,
                                            "text": j.candidate if j.status == "RELEASED" else "", "ms": j.ms, "model": j.model})
                if self.path == "/api/anon/send":
                    try:
                        text = pipe.mark_sent(req["job"], "external")
                    except KeyError as exc:
                        return self._json(404, {"error": str(exc)})
                    try:  # only text released by the automated checks goes out
                        out = OpenAICompatProvider(replace(settings, backend="external")).correct(text)
                        return self._json(200, {"status": "SENT", "sent": text, "reply": out})
                    except Exception as exc:  # noqa: BLE001
                        return self._json(502, {"error": str(exc)[:200], "sent": text})
                if self.path == "/api/generalize":
                    with lock:
                        entry = sessions.get(req["session"])
                        text = masked.get(req["session"])
                    if not entry or text is None:
                        return self._json(404, {"error": "unknown or expired session"})
                    try:
                        g = generalizer.generalize(entry[0], text)  # type: ignore[arg-type]
                        return self._json(200, {"text": g.text, "ok": g.ok, "problems": g.problems,
                                                "model": g.model, "ms": g.ms})
                    except Exception as exc:  # noqa: BLE001
                        return self._json(502, {"error": str(exc)[:200]})
                # Model call outside the lock (slow). Only the masked text is sent.
                if self.path == "/api/llm":
                    try:
                        t0 = time.perf_counter()
                        out = provider.correct(req["text"])
                        return self._json(200, {"text": out, "model": model, "backend": backend,
                                                "ms": round((time.perf_counter() - t0) * 1000)})
                    except Exception as exc:  # noqa: BLE001
                        return self._json(502, {"error": str(exc)[:200]})
                self._json(404, {"error": "not found"})
            except (KeyError, ValueError):
                self._json(400, {"error": "bad request"})

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = build(a.port)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"PII Gate Playground on {url}  (Ctrl+C to stop)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
