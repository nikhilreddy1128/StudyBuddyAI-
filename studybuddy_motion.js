/* StudyBuddyAI Cinematic Motion Engine — dependency-free, parent-document safe. */
(() => {
  'use strict';
  let doc, win;
  try { doc = window.parent.document; win = window.parent; } catch (_) { return; }
  if (!doc || !doc.body || doc.getElementById('studybuddy-fx-dock')) return;
  const reduceMotion = !!(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const $ = (s, root = doc) => root.querySelector(s);
  const el = (tag, attrs = {}, parent) => {
    const n = doc.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => k === 'text' ? n.textContent = v : k === 'html' ? n.innerHTML = v : n.setAttribute(k, v));
    if (parent) parent.appendChild(n);
    return n;
  };
  const style = el('style', {}, doc.head || doc.documentElement);
  style.textContent = ''; // Styling is embedded by the Streamlit host before this engine runs.
  const canvas = el('canvas', {id:'studybuddy-fx-canvas','aria-hidden':'true'}, doc.body);
  const ctx = canvas.getContext('2d', {alpha:true});
  const aura = el('div', {id:'studybuddy-cursor-aura','aria-hidden':'true'}, doc.body);
  const dock = el('nav', {id:'studybuddy-fx-dock','aria-label':'Cinematic effects controls'}, doc.body);
  dock.innerHTML = '<span class="sb-fx-brand"><i class="sb-fx-orb"></i>STUDYVERSE</span><select id="sb-fx-theme" aria-label="Background mood"><option value="nebula">Nebula</option><option value="aurora">Aurora</option><option value="solar">Solar flare</option><option value="eclipse">Eclipse</option></select><button id="sb-fx-particles" aria-pressed="true" title="Toggle interactive particles">✦ FX</button><button id="sb-fx-focus" title="Open distraction-free focus timer">◷ Focus</button><button id="sb-fx-quiet" aria-pressed="false" title="Reduce visual effects">◌ Calm</button>';
  const hud = el('div', {id:'studybuddy-fx-hud','aria-live':'polite'}, doc.body);
  hud.innerHTML = '<span class="sb-hud-mark"></span><span id="sb-fx-hud-text">STUDYVERSE ONLINE · MOVE YOUR POINTER TO INTERACT</span>';
  const toastStack = el('div', {id:'studybuddy-fx-toast-stack','aria-live':'polite','aria-atomic':'false'}, doc.body);
  const overlay = el('div', {id:'studybuddy-fx-overlay','aria-label':'Focus timer'}, doc.body);
  overlay.innerHTML = '<section class="sb-focus-panel"><div class="sb-focus-kicker">STUDYBUDDYAI · DEEP FOCUS</div><div id="sb-focus-clock" class="sb-focus-clock">25:00</div><div id="sb-focus-label" class="sb-focus-label">One thing at a time. You have got this.</div><div class="sb-focus-actions"><button id="sb-focus-start">▶ Start focus</button><button id="sb-focus-reset" class="sb-secondary">↻ Reset</button><button id="sb-focus-close" class="sb-secondary">✕ Close</button></div><p style="color:#8e9fbe;font-size:11px;margin-top:18px">Shortcut: F opens focus · Esc closes · P pauses/resumes</p></section>';
  const themeSelect = $('#sb-fx-theme'), particleButton = $('#sb-fx-particles'), focusButton = $('#sb-fx-focus'), quietButton = $('#sb-fx-quiet');
  const focusClock = $('#sb-focus-clock'), focusLabel = $('#sb-focus-label'), focusStart = $('#sb-focus-start');
  let width=1,height=1,dpr=1,raf=0,last=0,active=true,quiet=false,theme='nebula',mouse={x:-1000,y:-1000,tx:-1000,ty:-1000},particles=[],bursts=[],streaks=[],elapsed=0,focusSeconds=1500,focusRunning=false,focusInterval=null;
  const rand=(a,b)=>a+Math.random()*(b-a), clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const palette = {
    nebula:['#79efff','#b39bff','#ff9ee7','#d7e9ff'], aurora:['#7affc7','#70eaff','#9e9aff','#d5fff0'],
    solar:['#ffd98a','#ff9bcb','#a6c5ff','#fff1cb'], eclipse:['#aebeff','#d7d9ff','#8d9ab8','#c8efff']
  };
  function resize(){
    width=Math.max(1,win.innerWidth||1);height=Math.max(1,win.innerHeight||1);dpr=Math.min(win.devicePixelRatio||1,1.5);
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);canvas.style.width=width+'px';canvas.style.height=height+'px';
    if(ctx)ctx.setTransform(dpr,0,0,dpr,0,0);
    const count=reduceMotion?28:Math.round(clamp(width*height/9000,70,190));
    particles=Array.from({length:count},()=>({x:rand(0,width),y:rand(0,height),r:rand(.45,2.0),vx:rand(-.12,.12),vy:rand(-.19,.08),a:rand(.15,.78),phase:rand(0,Math.PI*2),speed:rand(.4,1.8),depth:rand(.3,1),hue:Math.floor(rand(0,4)),kind:Math.random()<.12?'dust':'star'}));
  }
  function drawBackground(dt,now){
    if(!ctx)return;ctx.clearRect(0,0,width,height);const colors=palette[theme]||palette.nebula;
    // Gentle chromatic fog follows the pointer with a small, smoothed parallax offset.
    const px=mouse.x<0?0:(mouse.x/width-.5)*width*.08,py=mouse.y<0?0:(mouse.y/height-.5)*height*.08;
    const fogs=[[width*.22+px,height*.25+py,width*.38,colors[1],.075],[width*.76-px,height*.62-py,width*.42,colors[0],.055],[width*.52,height*.92,width*.28,colors[2],.035]];
    fogs.forEach(([x,y,r,c,a])=>{const g=ctx.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,hexAlpha(c,a));g.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g;ctx.fillRect(0,0,width,height)});
    particles.forEach(p=>{
      p.x+=p.vx*dt*(quiet?.4:1);p.y+=p.vy*dt*(quiet?.4:1);if(p.y<-5){p.y=height+5;p.x=rand(0,width)}if(p.x<-5)p.x=width+5;if(p.x>width+5)p.x=-5;
      const tw=.58+.42*Math.sin(now*.001*p.speed+p.phase);const dx=p.x-mouse.x,dy=p.y-mouse.y,dist=Math.hypot(dx,dy);
      let ox=0,oy=0;if(active&&dist<145&&dist>0){const f=(145-dist)/145;ox=dx/dist*f*9;oy=dy/dist*f*9;}
      const x=p.x+ox,y=p.y+oy;ctx.globalAlpha=p.a*tw*(quiet?.32:1);ctx.fillStyle=colors[p.hue];
      if(p.kind==='dust'){ctx.beginPath();ctx.arc(x,y,p.r*2.5,0,Math.PI*2);ctx.fill()}else{ctx.beginPath();ctx.arc(x,y,p.r,0,Math.PI*2);ctx.fill();if(p.r>1.35){ctx.globalAlpha*=.22;ctx.fillRect(x-5,y-.35,10,.7);ctx.fillRect(x-.35,y-5,.7,10)}}
    });
    ctx.globalAlpha=1;
    if(active&&!quiet){ // fine connective filaments appear only near the cursor
      const nearby=particles.filter(p=>Math.hypot(p.x-mouse.x,p.y-mouse.y)<125).slice(0,22);ctx.lineWidth=.55;
      nearby.forEach(p=>{const d=Math.hypot(p.x-mouse.x,p.y-mouse.y);ctx.strokeStyle=hexAlpha(colors[0],(1-d/125)*.18);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(mouse.x,mouse.y);ctx.stroke()});
    }
    bursts.forEach((b,i)=>{b.t+=dt;const t=b.t/b.life;if(t>=1){bursts.splice(i,1);return;}b.bits.forEach(bit=>{const x=b.x+bit.vx*b.t,y=b.y+bit.vy*b.t+.5*bit.gravity*b.t*b.t;ctx.globalAlpha=(1-t)*bit.alpha;ctx.fillStyle=bit.color;ctx.save();ctx.translate(x,y);ctx.rotate(bit.rot+b.t*.008);ctx.fillRect(-bit.s/2,-bit.s/2,bit.s,bit.s*1.5);ctx.restore()})});ctx.globalAlpha=1;
    streaks.forEach((s,i)=>{s.x+=s.vx*dt;s.y+=s.vy*dt;s.life-=dt;if(s.life<=0||s.x>width+120||s.y>height+120){streaks.splice(i,1);return;}const g=ctx.createLinearGradient(s.x-s.vx*18,s.y-s.vy*18,s.x,s.y);g.addColorStop(0,'rgba(255,255,255,0)');g.addColorStop(1,hexAlpha(colors[3],.68));ctx.strokeStyle=g;ctx.lineWidth=s.w;ctx.beginPath();ctx.moveTo(s.x-s.vx*18,s.y-s.vy*18);ctx.lineTo(s.x,s.y);ctx.stroke()});
  }
  function hexAlpha(hex,a){const h=hex.replace('#','');const n=parseInt(h.length===3?h.split('').map(x=>x+x).join(''):h,16);return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`}
  function frame(now){if(!active)return;const dt=Math.min(34,now-(last||now));last=now;elapsed+=dt;mouse.x+=(mouse.tx-mouse.x)*.12;mouse.y+=(mouse.ty-mouse.y)*.12;drawBackground(dt,now);if(!reduceMotion)raf=win.requestAnimationFrame(frame)}
  function burst(x,y,amount=42){const colors=palette[theme]||palette.nebula;bursts.push({x,y,t:0,life:1000,bits:Array.from({length:amount},()=>({vx:rand(-.27,.27),vy:rand(-.48,-.08),gravity:rand(.00028,.00055),s:rand(2,5),rot:rand(0,6),alpha:rand(.5,1),color:colors[Math.floor(rand(0,colors.length))]}))});if(bursts.length>6)bursts.shift()}
  function sparkle(x,y){const n=el('span',{class:'sb-fx-sparkle',text:['✦','✧','✺','⋆'][Math.floor(Math.random()*4)]},doc.body);n.style.left=x+'px';n.style.top=y+'px';win.setTimeout(()=>n.remove(),950)}
  function toast(title,detail=''){const item=el('div',{class:'sb-fx-toast'},toastStack);item.innerHTML=`<span class="sb-toast-icon">✦</span><span><strong>${escapeHtml(title)}</strong>${detail?`<br><span style="color:#b8c9e8;font-weight:500">${escapeHtml(detail)}</span>`:''}</span>`;win.setTimeout(()=>{item.classList.add('sb-toast-out');win.setTimeout(()=>item.remove(),400)},3800)}
  function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
  function setTheme(next){theme=next;doc.body.classList.remove('sb-theme-aurora','sb-theme-solar','sb-theme-eclipse');if(next!=='nebula')doc.body.classList.add('sb-theme-'+next);const labels={nebula:'NEBULA DRIFT',aurora:'AURORA FLOW',solar:'SOLAR FLARE',eclipse:'ECLIPSE CALM'};$('#sb-fx-hud-text').textContent='STUDYVERSE ONLINE · '+labels[next]+' · POINTER-REACTIVE';toast('Background mood changed',labels[next]+' is now active')}
  function setQuiet(on){quiet=!!on;doc.body.classList.toggle('sb-fx-quiet',quiet);quietButton.setAttribute('aria-pressed',String(quiet));quietButton.textContent=quiet?'◌ Calm ON':'◌ Calm';toast(quiet?'Visuals softened':'Full effects restored',quiet?'Lower motion for easier focus':'The cinematic layer is back')}
  function updateFocus(){const m=String(Math.floor(focusSeconds/60)).padStart(2,'0'),s=String(focusSeconds%60).padStart(2,'0');focusClock.textContent=m+':'+s;focusStart.textContent=focusRunning?'Ⅱ Pause focus':'▶ Start focus';focusLabel.textContent=focusSeconds===0?'Session complete — take a well-earned short break.':focusRunning?'Stay with one task. Your future self will thank you.':'One thing at a time. You have got this.'}
  function stopFocus(){focusRunning=false;if(focusInterval){win.clearInterval(focusInterval);focusInterval=null}updateFocus()}
  function openFocus(){overlay.classList.add('sb-focus-on');doc.body.classList.add('sb-cinematic-focus');updateFocus()}
  function closeFocus(){overlay.classList.remove('sb-focus-on');doc.body.classList.remove('sb-cinematic-focus')}
  function tickFocus(){if(!focusRunning)return;focusSeconds=Math.max(0,focusSeconds-1);updateFocus();if(focusSeconds===0){stopFocus();burst(width/2,height/2,110);toast('Focus session complete','Brilliant work. Take a short break before your next round.')}}
  function toggleFocus(){if(overlay.classList.contains('sb-focus-on'))closeFocus();else openFocus()}
  resize();if(ctx)raf=win.requestAnimationFrame(frame);
  win.addEventListener('resize',resize,{passive:true});
  doc.addEventListener('pointermove',e=>{mouse.tx=e.clientX;mouse.ty=e.clientY;aura.style.opacity=quiet||reduceMotion?'0':'.9';aura.style.transform=`translate(${e.clientX-130}px,${e.clientY-130}px)`},{passive:true});
  doc.addEventListener('pointerleave',()=>{aura.style.opacity='0'});
  doc.addEventListener('click',e=>{if(!active||quiet||reduceMotion)return;const target=e.target.closest('button,[role="button"],a');if(!target)return;const r=target.getBoundingClientRect();sparkle(e.clientX,e.clientY);if(/submit|complete|finish|unlock|save|send|start|claim|mark done|check answer/i.test((target.innerText||target.getAttribute('aria-label')||'').slice(0,100))){burst(r.left+r.width/2,r.top+r.height/2,26)}},{passive:true});
  themeSelect.addEventListener('change',()=>setTheme(themeSelect.value));particleButton.addEventListener('click',()=>{active=!active;particleButton.setAttribute('aria-pressed',String(active));particleButton.textContent=active?'✦ FX':'✧ FX OFF';canvas.style.opacity=active?(quiet?'.12':'.72'):'0';if(active&&!reduceMotion){last=0;raf=win.requestAnimationFrame(frame)}else if(raf)win.cancelAnimationFrame(raf);toast(active?'Interactive particles enabled':'Particles paused',active?'Cursor and star effects are active':'Background scene stays visible')});
  quietButton.addEventListener('click',()=>setQuiet(!quiet));focusButton.addEventListener('click',openFocus);$('#sb-focus-close').addEventListener('click',closeFocus);focusStart.addEventListener('click',()=>{focusRunning=!focusRunning;if(focusRunning&&!focusInterval)focusInterval=win.setInterval(tickFocus,1000);if(!focusRunning&&focusInterval){win.clearInterval(focusInterval);focusInterval=null}updateFocus()});$('#sb-focus-reset').addEventListener('click',()=>{stopFocus();focusSeconds=1500;updateFocus();toast('Focus timer reset','A fresh 25-minute session is ready')});
  overlay.addEventListener('click',e=>{if(e.target===overlay)closeFocus()});
  doc.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey)return;if(e.key==='Escape'&&overlay.classList.contains('sb-focus-on'))closeFocus();if(e.key.toLowerCase()==='f'&&!/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))toggleFocus();if(e.key.toLowerCase()==='p'&&overlay.classList.contains('sb-focus-on')&&!/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))focusStart.click();if(e.key==='?'&&!/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))toast('Studyverse shortcuts','F = focus mode · P = pause/resume · Esc = close focus')});
  // Observe Streamlit feedback banners, then turn important app successes into a restrained celebration.
  let lastNotice='';const noticeObserver=new MutationObserver(records=>{for(const rec of records){for(const node of rec.addedNodes){if(!(node instanceof win.Element))continue;const candidates=[node,...node.querySelectorAll('[data-testid="stAlert"],[data-testid="stToast"]')];for(const n of candidates){const msg=(n.innerText||'').trim();if(msg.length>2&&msg.length<180&&/success|completed|saved|earned|unlocked|correct|great job|well done/i.test(msg)&&msg!==lastNotice){lastNotice=msg;toast('Nice work!',msg);if(/completed|earned|unlocked|great job|well done/i.test(msg))burst(width*.7,height*.28,48);break}}}}});
  noticeObserver.observe(doc.body,{childList:true,subtree:true});
  // Keep controls alive if Streamlit rerenders its own app subtree.
  const dockObserver=new MutationObserver(()=>{if(!doc.body.contains(dock))doc.body.appendChild(dock);if(!doc.body.contains(canvas))doc.body.appendChild(canvas);if(!doc.body.contains(aura))doc.body.appendChild(aura);if(!doc.body.contains(hud))doc.body.appendChild(hud);if(!doc.body.contains(toastStack))doc.body.appendChild(toastStack);if(!doc.body.contains(overlay))doc.body.appendChild(overlay)});
  dockObserver.observe(doc.body,{childList:true});
  if(reduceMotion){canvas.style.opacity='.16';quiet=true;quietButton.setAttribute('aria-pressed','true');quietButton.textContent='◌ Calm ON'}
  win.setTimeout(()=>toast('Welcome to the Studyverse','Your galaxy is live. Press F anytime to enter focus mode.'),1100);
})();
