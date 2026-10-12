/* v7.3.16 — metadata decorations on existing VIRTUALIZED rows. No changes
 * to legacy renderRows, search filters, calendar, or iframe navigation. */
(() => {
  'use strict';
  if(window.__archiveListMetaV7316)return;
  window.__archiveListMetaV7316=true;
  const style=document.createElement('style');
  style.textContent=`
    .row small.archive-v316-meta{display:flex!important;align-items:center;gap:8px;width:100%;font:10px/1.4 system-ui,sans-serif;white-space:nowrap;overflow:hidden;min-height:14px}
    .row small.archive-v316-meta span{display:inline-flex;align-items:center;width:auto;flex:0 0 auto;gap:3px;white-space:nowrap;font-weight:400;overflow:visible}
    .archive-v316-archived{background:#e7f3ff;color:#3474ad;border-radius:8px;padding:1px 5px;line-height:1.3}
    .archive-v316-meta svg{width:11px;height:11px;fill:none;stroke:currentColor;stroke-width:1.6}
    @media(max-width:720px){.row small.archive-v316-meta{gap:4px;font-size:9px}}
  `;
  document.head.appendChild(style);
  const iconQuestions='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg>';
  const iconImages='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m4 18 5-6 4 3 3-5 5 8"/></svg>';
  let entries=new Map(), extra=new Map(),lastUpdate=0;
  const rows=document.getElementById('rows');
  if(!rows)return;
  function relatedHref(link){
    try{const u=new URL(link,document.baseURI);const m=u.pathname.match(/\/chats\/(chat_\d{7}_[a-f0-9]{8}\.html)$/);return m?'chats/'+m[1]:null;}
    catch(_){return null;}
  }
  function add(el,value,icon,title,archived=false){
    const x=document.createElement('span');x.title=title;
    if(archived){x.className='archive-v316-archived';x.textContent='archived';}
    else{x.innerHTML=icon;x.append(document.createTextNode(' '+String(value)));}
    el.appendChild(x);
  }
  function render(){
    for(const el of rows.querySelectorAll('a.row')){
      const href=relatedHref(el.getAttribute('href'));
      const m=entries.get(href);
      if(!m)continue;
      const old=el.querySelector(':scope > small');
      if(!old||old.dataset.archiveMetaV316==='1')continue;
      old.dataset.archiveMetaV316='1';old.classList.add('archive-v316-meta');
      const date=old.textContent||'';old.textContent=date;
      add(old,Number(m.questions)||0,iconQuestions,'Вопросов пользователя');
      const imgs=new Set(m.image_assets||[]);
      for(const asset of extra.get(href)||[])imgs.add(asset);
      if(imgs.size||m.images){add(old,Math.max(imgs.size,Number(m.images)||0),iconImages,'Уникальных локальных изображений в чате');}
      if(m.is_archived===true)add(old,'',null,'Архивировано в ChatGPT',true);
    }
  }
  const observer=new MutationObserver(()=>render());
  observer.observe(rows,{childList:true});
  async function load(){
    try{
      const r=await fetch('chat_metadata_index.json',{cache:'no-store'});
      if(!r.ok)return;
      const data=await r.json();
      entries=new Map((data.chats||[]).map(item=>[item.href,item]));
      render();
      await updateRecovered();
    }catch(err){console.warn('Chat metadata is unavailable:',err);}
  }
  async function updateRecovered(){
    if(Date.now()-lastUpdate<3000)return;
    lastUpdate=Date.now();
    try{
      const r=await fetch('recovered_files.json',{cache:'no-store'});
      if(!r.ok)return;
      const data=await r.json();const m=new Map();
      for(const entry of Object.values(data)){
        if(!entry||!entry.asset_name||!(/\.(?:png|jpe?g|gif|webp|svg|bmp|avif)$/i).test(entry.asset_name))continue;
        const related=entry.hrefs||[entry.href];
        for(const href of related){
          if(!entries.has(href))continue;
          if(!m.has(href))m.set(href,new Set());
          m.get(href).add(entry.asset_name);
        }
      }
      extra=m;
      for(const el of rows.querySelectorAll('a.row small.archive-v316-meta'))el.removeAttribute('data-archive-meta-v316');
      // Remove previously appended markers before recreating the row metadata.
      for(const el of rows.querySelectorAll('a.row small.archive-v316-meta')){
        while(el.children.length)el.lastElementChild.remove();
        el.dataset.archiveMetaV316='';
      }
      render();
    }catch(_){} // The registry is optional in a fresh archive.
  }
  window.addEventListener('focus',()=>updateRecovered());
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)updateRecovered();});
  load();
})();
