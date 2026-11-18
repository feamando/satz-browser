#!/usr/bin/env python3
"""Regenerate docs/design/components.html from src/design-system/icons.ts.
Run from the repo root: python3 scripts/build_components_gallery.py
"""
import re
ic=open('src/design-system/icons.ts').read()
body=ic[ic.index('{')+1:ic.index('} as const')]
pairs=re.findall(r"^\s*'?(\w+)'?:'(.*)',?\s*$",body,re.M)
icons={k:v.rstrip("'") for k,v in pairs}
def I(n,c=''):
    return f'<svg class="ico {c}" viewBox="0 0 24 24" aria-hidden="true">{icons[n]}</svg>'
grid=''.join(f'<div class="ig">{I(n)}<span class="mono">{n}</span></div>' for n in icons)
html=f'''<!doctype html>
<html lang="en" data-layout="floating">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Satz Components</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Besley:wght@700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="../../src/design-system/tokens.css">
<link rel="stylesheet" href="../../src/design-system/components.css">
<style>
/* Gallery-only layout. Do not copy into the app. */
html,body{{margin:0;height:auto}}
body{{padding-block:24px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}}
.g{{max-width:1120px;margin:0 auto;display:flex;flex-direction:column;gap:32px}}
.g-h{{display:flex;align-items:center;gap:16px;flex-wrap:wrap;position:sticky;top:0;z-index:5;padding:10px 0;background:var(--canvas)}}
.g-h h1{{margin:0;font:700 26px/1 var(--font-display)}}
.g-h .seg:first-of-type{{margin-left:auto}}
.g-s{{display:flex;flex-direction:column;gap:12px}}
.g-s > h2{{margin:0;font:700 18px/1.2 var(--font-display)}}
.g-s > p{{margin:0;color:var(--muted);font-size:var(--fs-sm);max-width:70ch}}
.g-row{{display:flex;flex-wrap:wrap;align-items:center;gap:10px}}
.g-box{{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-lg);padding:18px;display:flex;flex-direction:column;gap:14px;min-width:0}}
.g-2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}
.sw{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px}}
.sw div{{border:1px solid var(--line);border-radius:var(--r-md);overflow:hidden;font-size:var(--fs-xs)}}
.sw i{{display:block;height:44px}}
.sw span{{display:block;padding:6px 8px}}
.ig{{display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 4px;border-radius:var(--r-md);font-size:10.5px;color:var(--muted)}}
.ig:hover{{background:var(--hover);color:var(--ink)}}
.igrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:4px}}
.mini-side{{width:232px;position:relative;padding:12px 10px 10px;border:1px dashed var(--line);border-radius:var(--r-lg);display:flex;flex-direction:column}}
.thumb-demo{{background:var(--accent-soft) radial-gradient(circle,var(--accent) 1px,transparent 1.5px) 0 0/5px 5px}}
</style>
</head>
<body class="ds">
<div class="g">
 <div class="g-h">
  <h1>Satz components</h1>
  <span class="faint mono" style="font-size:11px">v1 · 2026-11-18 · spec docs/design/DESIGN_SYSTEM.md</span>
  <div class="seg" role="group" aria-label="Theme"><button id="t-light" data-t="light" aria-pressed="false">Light</button><button id="t-dark" data-t="dark" aria-pressed="false">Dark</button></div>
  <div class="seg" role="group" aria-label="Layout"><button id="l-floating" data-l="floating" aria-pressed="true">Floating</button><button id="l-flush" data-l="flush" aria-pressed="false">Flush</button></div>
 </div>

 <section class="g-s"><h2>2.1 Color</h2><p>Semantic tokens. Components never use hex values.</p>
  <div class="sw">{''.join(f'<div><i style="background:var(--{t})"></i><span class="mono">--{t}</span></div>' for t in ['canvas','panel','sunk','hover','line','ink','muted','faint','accent','accent-soft','good','warn','danger'])}</div>
 </section>

 <section class="g-s"><h2>2.2 Type</h2>
  <div class="g-box">
   <div class="display" style="font-size:var(--fs-2xl)">Where do you want to start?</div>
   <div class="display" style="font-size:var(--fs-xl)">Heating maintenance on 24 Nov</div>
   <div style="font:600 var(--fs-lg) var(--font-ui)">EU grid operators agree on a shared winter reserve</div>
   <div style="font-size:var(--fs-md);max-width:62ch;line-height:var(--lh-read)">Reading text at 13.5px Inter with 1.6 line height. Our technician will service the gas boilers in all units on Tuesday between 08:00 and 12:00.</div>
   <div class="muted" style="font-size:var(--fs-xs)">Meta line · orders lane · Deutsche Bahn · 2h</div>
   <div class="label">Section label <span class="ct">4</span></div>
   <div class="mono" style="font-size:var(--fs-xs)">gemma-4-e4b · conf 7.8 · 182 / 200 · satz://news</div>
  </div>
 </section>

 <section class="g-s"><h2>5.1 Primitives</h2>
  <div class="g-2">
   <div class="g-box">
    <div class="label">Buttons</div>
    <div class="g-row"><button class="btn primary">Send</button><button class="btn">Reply</button><button class="btn ghost">Cancel</button><button class="btn danger">Remove</button><button class="btn" disabled>Disabled</button></div>
    <div class="g-row"><button class="btn-text pri">Open reader</button><button class="btn-text">Perspectives (3)</button><button class="btn-text">Save</button></div>
    <div class="g-row"><button class="icon-btn" title="Home" aria-label="Home">{I('home')}</button><button class="icon-btn on" title="Brain" aria-label="Brain">{I('brain')}</button><button class="icon-btn" title="Telemetry" aria-label="Telemetry">{I('pulse')}<i class="dot"></i></button><button class="icon-btn" title="More" aria-label="More">{I('more')}</button></div>
    <div class="seg" role="group" aria-label="Example"><button aria-pressed="true">1 Email</button><button aria-pressed="false">2 Ping</button><button aria-pressed="false">3 Information</button><button aria-pressed="false">4 Promotion</button></div>
   </div>
   <div class="g-box">
    <div class="label">Inputs</div>
    <input id="d-in" class="input" placeholder="Profile name">
    <div class="form-row"><input id="d-pin" class="input pin" placeholder="PIN" value="••••••"><button class="btn primary">Unlock</button><button class="btn">Unlock with Touch ID</button></div>
    <div class="input-wrap">{I('search')}<input id="d-search" class="input" placeholder="Filter domain, category, rubric"></div>
    <select id="d-sel" class="select"><option>EU grid winter reserve</option></select>
    <div class="slider-row"><span class="muted" style="font-size:var(--fs-sm)">Personal trust</span><input id="d-sl" class="slider" type="range" value="60"><span class="slider-val">6.0</span></div>
   </div>
   <div class="g-box">
    <div class="label">Pills, chips, badges</div>
    <div class="g-row"><span class="pill"><b>dw.com</b> 8.4</span><span class="pill"><b>lemonde.fr</b> 8.1 · fr</span><span class="pill">+2</span></div>
    <div class="g-row"><button class="pill round on">All mail</button><button class="pill round">Personal</button><button class="pill round">Studio</button></div>
    <div class="g-row"><button class="chip">{I('attach','ico-xs')} tab</button><button class="chip">gemma-4 · local {I('chev','ico-xs')}</button></div>
    <div class="g-row"><span class="badge">12</span><span class="badge soft">4 new</span><span class="status"><i class="dot"></i><span class="mono" style="font-size:11px">ready</span></span><span class="status"><i class="dot warn"></i><span class="mono" style="font-size:11px">no key</span></span><span class="status"><i class="dot danger"></i><span class="mono" style="font-size:11px">offline</span></span><span class="status"><i class="dot live"></i><span class="mono" style="font-size:11px">running</span></span></div>
    <div class="g-row" style="font-size:var(--fs-md)">Germany wants pro rata <span class="cite">1</span> and France <span class="cite flagged">3</span><span class="flag">cut</span><span class="flag">translated</span><span class="kbd">⌘K</span></div>
   </div>
   <div class="g-box">
    <div class="label">Banners</div>
    <div class="banner">{I('lock')}<span>Mail is locked. Enter your PIN to read it.</span><button class="btn primary">Unlock</button></div>
    <div class="banner warn">{I('pulse')}<span><b>Gemma is loading.</b> Answers use x-planck until it is warm.</span></div>
    <div class="banner danger">{I('x')}<span><b>Sidecar offline.</b> Restart it from Settings.</span><button class="btn">Retry</button></div>
   </div>
  </div>
 </section>

 <section class="g-s"><h2>5.2 Sidebar, 5.4 Telemetry</h2>
  <div class="g-row" style="align-items:flex-start;gap:24px">
   <div class="mini-side side" style="height:520px">
    <div class="brand"><span class="display" style="font-size:20px">Satz</span><span class="ver">0.6</span></div>
    <div class="quick"><button class="icon-btn on" title="Home" aria-label="Home">{I('home')}</button><button class="icon-btn" title="Command bar" aria-label="Command bar">{I('cmd')}</button><button class="icon-btn" title="New conversation" aria-label="New conversation">{I('compose')}</button></div>
    <div class="acc-wrap">
     <div class="acc open"><button class="acc-h">Pinned <span class="ct">4</span>{I('chev')}</button><div class="acc-b">
      <div class="row on">{I('mail')}<span class="t">Mail</span><span class="badge">12</span></div>
      <div class="row sub"><span class="t">Personal (9)</span><span class="meta">412 msg</span></div>
      <div class="row">{I('news')}<span class="t">News</span><span class="badge soft">4 new</span></div>
      <div class="sep"></div>
      <div class="row">{I('pin')}<span class="t">Berlin flat search</span><span class="meta">6 src</span></div></div></div>
     <div class="acc open"><button class="acc-h">Conversations <span class="ct">2</span>{I('chev')}</button><div class="acc-b">
      <div class="row">{I('chat')}<span class="t">Compare induction hobs</span><i class="dot live"></i></div>
      <div class="row">{I('chat')}<span class="t">Steuererklärung Q&amp;A</span><span class="meta">5h</span><button class="icon-btn row-menu" aria-label="More">{I('more','ico-sm')}</button></div></div></div>
     <div class="acc"><button class="acc-h">Archived <span class="ct">14</span>{I('chev')}</button><div class="acc-b"></div></div>
    </div>
    <div class="foot"><button class="icon-btn" aria-label="Brain">{I('brain')}</button><button class="icon-btn" aria-label="Settings">{I('settings')}</button><button class="icon-btn on" aria-label="Telemetry">{I('pulse')}<i class="dot"></i></button><span class="prof"><span class="avatar">N</span>Nikita</span></div>
    <div class="telemetry-pop">
     <div class="label">Model</div>
     <div class="kv"><span>Active</span><span>gemma-4-e4b</span><span>Gemma</span><span class="status"><i class="dot"></i>warm · gpu</span><span>Privacy</span><span>on-device</span></div>
     <div class="label">Context</div>
     <div class="kv"><span>Sources in context</span><span>14</span><span>Mail processing</span><span>182 / 200</span></div>
     <div class="meter" style="--v:91%"><b></b></div>
    </div>
   </div>
   <div class="g-box" style="flex:1;min-width:300px">
    <div class="label">Menu</div>
    <div class="menu" style="width:220px"><button class="menu-item">{I('compose')}Rename<span class="end">F2</span></button><button class="menu-item">{I('pin')}Unpin</button><button class="menu-item">{I('archive')}Archive</button><div class="sep"></div><button class="menu-item danger">{I('trash')}Delete</button></div>
    <div class="label">Top bar</div>
    <div class="top" style="border:1px solid var(--line);border-radius:var(--r-lg)"><button class="icon-btn" aria-label="Back">{I('back')}</button><button class="icon-btn" aria-label="Forward">{I('fwd')}</button><button class="icon-btn" aria-label="Reload">{I('reload')}</button><div class="addr">{I('globe','ico-sm')}<span class="host">dw.com</span>/en/eu-grid-reserve<span class="kbd">⌘L</span></div><button class="icon-btn" aria-label="Bookmark">{I('star')}</button></div>
    <div class="label">Tabs</div>
    <div class="tabs"><span class="tab">Chat</span><span class="tab on">Inbox <span class="n">12</span></span><span class="tab">Pings <span class="n">31</span></span><span class="tab compare-pick"><span class="t">dw.com</span><button class="close" aria-label="Close">{I('x','ico-xs')}</button></span></div>
   </div>
  </div>
 </section>

 <section class="g-s"><h2>5.6 Composer, 5.8 Home bar</h2>
  <div class="g-box">
   <div class="bigbar"><div class="bigbar-in">{I('cmd')}<input id="d-big" placeholder="url, question, mail: term, brain: term, or a command"><span class="kbd">⌘K</span></div><div class="bigbar-ctl"><button class="chip">{I('attach','ico-xs')} tab</button><button class="chip">gemma-4 · local {I('chev','ico-xs')}</button><button class="send" aria-label="Send">{I('send')}</button></div></div>
   <div class="composer" style="padding:0"><div class="cbox"><span class="pill"><b>dw.com</b> tab<span class="x">{I('x','ico-xs')}</span></span><input id="d-comp" placeholder="Ask about today's news"><button class="chip">{I('attach','ico-xs')}</button><button class="chip">gemma-4 · local {I('chev','ico-xs')}</button><button class="send" aria-label="Send">{I('send')}</button></div><div class="sugg"><button>compare perspectives</button><button>what changed since this morning?</button><button>only Berlin</button></div></div>
   <div class="home-cols"><div><div class="label">For you<span class="end">refresh</span></div>
    <div class="digest"><span class="digest-src">{I('mail')}</span><div class="digest-body"><b>DB refund of €38.90 approved</b><small>orders lane · Deutsche Bahn · 2h</small></div></div>
    <div class="digest"><span class="digest-src">{I('news')}</span><div class="digest-body"><b>EU grid operators agree on shared winter reserve</b><small>3 source families · conf 7.8</small></div><span class="digest-thumb thumb-demo"></span></div></div>
    <div><div class="label">Resume<span class="end">all</span></div><div class="row">{I('chat')}<span class="t">Compare induction hobs</span><span class="meta">4 tabs</span></div><div class="row">{I('pin')}<span class="t">Berlin flat search</span><span class="meta">6 src</span></div></div></div>
  </div>
 </section>

 <section class="g-s"><h2>5.9 Chat thread, 5.10 Agent</h2>
  <div class="g-2">
   <div class="g-box"><div class="thread">
    <div class="msg-you">Where do Germany and France disagree on the reserve?</div>
    <div class="msg-bot"><span class="msg-meta">gemma-4-e4b · 09:41 · 3 sources</span><span class="msg-text">The split is over cost allocation. Germany wants idle capacity paid pro rata <span class="cite">1</span>; France argues exporters should carry more <span class="cite">3</span>.</span><div class="msg-sources"><span>1 · dw.com · 8.4</span><span>3 · lemonde.fr · 8.1 · translated</span></div></div>
    <div class="stream"><span class="stream-now"><i class="dot live"></i>Reading reuters.com</span><span class="stream-step">Planned 3 queries · on-device</span><span class="stream-step">Fetched dw.com, lemonde.fr</span></div>
    <div class="draft"><span class="gate">Draft · sends only after you press Send</span><span>Hallo, der Schlüssel liegt bei Frau Weber, Wohnung 2B.</span><div class="acts"><button class="btn primary">Send</button><button class="btn">Edit</button></div></div>
    <div class="findings"><div class="finding"><span class="thumb-demo" style="height:90px;display:block"></span><div><span>Bosch PIE631</span><span class="price">€449</span></div></div><div class="finding"><span class="thumb-demo" style="height:90px;display:block"></span><div><span>Siemens EH645</span><span class="price">€399</span></div></div></div>
   </div></div>
   <div class="g-box" style="padding:0;overflow:hidden"><div class="agent" style="height:100%">
    <div class="ag-h"><span class="spark-tile">{I('spark')}</span><div class="ag-title"><b>On this tab</b><small>Inbox · message 1 of 12</small></div><button class="icon-btn" aria-label="Fold agent">{I('panel')}</button></div>
    <div class="tabs"><span class="tab on">Chat</span><span class="tab">Sources <span class="n">14</span></span></div>
    <div class="ag-body"><div class="source-row"><div class="source-row-top"><span class="favicon thumb-demo"></span><span class="t">EU grid reserve deal</span><span class="trust">8.4</span></div><div class="source-row-meta">dw.com <span class="flag">cut</span></div></div><div class="source-row"><div class="source-row-top"><span class="favicon thumb-demo"></span><span class="t">Réserve d'hiver commune</span><span class="trust">8.1 · 6.5</span></div><div class="source-row-meta">lemonde.fr</div></div></div>
    <div class="composer"><div class="cbox"><input id="d-ag" placeholder="Ask about this email"><button class="send" aria-label="Send">{I('send')}</button></div></div>
   </div></div>
  </div>
 </section>

 <section class="g-s"><h2>5.11 Cards, tables, 5.13 Mail, 5.14 News</h2>
  <div class="story"><span class="story-thumb thumb-demo"></span><div class="story-c">
   <div class="story-meta"><span class="live">developing · 40m</span><span>energy · EU</span><span class="conf">conf 7.8 <i style="--c:78%"></i></span></div>
   <h3 class="story-title">EU grid operators agree on a shared winter reserve for cross-border shortfalls</h3>
   <ul><li>ENTSO-E members pool 4.2 GW of standby capacity through March.</li><li>Germany and France disagree on who pays for idle reserve.</li></ul>
   <div class="story-foot"><div class="pills"><span class="pill"><b>dw.com</b> 8.4</span><span class="pill"><b>reuters.com</b> 8.9</span><span class="pill" title="lemonde.fr 8.1 · fr">+1</span></div><div class="acts"><button class="btn-text pri">Open reader</button><button class="btn-text">Perspectives (3)</button><button class="btn-text">Save</button><button class="icon-btn" aria-label="More actions">{I('more','ico-sm')}</button></div></div>
  </div></div>
  <div class="g-2">
   <div class="g-box" style="padding:0;overflow:hidden"><div class="mail-list" style="border-right:0">
    <div class="mail-row on"><div class="h"><i class="dot accent"></i><b>Hausverwaltung Kranz</b><span class="time">09:12</span></div><div class="s">Heating maintenance on 24 Nov</div><div class="p">Dear tenants, our technician will service the boilers…</div></div>
    <div class="mail-row read"><div class="h"><b>Finanzamt Berlin</b><span class="time">Mon</span></div><div class="s">Eingangsbestätigung Ihrer Erklärung</div><div class="p">Ihre Einkommensteuererklärung 2025 ist eingegangen…</div></div>
   </div></div>
   <div class="g-box"><h2 class="mail-subject">Heating maintenance on 24 Nov</h2><div class="mail-from"><span class="avatar lg">HK</span><b>Hausverwaltung Kranz</b><span class="when">Wed 18 Nov · 09:12</span></div><div class="extract">{I('cal')}<span><b>Action:</b> be home Tue 24 Nov, 08:00 to 12:00</span><button class="btn primary">Add to calendar</button></div></div>
  </div>
  <div class="table-wrap"><table class="table"><thead><tr><th>Domain</th><th>Category</th><th class="num">System</th><th class="num">Effective</th></tr></thead><tbody><tr><td>dw.com</td><td>public broadcaster</td><td class="num">8.4</td><td class="num">8.6</td></tr><tr><td>euractiv.com</td><td>trade press</td><td class="num">7.4</td><td class="num">7.4</td></tr></tbody></table></div>
  <div class="card"><div class="card-h"><b>Add mail account</b><span class="end"><span class="faint" style="font-size:var(--fs-xs)">Credentials are stored in your encrypted vault</span></span></div><div class="form-row"><input id="d-em" class="input" placeholder="you@gmail.com"><input id="d-pw" class="input" type="password" placeholder="App password"><button class="btn">Test</button><button class="btn primary">Add account</button></div></div>
 </section>

 <section class="g-s"><h2>6 Icons</h2><div class="g-box"><div class="igrid">{grid}</div></div></section>
</div>
<script>
(()=>{{const r=document.documentElement;
 const set=(k,v,attr)=>{{r.setAttribute(attr,v);document.querySelectorAll('[data-'+k+']').forEach(b=>b.setAttribute('aria-pressed',b.dataset[k]===v))}};
 const dark=matchMedia('(prefers-color-scheme: dark)').matches; set('t',dark?'dark':'light','data-theme');
 document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>set('t',b.dataset.t,'data-theme'));
 document.querySelectorAll('[data-l]').forEach(b=>b.onclick=()=>set('l',b.dataset.l,'data-layout'));
 document.querySelectorAll('.acc-h').forEach(h=>h.onclick=()=>h.parentElement.classList.toggle('open'));
}})();
</script>
</body></html>'''
open('docs/design/components.html','w').write(html)
print(len(icons))