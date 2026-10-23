/* AIP Studio — dependency-free accessible dashboard. No synthetic audit metrics. */
(() => {
  'use strict';
  const API = '/api/v1';
  const state = {token:sessionStorage.getItem('aip_access') || '', refresh:sessionStorage.getItem('aip_refresh') || '', user:null, orgs:[], orgId:'', websites:[], audits:[], report:null, page:'overview', busy:false, filter:'all', insights:null, gsc:null, gscSiteId:''};
  const root = document.getElementById('app');
  const icons = {
    grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-4 4-4 14 0 18M12 3c4 4 4 14 0 18"/>',
    chart:'<path d="M3 3v18h18M7 16l4-5 4 2 5-7"/>',
    spark:'<path d="m12 3 1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8L12 3ZM19 18l.7 1.3L21 20l-1.3.7L19 22l-.7-1.3L17 20l1.3-.7L19 18Z"/>',
    settings:'<circle cx="12" cy="12" r="3"/><path d="M19.5 13.5a1.6 1.6 0 0 0 .3 1.8l.1.1-2 2-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V20h-3v-1.5a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1-2-2 .1-.1a1.6 1.6 0 0 0 .3-1.8A1.6 1.6 0 0 0 6 12H4v-3h2a1.6 1.6 0 0 0 1.5-1A1.6 1.6 0 0 0 7.2 6l-.1-.1 2-2 .1.1A1.6 1.6 0 0 0 11 4.3 1.6 1.6 0 0 0 12 3h3v1.5a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1 2 2-.1.1a1.6 1.6 0 0 0-.3 1.8A1.6 1.6 0 0 0 21 11v2a1.6 1.6 0 0 0-1.5.5Z"/>',
    plus:'<path d="M12 5v14M5 12h14"/>', arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
    logout:'<path d="M10 17l5-5-5-5m5 5H3M12 3h6a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3h-6"/>',
    shield:'<path d="m12 2 9 4v6c0 5-4 9-9 10-5-1-9-5-9-10V6l9-4Z"/><path d="m8 12 3 3 5-6"/>',
    activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    file:'<path d="M6 3h9l4 4v14H6V3Zm9 0v5h4M9 12h7M9 16h7"/>',
    alert:'<path d="m12 3 10 18H2L12 3Zm0 6v5m0 3v1"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    search:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
    close:'<path d="M6 6l12 12M18 6 6 18"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    check:'<path d="m4 12 5 5L20 6"/>',
    external:'<path d="M13 4h7v7M20 4l-9 9M20 14v6H4V4h6"/>',
    trash:'<path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6"/>',
    refresh:'<path d="M20 11a8 8 0 0 0-14-5L3 9m0-6v6h6M4 13a8 8 0 0 0 14 5l3-3m0 6v-6h-6"/>',
    layers:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>'
  };
  const icon = (name, size=18) => `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icons[name]||icons.grid}</svg>`;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = date => date ? new Date(date).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '—';
  const niceUrl = url => {try{return new URL(url).hostname.replace(/^www\./,'')}catch{return url}};
  const toast = (message,error=false) => {const el=document.getElementById('toast');el.textContent=message;el.className='toast show'+(error?' error':'');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className='toast',4900)};
  async function request(path, options={}){
    const headers = {...(options.headers||{})};
    if(state.token) headers.Authorization = `Bearer ${state.token}`;
    if(options.json !== undefined) {headers['Content-Type']='application/json';options.body=JSON.stringify(options.json)}
    const response = await fetch(API+path,{...options,headers});
    if(response.status===204) return null;
    const data = await response.json().catch(()=>({}));
    if(!response.ok){if(response.status===401&&state.token){logout(false);throw new Error('Session expired. Please sign in again.')};throw new Error(data?.error?.message || data?.detail || 'Request failed.')}
    return data;
  }
  const button = (text,action,cls='btn-primary',extra='')=>`<button class="btn ${cls}" data-action="${action}" ${extra}>${text}</button>`;
  const heading = (kicker,title,desc,action='')=>`<div class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${desc}</p></div><div class="actions">${action}</div></div>`;
  const empty = (name,heading,desc,action='')=>`<div class="empty wide-empty"><div class="empty-symbol">${icon(name,27)}</div><h4>${heading}</h4><p>${desc}</p>${action}</div>`;

  function authView(mode='login', email=''){
    if(typeof mode==='boolean') mode=mode?'register':'login';
    const verify=mode==='verify', forgot=mode==='forgot', reset=mode==='reset', register=mode==='register';
    const headingText={login:'Welcome back',register:'Create your account',verify:'Verify your email',forgot:'Recover your account',reset:'Choose a new password'}[mode];
    const desc={login:'Enter your workspace and pick up where you left off.',register:'Start your workspace with secure email verification.',verify:'Check your inbox for a six-digit security code. It expires in 10 minutes.',forgot:'We will send a one-time reset code if this address has an account.',reset:'Enter the code from your email and your new password.'}[mode];
    const textField=(id,label,type,placeholder,value='',attributes='')=>`<div class="form-row"><label for="${id}">${label}</label><input id="${id}" class="field" type="${type}" name="${id}" placeholder="${placeholder}" value="${esc(value)}" ${attributes} required /></div>`;
    const emailField=textField('email','Email address','email','you@company.com',email,'autocomplete="email"');
    const newPassword=textField('password','Password','password','At least 8 characters','',`minlength="8" autocomplete="${register?'new-password':'current-password'}"`);
    const sixCode=textField('code','Six-digit email code','text','000000','','inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code"');
    const formFields={
      login:emailField+newPassword,
      register:emailField+textField('name','Your name','text','Full name','',`minlength="2"`)+textField('company','Workspace name','text','e.g. Ala AI Lab','',`minlength="2"`)+newPassword,
      verify:emailField+sixCode,
      forgot:emailField,
      reset:emailField+sixCode+textField('password','New password','password','At least 8 characters','',`minlength="8" autocomplete="new-password"`)
    }[mode];
    const submitText={login:'Sign in to dashboard',register:'Create account & send code',verify:'Verify email',forgot:'Send reset code',reset:'Reset password'}[mode];
    root.innerHTML=`<div class="auth-page"><section class="auth-left"><div class="auth-brand"><div class="brand-symbol">a✳</div><strong>AIP Studio</strong></div><div class="auth-left-inner"><span class="auth-label">WEBSITE INTELLIGENCE PLATFORM</span><h1>Understand your site.<br><span>Own your growth.</span></h1><p>Technical SEO, real on-page keyword evidence, and a prioritized content action plan — organized in one elegant workspace.</p><div class="preview-card" aria-label="Illustrative interface preview"><div class="preview-head"><span>Content intelligence · interface preview</span><span>${icon('activity',15)}</span></div><div class="preview-bars">${[46,64,55,82,72,94,76,88,100].map(h=>`<span style="height:${h}%"></span>`).join('')}</div><div class="preview-foot"><span>Illustrative graphic · not live data</span><span>↗ Audit insights</span></div></div></div><div class="auth-note">© ${new Date().getFullYear()} AIP Studio · Built for people who build.</div></section><section class="auth-right"><div class="auth-form-container"><div class="auth-topicon">${icon(verify?'shield':'spark',24)}</div><h2>${headingText}</h2><p>${desc}</p><form id="auth-form">${formFields}<button type="submit" class="btn btn-primary auth-submit">${submitText} ${icon('arrow',17)}</button></form><div class="auth-switch">${mode==='login'?`New to AIP Studio? <button data-action="sign-up">Create an account</button>`:mode==='register'?`Already registered? <button data-action="sign-in">Sign in</button>`:`<button data-action="sign-in">Back to sign in</button>`}</div>${mode==='login'?`<div class="auth-switch"><button data-action="forgot">Forgot password?</button> · <button data-action="verify">Enter verification code</button></div>`:''}${mode==='verify'?`<div class="auth-switch">Didn't receive a code? <button data-action="resend-verification" data-email="${esc(email)}">Resend code</button></div>`:''}<div class="divider-line"></div><p class="auth-feature">${icon('shield',15)} Email codes expire in 10 minutes. Existing workspaces are preserved when passwords change.</p></div></section></div>`;
    document.getElementById('auth-form').onsubmit=async e=>{
      e.preventDefault();const form=e.target,submit=form.querySelector('button[type="submit"]');submit.disabled=true;submit.textContent='Working…';
      try{
        const fd=new FormData(form), mail=String(fd.get('email')).trim();
        if(mode==='register'){
          await request('/auth/register',{method:'POST',json:{email:mail,password:fd.get('password'),full_name:fd.get('name'),organization_name:fd.get('company')}});
          authView('verify',mail);toast('Account created. Enter the email verification code.');return;
        }
        if(mode==='verify'){
          await request('/auth/verify-email',{method:'POST',json:{email:mail,code:fd.get('code')}});
          authView('login',mail);toast('Email verified. Sign in to continue.');return;
        }
        if(mode==='forgot'){
          await request('/auth/forgot-password',{method:'POST',json:{email:mail}});
          authView('reset',mail);toast('If your account exists, a reset code has been sent.');return;
        }
        if(mode==='reset'){
          await request('/auth/reset-password',{method:'POST',json:{email:mail,code:fd.get('code'),new_password:fd.get('password')}});
          authView('login',mail);toast('Password updated. Sign in with your new password.');return;
        }
        const params=new URLSearchParams({username:mail,password:fd.get('password')});
        const tokens=await request('/auth/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:params});
        state.token=tokens.access_token;state.refresh=tokens.refresh_token;
        sessionStorage.setItem('aip_access',state.token);sessionStorage.setItem('aip_refresh',state.refresh);
        await initialize();toast('Signed in successfully.');
      }catch(err){toast(err.message,true);submit.disabled=false;submit.innerHTML=submitText+' '+icon('arrow',17)}
    };
  }
  function logout(notify=true){state.token='';state.refresh='';sessionStorage.removeItem('aip_access');sessionStorage.removeItem('aip_refresh');state.user=null;state.orgs=[];state.orgId='';state.websites=[];state.report=null;state.gsc=null;authView();if(notify)toast('Signed out of this session.')}
  async function signOut(){if(state.refresh){try{await request('/auth/logout',{method:'POST',json:{refresh_token:state.refresh}})}catch{}}logout()}
  async function initialize(){
    try{state.user=await request('/auth/me');state.orgs=await request('/organizations');state.orgId=state.orgs.some(x=>x.id===state.orgId)?state.orgId:(state.orgs[0]?.id||'');await refreshData();state.page='overview';render()}
    catch(err){if(!state.token) return;toast(err.message,true);logout(false)}
  }
  async function refreshData(){
    state.websites=state.orgId?await request(`/organizations/${state.orgId}/websites`):[];
    const results=await Promise.all(state.websites.slice(0,30).map(async s=>{try{return (await request(`/websites/${s.id}/audits`)).map(a=>({...a,site:s}))}catch{return []}}));
    state.audits=results.flat().sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));
  }
  function frame(content){
    const links=[['overview','grid','Overview'],['websites','globe','Websites'],['reports','chart','Audit reports'],['insights','spark','Insights'],['settings','settings','Settings']];
    root.innerHTML=`<div class="shell"><aside class="sidebar" id="sidebar"><div class="brand"><div class="brand-symbol">a✳</div><div><div class="brand-title">AIP Studio</div><div class="brand-desc">INTELLIGENCE HUB</div></div></div><div class="nav-label">WORKSPACE</div><nav class="nav-group" aria-label="Main navigation">${links.map(([id,ic,label])=>`<button class="nav-link ${state.page===id?'active':''}" data-action="navigate" data-page="${id}">${icon(ic)}<span>${label}</span></button>`).join('')}</nav><div class="sidebar-foot"><div class="help-card"><div class="help-icon">${icon('spark',18)}</div><strong>Insights, not guesswork.</strong><p>Every audit finding includes evidence, severity and a suggested fix.</p><a href="/docs" target="_blank" rel="noopener noreferrer">Explore the API ${icon('arrow',13)}</a></div><div class="profile"><div class="avatar">${esc((state.user?.full_name||state.user?.email||'A')[0].toUpperCase())}</div><div><strong>${esc(state.user?.full_name||'Your workspace')}</strong><small>${esc(state.user?.email||'')}</small></div><button class="sign-out" data-action="logout" aria-label="Sign out" title="Sign out">${icon('logout',17)}</button></div></div></aside><div class="content-wrap"><header class="topbar"><div class="bread"><button class="icon-btn mobile-nav-toggle" data-action="menu" aria-label="Open navigation">${icon('menu')}</button>AIP Studio <span class="slash">/</span><strong>${esc(links.find(x=>x[0]===state.page)?.[2]||'Overview')}</strong></div><div class="top-actions"><button class="icon-btn mobile-nav-toggle" data-action="menu" aria-label="Menu">${icon('menu')}</button><div class="status-pill"><span class="status-dot"></span> Workspace active</div><select id="org-selector" aria-label="Select organization">${state.orgs.map(o=>`<option value="${esc(o.id)}" ${o.id===state.orgId?'selected':''}>${esc(o.name)}</option>`).join('')}${state.orgs.length===0?'<option>No workspace</option>':''}</select><a class="icon-btn" href="/docs" target="_blank" rel="noopener noreferrer" aria-label="API documentation" title="API docs">${icon('external',16)}</a></div></header><main class="main">${content}</main></div></div><div id="modal-root"></div>`;
    document.getElementById('org-selector')?.addEventListener('change',async e=>{state.orgId=e.target.value;state.report=null;state.gsc=null;state.gscSiteId='';try{await refreshData();render()}catch(err){toast(err.message,true)}});
    document.getElementById('change-password-form')?.addEventListener('submit',async e=>{e.preventDefault();const form=e.target,b=form.querySelector('button[type=submit]');b.disabled=true;try{await request('/auth/change-password',{method:'POST',json:{current_password:document.getElementById('old-password').value,new_password:document.getElementById('new-password').value}});logout(false);toast('Password changed. Sign in again.')}catch(err){toast(err.message,true);b.disabled=false}});
  }
  function render(){if(!state.token)return authView();const views={overview:overviewView,websites:websiteView,reports:reportsView,insights:insightsView,settings:settingsView};frame((views[state.page]||overviewView)())}
  // Reinterpret legacy records as failed if all attempts ended in fetch errors.
  // Earlier versions incorrectly recorded such reports as completed, scoring 88/100.
  function auditState(a){
    if(!a)return 'not_scanned';
    const pages=a.summary?.pages;
    if(Array.isArray(pages)&&pages.length){
      const fetched=pages.filter(p=>Number.isInteger(p.status)&&p.status>=200&&p.status<400).length;
      if(!fetched)return 'failed';
      if(pages.some(p=>p.status==='error'||(Number.isInteger(p.status)&&p.status>=400)))return 'partial';
    }
    return a.status||'completed';
  }
  function pagesAnalyzed(a){
    if(!a)return 0;
    const pages=a.summary?.pages;
    if(Array.isArray(pages)&&pages.length)return pages.filter(p=>Number.isInteger(p.status)&&p.status>=200&&p.status<400).length;
    return a.pages_scanned||0;
  }
  function validScore(a){return !!a && auditState(a)!=='failed' && Number.isFinite(a.score) && pagesAnalyzed(a)>0}
  function scoreBadge(a){
    if(!a)return '<span class="tag tag-neutral">Not scanned</span>';
    const status=auditState(a);
    if(status==='failed')return '<span class="tag tag-danger">Scan failed · N/A</span>';
    const tone=status==='partial'?'tag-amber':a.score>=80?'tag-success':a.score>=55?'tag-amber':'tag-danger';
    return `<span class="tag ${tone}">${status==='partial'?'Partial · ':''}${a.score} / 100</span>`;
  }
  const latestFor = siteId => state.audits.find(a=>a.website_id===siteId);
  function stat(label,value,footer,ic,accent){return `<div class="card stat-card"><div class="stat-top"><span>${label}</span><div class="stat-icon ${accent}">${icon(ic)}</div></div><div><div class="metric-value">${value}</div><div class="metric-foot">${footer}</div></div></div>`}
  function lineChart(audits){
    const sorted=[...audits].filter(a=>auditState(a)==='completed'&&validScore(a)).reverse().slice(-9);
    if(!sorted.length) return '<div class="chart-empty"><strong>Nothing to chart just yet</strong><p>Your audit score history will appear here after your first scan.</p></div>';
    const width=540,height=180,marginX=18,marginY=16,span=width-2*marginX;
    const points=sorted.map((a,i)=>[marginX+(i/(Math.max(1,sorted.length-1)))*span, height-marginY-(a.score/100)*(height-marginY*2)]);
    const poly=points.map(p=>p.join(',')).join(' ');
    const area=`${marginX},${height-marginY} ${poly} ${points.at(-1)[0]},${height-marginY}`;
    return `<svg role="img" aria-label="Audit scores ${sorted.map(a=>a.score).join(', ')}" viewBox="0 0 540 205" preserveAspectRatio="none"><defs><linearGradient id="linefill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#7b70f9" stop-opacity=".20"/><stop offset="1" stop-color="#7b70f9" stop-opacity="0"/></linearGradient></defs>${[0,25,50,75,100].map(n=>`<line x1="17" x2="525" y1="${height-marginY-n/100*(height-marginY*2)}" y2="${height-marginY-n/100*(height-marginY*2)}" stroke="#ebedf5" stroke-dasharray="4 5"/><text x="528" y="${height-marginY-n/100*(height-marginY*2)+4}" text-anchor="start" fill="#a8b0c2" font-size="10">${n}</text>`).join('')}<polygon fill="url(#linefill)" points="${area}"/><polyline points="${poly}" fill="none" stroke="#6b61f4" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>${points.map(p=>`<circle cx="${p[0]}" cy="${p[1]}" r="5" fill="#fff" stroke="#6b61f4" stroke-width="3"/>`).join('')}</svg>`;
  }
  function overviewView(){
    const latest=state.audits[0];const totalIssues=state.audits.slice(0,10).reduce((n,a)=>n+a.issues_count,0);
    const score=validScore(latest)?latest.score:null;const counts=latest?.summary?.severity_counts||{};
    return `${heading('YOUR WORKSPACE','Overview','Your website intelligence, all in one place.',button(`${icon('plus',17)} Add website`,'new-website'))}<section class="hero"><div class="hero-copy"><div class="hero-kicker">${icon('spark',13)} EVIDENCE-DRIVEN INTELLIGENCE</div><h2>Make every page count.</h2><p>Discover technical SEO issues, understand their impact, and turn your next fix into measurable progress.</p></div><div class="hero-icon">${icon('shield',17)} Public-page scans</div></section><section class="stat-grid">${stat('Websites',state.websites.length,'Connected to your workspace','globe','lilac')}${stat('Completed audits',state.audits.filter(a=>auditState(a)==='completed').length,'Most recent 30 sites','chart','mint')}${stat('Latest SEO score',score===null?'—':score+'<span style="font-size:14px;color:#9ba6b9"> / 100</span>',score===null&&latest?'Scan failed or unavailable':'Heuristic technical health score','activity','peach')}${stat('Latest audit issues',latest?latest.issues_count:'—','Issues detected in most recent scan','alert','rose')}</section><div class="grid-two"><section class="card panel"><div class="panel-heading"><div><h3>Audit score history</h3><div class="panel-sub">Scores from your completed scans</div></div><button class="panel-link" data-action="navigate" data-page="reports">All reports →</button></div><div class="chart-wrap">${lineChart(state.audits)}</div></section><section class="card panel"><div class="panel-heading"><div><h3>Latest health snapshot</h3><div class="panel-sub">${latest?esc(latest.site.name)+' · '+fmt(latest.created_at):'Run an audit to populate insights'}</div></div></div><div class="score-panel"><div class="donut" style="--percent:${score??0}%"><div class="donut-inner"><strong>${score??'—'}</strong><small>SEO score</small></div></div><div class="score-legend">${[['Critical',counts.critical||0,'#e85c74'],['High',counts.high||0,'#f28e70'],['Medium',counts.medium||0,'#f5b954'],['Low',counts.low||0,'#8e87f3']].map(([label,n,color])=>`<div class="legend-item"><i class="legend-dot" style="background:${color}"></i>${label} <strong style="margin-left:auto;color:#35415b">${latest?n:'—'}</strong></div>`).join('')}<div class="score-note">${auditState(latest)==='failed'?'Scan failed; no SEO score available.':'Scores reflect only checks performed by the crawler.'}</div></div></div></section></div><section class="card table-panel"><div class="panel-heading"><div><h3>Your websites</h3><div class="panel-sub">Manage your tracked domains and start new audits.</div></div><button class="panel-link" data-action="navigate" data-page="websites">View all →</button></div>${siteTable()}</section>`;
  }
  function siteTable(){if(!state.websites.length)return empty('globe','Your first website starts here','Add a public website URL to run your first technical SEO audit.',button(`${icon('plus',16)} Add website`,'new-website'));
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Website</th><th>Last scan</th><th>SEO score</th><th>Issues</th><th>Action</th></tr></thead><tbody>${state.websites.map(s=>{const a=latestFor(s.id);return `<tr><td><div class="table-primary"><div class="web-icon">${icon('globe',18)}</div><div><strong>${esc(s.name)}</strong><small>${esc(niceUrl(s.url))}</small></div></div></td><td>${fmt(a?.created_at)}</td><td>${scoreBadge(a)}</td><td>${a?a.issues_count:'—'}</td><td>${a?`<button class="text-btn" data-action="open-report" data-id="${a.id}">View report</button>`:`<button class="text-btn" data-action="run-scan" data-id="${s.id}">Run audit →</button>`}</td></tr>`}).join('')}</tbody></table></div>`}
  function websiteView(){return `${heading('ASSET MANAGEMENT','Your websites','Track domains, monitor technical health and manage scans.',button(`${icon('plus',17)} Add website`,'new-website'))}${state.websites.length?`<div class="project-list">${state.websites.map(s=>{const audit=latestFor(s.id);return `<section class="card project-card"><div class="web-icon">${icon('globe',20)}</div><h3>${esc(s.name)}</h3><p>${esc(s.url)}</p>${scoreBadge(audit)}<div class="project-footer"><small>${audit?'Last scan '+fmt(audit.created_at):'Created '+fmt(s.created_at)}</small><div class="actions">${audit?`<button class="text-btn" data-action="open-report" data-id="${audit.id}">Report</button>`:''}<button class="text-btn" data-action="open-gsc" data-id="${s.id}" title="Import or inspect Search Console CSV">GSC data</button><button class="mini-btn" data-action="run-scan" data-id="${s.id}">${icon('refresh',14)} Scan</button><button class="text-btn" title="Delete website" aria-label="Delete website" data-action="delete-site" data-id="${s.id}" style="color:#da6977">${icon('trash',15)}</button></div></div></section>`}).join('')}</div>`:`<section class="card">${empty('globe','No websites connected yet','Your workspace is ready. Add your first website to begin auditing.',button(`${icon('plus',16)} Add website`,'new-website'))}</section>`}`}
  function reportsView(){return `${heading('HISTORY & EVIDENCE','Audit reports','Review scan results and export issue-by-issue reports.')}${state.report?reportCard(state.report):''}<section class="card table-panel"><div class="panel-heading"><div><h3>Audit history</h3><div class="panel-sub">Select a report to see the evidence behind each finding.</div></div></div>${!state.audits.length?empty('file','Your reports live here','Run a website audit and results will automatically appear in this section.',button('Go to websites','go-websites','btn-outline')):`<div class="table-scroll"><table class="data-table"><thead><tr><th>Website</th><th>Scanned</th><th>Pages</th><th>SEO score</th><th>Issues</th><th></th></tr></thead><tbody>${state.audits.map(a=>`<tr><td><div class="table-primary"><div class="web-icon">${icon('file',17)}</div><div><strong>${esc(a.site.name)}</strong><small>${esc(niceUrl(a.site.url))}</small></div></div></td><td>${fmt(a.created_at)}</td><td>${pagesAnalyzed(a)}</td><td>${scoreBadge(a)}</td><td>${a.issues_count}</td><td><button class="text-btn" data-action="open-report" data-id="${a.id}">Inspect →</button></td></tr>`).join('')}</tbody></table></div>`}</section>`}
  function reportCard(report){const a=report.audit,w=report.website;return `<div class="card panel" style="margin-bottom:21px"><div class="panel-heading"><div><div class="eyebrow">SELECTED REPORT</div><h3>${esc(w.name)} <span class="muted" style="font-weight:500">· ${fmt(a.created_at)}</span></h3></div><div class="actions">${validScore(a)?`<button class="btn btn-outline" data-action="ai" data-id="${a.id}">${icon('spark',16)} Action plan / local AI</button>`:''}<button class="btn btn-outline" data-action="csv" data-id="${a.id}">${icon('download',16)} Export CSV</button><button class="btn btn-outline" data-action="close-report">${icon('close',15)}</button></div></div><div class="stat-grid" style="margin:0 0 21px">${stat('SEO score',validScore(a)?a.score+' / 100':'N/A',auditState(a)==='failed'?'Scan failed · No pages analyzed':auditState(a)==='partial'?'Partial result · Fetched pages only':'Rules-based technical checks','activity','mint')}${stat('Pages scanned',pagesAnalyzed(a),'Successfully analyzed HTML pages','globe','lilac')}${stat('Issues found',a.issues_count,'Actionable diagnostics','alert','peach')}${stat('Report date',fmt(a.created_at),'Persisted audit history','clock','rose')}</div><div id="ai-narrative" class="hidden"></div>${auditState(a)==='failed'?'<div class="notice notice-warning"><strong>Scan failed — SEO score unavailable.</strong> No HTML page was successfully analyzed. Review the connection diagnostic below, then retry.</div>':auditState(a)==='partial'?'<div class="notice notice-warning"><strong>Partial scan.</strong> The score reflects fetched pages only; other pages were not analyzed.</div>':''}<div class="notice"><strong>Measurement scope:</strong> ${esc(a.summary?.methodology||'Technical HTML and HTTP checks only.')}</div>${a.summary?.crawl_discovery?`<div class="crawl-scope"><span><b>Robots.txt</b> ${esc(a.summary.crawl_discovery.robots_status)}</span><span><b>Sitemap</b> ${esc(a.summary.crawl_discovery.sitemap_status)}</span><span><b>Discovered URLs</b> ${a.summary.crawl_discovery.sitemap_urls_observed}</span></div>`:''}${contentIntelligence(report)}${gscPanel(w.id)}${report.findings.length?`<div class="two-column-controls"><h3 style="margin:0;font-size:15px">Findings <span class="issue-count">(${report.findings.length})</span></h3><select class="filter-select" id="severity-filter" aria-label="Filter findings by severity"><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></div><div id="findings-list">${findingsHtml(report.findings,'all')}</div>`:empty('check','No issues detected by these checks','This result only covers checks performed by the crawler.')}</div>`}
  function contentIntelligence(report){
    const data=report.audit.summary?.content_analysis;
    if(!data?.pages?.length)return `<section class="content-insight"><div class="content-section-heading"><div><span class="eyebrow">CONTENT INTELLIGENCE</span><h3>No content analyzed</h3></div></div><p class="muted small">The crawler needs at least one successfully fetched HTML page to extract page text or keywords.</p></section>`;
    return `<section class="content-insight"><div class="content-section-heading"><div><span class="eyebrow">CONTENT INTELLIGENCE</span><h3>What your pages actually say</h3><p>On-page topics extracted from the HTML we fetched — not estimated Google searches.</p></div><span class="tag tag-violet">${data.pages.length} analyzed pages</span></div><div class="content-metrics"><div><strong>${data.pages.reduce((n,p)=>n+p.word_count,0)}</strong><small>Visible words (selected tokens)</small></div><div><strong>${data.keywords?.length||0}</strong><small>Observed keyword themes</small></div><div><strong>${data.recommendations?.length||0}</strong><small>Content opportunities</small></div></div><div class="keyword-panel"><h4>${icon('search',17)} Keywords observed on your pages</h4><p class="muted small">Frequency means occurrences in scanned HTML only. No search volume or ranking data is claimed.</p><div class="keyword-list">${(data.keywords||[]).length?data.keywords.map((k,i)=>`<span class="keyword-chip"><span>${i+1}.</span> ${esc(k.term)} <strong>${k.occurrences_on_scanned_pages}×</strong></span>`).join(''):'No repeated terms found'}</div></div><div class="content-section-heading" style="margin-top:26px"><div><h3>Page-by-page content audit</h3><p>Evidence for each successfully fetched page.</p></div></div><div class="content-pages">${data.pages.map(p=>`<details class="content-page"><summary><div><strong>${esc(p.title||niceUrl(p.url))}</strong><small>${esc(p.url)}</small></div><span class="page-words">${p.word_count} words <span>⌄</span></span></summary><div class="content-page-details"><div><b>Main heading</b><p>${esc(p.h1?.join(' · ')||'Missing')}</p></div><div><b>Meta description</b><p>${esc(p.description||'Missing')}</p></div><div><b>Internal / external links</b><p>${p.internal_links} / ${p.external_links}</p></div><div><b>Page themes</b><p>${(p.keywords||[]).slice(0,7).map(k=>`${esc(k.term)} (${k.occurrences})`).join(' · ')||'Not enough text'}</p></div><div><b>H2 headings</b><p>${esc(p.h2?.slice(0,6).join(' · ')||'None')}</p></div><div><b>Structured data</b><p>${esc(p.schema_types?.join(' · ')||'No recognized JSON-LD @type detected')}</p></div><div><b>Canonical</b><p>${esc(p.canonical||'Not declared')}</p></div><div><b>Response to first headers</b><p>${p.response_ms===null||p.response_ms===undefined?'Not measured':p.response_ms+' ms (single observation)'}</p></div></div></details>`).join('')}</div>${(data.recommendations||[]).length?`<div class="content-section-heading" style="margin-top:26px"><div><h3>Content improvement plan</h3><p>Practical next steps grounded in scanned page evidence.</p></div></div>${data.recommendations.map((r,i)=>`<div class="action-item"><span class="action-index">${String(i+1).padStart(2,'0')}</span><div><strong>${esc(r.title)}</strong><p>${esc(r.reason)}</p><div class="issue-fix"><b>Next step: </b>${esc(r.action)}</div><small>${esc(r.page)}</small></div><span class="severity-chip severity-${esc(r.priority)}">${esc(r.priority)}</span></div>`).join('')}`:'<div class="notice" style="margin-top:20px">No additional content warnings were triggered by the current checks.</div>'}</section>`;
  }
  function findingsHtml(findings,filter){const severity={critical:0,high:1,medium:2,low:3};const filtered=findings.filter(x=>filter==='all'||x.severity===filter).sort((a,b)=>severity[a.severity]-severity[b.severity]);if(!filtered.length)return empty('check','No matching issues','Try another severity filter.');return filtered.map(f=>`<div class="issue-card"><div class="issue-head"><h4>${esc(f.title)}</h4><span class="severity-chip severity-${esc(f.severity)}">${esc(f.severity.toUpperCase())}</span></div><p>${esc(f.description)}</p><div class="issue-fix"><strong>Recommended action: </strong>${esc(f.recommendation)}</div><div class="issue-meta">${esc(f.category.replaceAll('_',' '))} · ${esc(f.page_url)}${f.evidence?' · Evidence: '+esc(f.evidence):''}</div></div>`).join('')}
  function gscPanel(websiteId=''){
    const siteId=websiteId||state.gscSiteId||state.websites[0]?.id||'';
    const site=state.websites.find(s=>s.id===siteId);
    const evidence=state.gsc?.website_id===siteId?state.gsc:null;
    const isLoaded=!!evidence;
    const rows=evidence?.opportunities||[];
    return `<section class="card panel gsc-panel" style="margin:22px 0"><div class="panel-heading"><div><span class="eyebrow">REAL SEARCH EVIDENCE · NO SUBSCRIPTION</span><h3>Search Console intelligence</h3><p class="muted small">Upload the Queries CSV exported from your own Google Search Console property. The numbers are supplied by you, not generated by our crawler.</p></div><span class="tag tag-violet">Verified format · user-uploaded</span></div>
    <div class="gsc-controls">${websiteId?'':`<label>Website <select class="filter-select" id="gsc-site-select" aria-label="Choose website for Search Console import">${state.websites.map(s=>`<option value="${esc(s.id)}" ${s.id===siteId?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label>`}
    ${site?`${button(icon('download',16)+' Upload Queries CSV','import-gsc','btn-primary',`data-id="${esc(siteId)}"`)} ${button(icon('refresh',15)+' Load saved data','load-gsc','btn-outline',`data-id="${esc(siteId)}"`)}`:'<span class="muted small">First add a website to your workspace.</span>'}</div>
    <div class="notice">Google Search Console → Performance → Search results → Queries → Export → CSV. Only UTF-8 CSV with Query, Clicks, Impressions, CTR and Position is accepted. Data and period are user-provided; totals are for imported rows, not necessarily the entire property.</div>
    ${!isLoaded?'<p class="muted small" style="padding:18px 0">Load existing data or upload a CSV to see evidence-based opportunities.</p>':!evidence.import_id?'<p class="muted small" style="padding:18px 0">No Search Console export has been imported for this website.</p>':`<div class="content-metrics"><div><strong>${evidence.row_count.toLocaleString('en-US')}</strong><small>Imported search queries</small></div><div><strong>${evidence.total_clicks.toLocaleString('en-US')}</strong><small>Clicks in imported rows</small></div><div><strong>${evidence.total_impressions.toLocaleString('en-US')}</strong><small>Impressions in imported rows</small></div></div><h4 style="margin:20px 0 10px">Opportunity shortlist <span class="muted small">· transparent heuristic, not predicted traffic</span></h4><div class="table-scroll"><table class="data-table"><thead><tr><th>Query</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Position</th><th>Suggested action</th></tr></thead><tbody>${rows.slice(0,30).map(q=>`<tr><td><strong class="gsc-query" dir="auto">${esc(q.query)}</strong><div class="muted small">${esc(q.type)}${q.matched_page?` · possible page: ${esc(niceUrl(q.matched_page))}`:''}</div></td><td>${q.clicks}</td><td>${q.impressions}</td><td>${(q.ctr*100).toFixed(1)}%</td><td>${q.position.toFixed(1)}</td><td class="gsc-action"><details><summary>${esc(q.type)} · review action</summary><p>${esc(q.recommendation)}</p><small>${esc(q.page_match_evidence||'Landing page not verified')}</small></details></td></tr>`).join('')}</tbody></table></div><p class="muted small" style="margin-top:12px">Imported: ${fmt(evidence.uploaded_at)}. Priority index is a triage formula, not a ranking or traffic forecast. Position/CTR may not be representative for small samples.</p>`}
    </section>`;
  }
  async function loadGsc(siteId){
    if(!siteId)return;
    try{state.gscSiteId=siteId;state.gsc=await request(`/websites/${siteId}/search-console`);render();toast(state.gsc.import_id?'Search Console evidence loaded.':'No CSV imported for this website yet.');}
    catch(err){toast(err.message,true)}
  }
  function importGsc(siteId){
    const fileInput=document.createElement('input');fileInput.type='file';fileInput.accept='.csv,text/csv';
    fileInput.addEventListener('change',async()=>{
      const file=fileInput.files?.[0];if(!file)return;
      if(file.size>2000000){toast('CSV must not exceed 2 MB.',true);return;}
      const data=new FormData();data.append('file',file);
      try{
        toast('Validating and importing Search Console evidence…');
        const result=await fetch(API+`/websites/${siteId}/search-console/import`,{method:'POST',headers:{Authorization:`Bearer ${state.token}`},body:data});
        const body=await result.json().catch(()=>({}));
        if(!result.ok)throw new Error(body?.error?.message||'CSV import failed');
        state.gsc=body;state.gscSiteId=siteId;state.page='insights';state.report=null;render();toast(`${body.row_count} real query rows imported.`);
      }catch(err){toast(err.message,true)}
    },{once:true});fileInput.click();
  }
  // GSC Queries CSV contains no landing-page column: all title matches are
  // candidates, never confirmed Google landing-page attributions.
  function combinedActionPlan(siteId){
    const data=state.gsc?.website_id===siteId?state.gsc:null;
    if(!data?.import_id)return '';
    const candidates=(data.opportunities||[]).slice(0,6);
    const scope=data.audit_id?`Paired with ${data.audit_page_count} scanned HTML pages (audit ${fmt(data.audit_at)}).`:'No usable page audit found; recommendations use the uploaded query metrics only.';
    return `<section class="card panel" style="margin:22px 0"><div class="panel-heading"><div><span class="eyebrow">GSC + ON-PAGE AUDIT</span><h3>Evidence-based combined action plan</h3><p class="muted small">${esc(scope)} Page matches are heuristic: a Queries CSV does not reveal the actual landing URLs.</p></div><span class="tag tag-violet">${candidates.length} review priorities</span></div>
      ${candidates.map((item,i)=>`<div class="action-item"><span class="action-index">${String(i+1).padStart(2,'0')}</span><div><strong dir="auto">${esc(item.query)}</strong><p>${item.impressions} impressions · ${item.clicks} clicks · ${(item.ctr*100).toFixed(1)}% CTR · avg. position ${item.position.toFixed(1)}</p><div class="issue-fix"><b>${esc(item.type)}: </b>${esc(item.recommendation)}</div><small>Page association: ${esc(item.page_match_confidence||'none')} · ${esc(item.page_match_evidence||'Landing page not established.')}</small></div></div>`).join('')}
      <p class="muted small" style="margin-top:14px">Suggestions do not predict traffic or guarantee rankings. The source is user-uploaded query data and a separately timed site crawl; verify landing pages and query intent before editing.</p></section>`;
  }

  function insightsView(){
    const siteId=state.gscSiteId||state.websites[0]?.id||'';
    const latest=latestFor(siteId), r=state.report;
    const counts=latest?.summary?.severity_counts||{};
    const header=heading('RECOMMENDATION ENGINE','Intelligence insights','Connect real query evidence with content and technical checks.',latest?button(`${icon('arrow')} View latest report`,'open-report','btn-primary',`data-id="${latest.id}"`):'');
    const notice='<div class="notice"><strong>Evidence and limitations:</strong> GSC Queries CSV metrics are supplied by the user. Page matches are only candidates based on fetched HTML, never confirmed Google landing pages. Local recommendations are deterministic; optional model commentary requires Ollama.</div>';
    const gsc=gscPanel();
    const combined=combinedActionPlan(siteId);
    const auditAvailable=latest&&auditState(latest)!=='failed';
    if(!auditAvailable){
      return `${header}${notice}${gsc}${combined}<section class="card panel">${latest?'<div class="notice notice-warning">The latest audit did not fetch usable HTML. Review the report before making on-page changes.</div>':empty('spark','Run a technical audit to add page evidence','Imported GSC statistics can still be reviewed, but content matching needs a successful crawl.',button('Open websites','go-websites','btn-outline'))}</section>`;
    }
    const topics=latest?.summary?.content_analysis?.keywords?.length?
      `<section class="card panel" style="margin-bottom:20px"><div class="panel-heading"><h3>Top observed page topics</h3></div><div class="keyword-list">${latest.summary.content_analysis.keywords.slice(0,12).map(k=>`<span class="keyword-chip">${esc(k.term)} <strong>${k.occurrences_on_scanned_pages}×</strong></span>`).join('')}</div><p class="muted small">On-page frequency, not search volume. Open the full report for page-by-page evidence.</p></section>`:'';
    const loaded=r?.audit.id===latest.id;
    const findings=loaded?
      `<div><p class="muted small" style="margin-bottom:14px">Showing the first six saved audit findings here, without navigating away from Insights.</p>${findingsHtml(r.findings.slice(0,6),'all')}</div>`:
      `<div class="empty"><div class="empty-symbol">${icon('spark',25)}</div><h4>View saved audit recommendations here</h4><p>Keep your Search Console table and technical findings on the same screen.</p>${button('Load recommendations here','load-recommendations','btn-primary',`data-id="${latest.id}"`)}</div>`;
    return `${header}${notice}${gsc}${combined}${topics}<div class="stat-grid">${stat('Critical',counts.critical||0,'Highest-priority fixes','alert','rose')}${stat('High',counts.high||0,'Important issues','activity','peach')}${stat('Medium',counts.medium||0,'Improvements','spark','lilac')}${stat('Low',counts.low||0,'Polish opportunities','check','mint')}</div><section class="card panel"><div class="panel-heading"><div><h3>Latest report recommendations</h3><div class="panel-sub">${esc(latest.site.name)} · Scan ${fmt(latest.created_at)}</div></div>${button('Open complete report','open-report','btn-outline',`data-id="${latest.id}"`)}</div>${findings}</section>`;
  }
  function settingsView(){const org=state.orgs.find(x=>x.id===state.orgId);return `${heading('YOUR ACCOUNT','Workspace settings','Your workspace profile, security and integration status.')}<div class="grid-two"><section class="card panel"><div class="panel-heading"><h3>Account profile</h3></div><div class="form-row"><label>Name</label><input class="field" readonly value="${esc(state.user?.full_name||'')}"/></div><div class="form-row"><label>Email address</label><input class="field" readonly value="${esc(state.user?.email||'')}"/></div><div class="form-row"><label>Organization</label><input class="field" readonly value="${esc(org?.name||'None selected')}"/></div><p class="small muted">Organization access is enforced in the API. This page is read-only.</p></section><section class="card panel"><div class="panel-heading"><h3>Product configuration</h3></div><div class="issue-card"><div class="issue-head"><h4>Technical SEO scanner</h4><span class="tag tag-success">Available</span></div><p>Public HTML audits with bounded page limits and private network blocking.</p></div><div class="issue-card"><div class="issue-head"><h4>Free local intelligence</h4><span class="tag tag-success">No API key needed</span></div><p>Evidence-backed action plans run locally. Optional genuine language-model explanations use Ollama installed on your own computer; hardware and download required.</p></div><a class="btn btn-outline" href="/docs" target="_blank" rel="noopener noreferrer">${icon('external',15)} Browse API docs</a></section></div><section class="card panel" style="margin-top:20px;max-width:640px"><div class="panel-heading"><h3>${icon('shield',17)} Change account password</h3></div><p class="small muted" style="margin-bottom:18px">After changing your password, all sessions are invalidated and you must sign in again.</p><form id="change-password-form"><div class="form-row"><label for="old-password">Current password</label><input type="password" id="old-password" class="field" minlength="8" required autocomplete="current-password" /></div><div class="form-row"><label for="new-password">New password</label><input type="password" id="new-password" class="field" minlength="8" required autocomplete="new-password" /></div><button class="btn btn-primary" type="submit">Update password ${icon('arrow',15)}</button></form></section>`}
  function modal(){document.getElementById('modal-root').innerHTML=`<div class="modal-backdrop" data-action="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><button type="button" class="close-btn" data-action="close-modal" aria-label="Close">${icon('close',16)}</button><div class="auth-topicon" style="margin-bottom:19px">${icon('globe',24)}</div><h2 id="modal-title">Add a website</h2><p>Track a public website. You can run a technical audit once it's added.</p><form id="site-form"><div class="form-row"><label for="site-name">Website name</label><input class="field" id="site-name" name="name" required minlength="2" maxlength="160" placeholder="e.g. Northstar Studio" /></div><div class="form-row"><label for="site-url">Website URL</label><input class="field" id="site-url" name="url" type="url" required placeholder="https://example.com" /></div><div class="check-line">The scanner requests only public HTML pages and respects robots.txt. Only scan websites you are authorized to assess.</div><div class="modal-actions"><button type="button" class="btn btn-outline" data-action="close-modal">Cancel</button><button class="btn btn-primary" type="submit">${icon('plus',16)} Add website</button></div></form></div></div>`;
    document.getElementById('site-form').onsubmit=async e=>{e.preventDefault();const form=e.target,b=form.querySelector('button[type=submit]');b.disabled=true;b.textContent='Adding…';try{const fd=new FormData(form);await request(`/organizations/${state.orgId}/websites`,{method:'POST',json:{name:fd.get('name'),url:fd.get('url')}});closeModal();await refreshData();state.page='websites';render();toast('Website added. Ready for its first scan!')}catch(err){toast(err.message,true);b.disabled=false;b.textContent='Add website'}};
  }
  function closeModal(){const el=document.getElementById('modal-root');if(el)el.innerHTML=''}
  async function scan(id){
    if(state.busy)return;
    state.busy=true;
    toast('Audit queued. The background worker is fetching public pages…');
    const buttons=document.querySelectorAll(`[data-action="run-scan"]`);
    buttons.forEach(b=>{b.disabled=true;b.textContent='Queued…'});
    try{
      let job=await request(`/websites/${id}/jobs`,{method:'POST'});
      for(let i=0;i<100 && job.status!=='completed' && job.status!=='failed';i++){
        if(i===0)toast('Scan is queued. You can keep this tab open to follow progress.');
        await new Promise(resolve=>setTimeout(resolve,2000));
        job=await request(`/websites/${id}/jobs/${job.id}`);
        buttons.forEach(b=>{b.textContent=job.status==='running'?'Analyzing pages…':'In queue…'});
      }
      if(job.status==='failed')throw new Error(job.error||'The scan worker reported an error.');
      if(job.status!=='completed'||!job.audit_id)throw new Error('Scan is still queued or running. Check that the scan worker started; reload your audit history later.');
      await refreshData();
      state.report=await request(`/audits/${job.audit_id}`);
      state.page='reports';render();
      const a=state.report.audit;
      toast(auditState(a)==='failed'?'Scan could not retrieve HTML — review diagnostics.':`Audit ${auditState(a)}: ${pagesAnalyzed(a)} pages, ${a.issues_count} findings.`,auditState(a)==='failed');
    }catch(err){toast(err.message,true);render()}
    finally{state.busy=false}
  }

  async function loadRecommendations(id){
    try{
      state.report=await request(`/audits/${id}`);
      state.page='insights';
      render();
      toast('Audit recommendations loaded alongside Search Console insights.');
    }catch(err){toast(err.message,true)}
  }
  async function openReport(id){try{state.report=await request(`/audits/${id}`);state.page='reports';state.filter='all';render();window.scrollTo({top:0,behavior:'smooth'})}catch(err){toast(err.message,true)}}
  async function getAI(id){const el=document.getElementById('ai-narrative');if(!el)return;el.classList.remove('hidden');el.innerHTML='<div class="notice">Requesting optional AI analysis…</div>';try{const data=await request(`/audits/${id}/ai-analysis`,{method:'POST'});el.innerHTML=`<section class="issue-card"><div class="issue-head"><h4>${data.mode==='local_llm'?'Locally generated AI analysis':'Evidence-based action plan'}</h4><span class="tag tag-violet">${esc(data.model)}</span></div><p style="white-space:pre-wrap;color:#46516b">${esc(data.analysis)}</p><div class="issue-meta">${data.mode==='local_llm'?'Locally generated model output; verify all claims.':'Deterministic rules and provided data; not a generative AI model.'}</div></section>`;el.scrollIntoView({behavior:'smooth',block:'center'})}catch(err){el.innerHTML=`<div class="notice"><strong>AI unavailable:</strong> ${esc(err.message)}</div>`}}
  async function downloadCsv(id){try{const res=await fetch(API+`/audits/${id}/export.csv`,{headers:{Authorization:`Bearer ${state.token}`}});if(!res.ok)throw new Error('Could not download report.');const blob=await res.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`aip-seo-audit-${id}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000)}catch(err){toast(err.message,true)}}
  document.addEventListener('change',e=>{if(e.target?.id==='gsc-site-select')return loadGsc(e.target.value);if(e.target?.id==='severity-filter'&&state.report){state.filter=e.target.value;document.getElementById('findings-list').innerHTML=findingsHtml(state.report.findings,state.filter)}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
  document.addEventListener('click',async e=>{
    const el=e.target.closest('[data-action]');if(!el)return;
    const action=el.dataset.action;
    if(action==='modal-backdrop'&&e.target!==el)return;
    if(action==='sign-in')return authView('login');
    if(action==='sign-up')return authView('register');
    if(action==='verify')return authView('verify');
    if(action==='forgot')return authView('forgot');
    if(action==='resend-verification'){try{await request('/auth/resend-verification',{method:'POST',json:{email:el.dataset.email||document.getElementById('email')?.value}});toast('If verification is pending, another code was sent.')}catch(err){toast(err.message,true)}return}
    if(action==='logout')return signOut();
    if(action==='navigate'){state.page=el.dataset.page;state.report=null;render();window.scrollTo(0,0);return}
    if(action==='open-gsc'){state.page='insights';state.gscSiteId=el.dataset.id;render();return loadGsc(el.dataset.id)}
    if(action==='load-gsc')return loadGsc(el.dataset.id);
    if(action==='import-gsc')return importGsc(el.dataset.id);
    if(action==='go-websites'){state.page='websites';render();return}
    if(action==='menu'){document.getElementById('sidebar')?.classList.toggle('open');return}
    if(action==='new-website')return modal();
    if(action==='close-modal'||action==='modal-backdrop')return closeModal();
    if(action==='run-scan')return scan(el.dataset.id);
    if(action==='open-report')return openReport(el.dataset.id);
    if(action==='load-recommendations')return loadRecommendations(el.dataset.id);
    if(action==='csv')return downloadCsv(el.dataset.id);
    if(action==='ai')return getAI(el.dataset.id);
    if(action==='close-report'){state.report=null;render();return}
    if(action==='delete-site'){const s=state.websites.find(x=>x.id===el.dataset.id);if(!s||!window.confirm(`Delete ${s.name} and all saved audits?`))return;try{await request(`/websites/${s.id}`,{method:'DELETE'});await refreshData();render();toast('Website deleted.')}catch(err){toast(err.message,true)}}
  });
  if(state.token)initialize();else authView();
})();
