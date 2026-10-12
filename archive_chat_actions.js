/* ChatGPT Local Archive v7.3.16. Chat-local controls. No DOM rewriting of
 * existing answers, attachments, MathJax, DIL, questions, or file registry. */
(() => {
  'use strict';
  if (window.__archiveExtraActionsV7316) return;
  window.__archiveExtraActionsV7316 = true;
  const style = document.createElement('style');
  style.textContent = `
    .archive-v316-toolbar{display:inline-flex;align-items:center;justify-content:flex-end;gap:3px;margin-left:auto;flex-wrap:wrap}
    .archive-v316-btn{box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;width:32px;height:30px;border:1px solid transparent;background:transparent;border-radius:7px;color:#657480;cursor:pointer;vertical-align:middle;padding:5px}
    .archive-v316-btn:hover,.archive-v316-btn:focus-visible{background:#eef6f3;color:#0b7b64;border-color:#d5e9e1}
    .archive-v316-btn:focus-visible{outline:2px solid #15866d;outline-offset:1px}
    .archive-v316-btn[disabled]{opacity:.4;cursor:not-allowed}
    .archive-v316-btn svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
    .archive-v316-feedback{font:12px/1.4 system-ui,sans-serif;color:#28745b;margin:0 2px}
    .archive-v316-user-actions{display:flex;justify-content:flex-end;margin:7px 0 0}
    .archive-v316-user-actions .archive-v316-btn{width:28px;height:27px}
    .archive-v316-code{position:relative}
    .archive-v316-code-button{position:absolute!important;z-index:3;top:6px;right:6px;border-color:#e1e5e8;background:#fff;box-shadow:0 1px 3px #0001}
    .archive-v316-code{padding-top:40px!important}
    @media(max-width:720px){.archive-v316-toolbar{margin-left:0}#archive-display-options{align-items:flex-start}}
    @media print{.archive-v316-toolbar,.archive-v316-user-actions,.archive-v316-code-button{display:none!important}}
  `;
  document.head.appendChild(style);
  const svgCopy='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"/></svg>';
  const svgDown='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 17v3h14v-3"/></svg>';
  const svgOut='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9"/><path d="M20 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h6"/></svg>';
  function button(icon,label){const b=document.createElement('button');b.type='button';b.className='archive-v316-btn';b.title=label;b.setAttribute('aria-label',label);b.innerHTML=icon;return b;}
  function clean(v){return String(v||'').replace(/\u00a0/g,' ').replace(/[ \t]+\n/g,'\n').trim();}
  function md(node){
    if (node.nodeType===Node.TEXT_NODE)return node.nodeValue||'';
    if (node.nodeType!==Node.ELEMENT_NODE)return '';
    if (node.closest('.archive-v316-toolbar,.archive-v316-user-actions,.archive-copy-actions,.ui-source,.archive-v316-code-button') ||
        node.matches('script,style,button'))return '';
    const tag=node.tagName.toLowerCase();
    if(tag==='br')return '\n';
    if(tag==='img')return '!['+(node.getAttribute('alt')||'Изображение').replace(/\]/g,'\\]')+']('+(node.getAttribute('src')||'')+')';
    if(tag==='mjx-container')return '[Формула]';
    if(tag==='svg')return '[SVG]';
    let children=Array.from(node.childNodes).map(md).join('');
    if(tag==='a')return '['+clean(children)+']('+(node.getAttribute('href')||'')+')';
    if(tag==='strong'||tag==='b')return '**'+clean(children)+'**';
    if(tag==='em'||tag==='i')return '*'+clean(children)+'*';
    if(tag==='code'&&!node.closest('pre'))return '`'+children+'`';
    if(tag==='pre'){const c=node.querySelector('code')||node;const lang=(c.className||'').match(/language-([\w+-]+)/)?.[1]||'';return '\n\n```'+lang+'\n'+c.textContent.replace(/^\n+|\n+$/g,'')+'\n```\n\n';}
    if(/^h[1-6]$/.test(tag))return '\n\n'+'#'.repeat(+tag[1])+' '+clean(children)+'\n\n';
    if(tag==='li')return '- '+clean(children)+'\n';
    if(tag==='p'||tag==='div'||tag==='figure'||tag==='ul'||tag==='ol'||tag==='blockquote')return '\n\n'+clean(children)+'\n\n';
    return children;
  }
  function legacyCopy(value){
    const e=document.createElement('textarea');e.value=value;e.readOnly=true;
    e.style.cssText='position:fixed;left:-10000px;top:0;width:1px;height:1px;opacity:0';
    document.body.appendChild(e);e.focus({preventScroll:true});e.select();
    let ok=false;try{ok=!!document.execCommand('copy');}catch(_){}e.remove();return ok;
  }
  async function copy(value){
    // Must try synchronous execCommand before any await: sandboxed iframe has
    // opaque origin and Clipboard API is often unavailable.
    if(legacyCopy(value))return true;
    if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(value);return true;}catch(_){}}
    return false;
  }
  const feedback=(button,success,successText='✓')=>{
    const saved=button.title;button.title=success?successText:'Не удалось скопировать';
    button.style.color=success?'#128269':'#b33d3d';
    setTimeout(()=>{button.title=saved;button.style.removeProperty('color');},1900);
  };
  function enhanceUser(article){
    if(article.dataset.archiveQuestionCopy==='1')return;
    const role=Array.from(article.children).find(x=>x.classList?.contains('role'));
    const body=Array.from(article.children).find(x=>x.classList?.contains('body'));
    if(!role?.classList.contains('user')||!body)return;
    article.dataset.archiveQuestionCopy='1';
    const row=document.createElement('div');row.className='archive-v316-user-actions';
    const b=button(svgCopy,'Скопировать вопрос');row.appendChild(b);body.appendChild(row);
    b.addEventListener('click',async()=>{const value=clean(md(body));feedback(b,!!value&&await copy(value));});
  }
  function trueCode(pre){
    if(pre.closest('.ui-source,.structure,.dil-v7-row,.dil-row,.dil-v7-badge,.dil-badge,.math,.dil-v7-title'))return false;
    const code=pre.querySelector(':scope > code');
    if(!code)return false;
    // Short one-line DIL captions (including **...**) are not code blocks.
    const cls=String(code.className||'');
    const source=code.textContent||'';
    const actualLang=/(?:^|\s)(?:language|lang)-[\w+#-]+/.test(cls);
    const multiline=source.includes('\n');
    return actualLang || multiline;
  }
  function enhanceCode(pre){
    if(pre.dataset.archiveCodeCopy==='1'||!trueCode(pre))return;
    pre.dataset.archiveCodeCopy='1';pre.classList.add('archive-v316-code');
    const b=button(svgCopy,'Скопировать код');b.classList.add('archive-v316-code-button');
    pre.appendChild(b);
    b.addEventListener('click',async e=>{e.stopPropagation();
      const c=pre.querySelector(':scope > code');feedback(b,!!c&&await copy(c.textContent||''));});
  }
  function toolbar(){
    const header=document.querySelector('body > header');if(!header)return;
    const date=header.querySelector('.date');
    let strip=header.querySelector('#archive-display-options');
    if(!strip){strip=document.createElement('div');strip.id='archive-display-options';
      strip.style.cssText='display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:10px';
      if(date)date.insertAdjacentElement('afterend',strip);else header.appendChild(strip);
      const old=header.querySelector('#archive-structured-toggle');if(old)strip.appendChild(old);
    }
    const actions=document.createElement('div');actions.className='archive-v316-toolbar';
    const status=document.createElement('span');status.className='archive-v316-feedback';status.setAttribute('role','status');
    const full=button(svgCopy,'Скопировать весь чат');
    const save=button(svgDown,'Сохранить чат в Markdown (.md)');
    const link=document.createElement('a');link.className='archive-v316-btn';link.innerHTML=svgOut;
    link.title='Открыть исходный чат на chatgpt.com';link.setAttribute('aria-label',link.title);
    link.target='_blank';link.rel='noopener noreferrer';
    // Only real export IDs are accepted. The local HTML filename is NEVER a chat ID.
    const id=window.__archiveOriginalConversationId;
    if(typeof id==='string'&&/^[A-Za-z0-9_-]{8,128}$/.test(id)){
      link.href='https://chatgpt.com/c/'+encodeURIComponent(id);
    }else{link.removeAttribute('href');link.style.opacity='.35';link.title='В экспорте не найден оригинальный ID чата';link.setAttribute('aria-disabled','true');}
    const chat=location.pathname.match(/\/(chat_\d{7}_[0-9a-f]{8})\.html$/);
    if(chat){save.addEventListener('click',()=>{
      // Export with the human-readable chat title. Sanitization affects only
      // filename-forbidden characters, never the contents of the Markdown.
      const raw=document.querySelector('body > header h1')?.textContent||'';
      let filename=(raw.trim()||chat[1]).normalize('NFC')
        .replace(/[<>:"/\\|?*\x00-\x1F\x7F]/g,'_')
        .replace(/\s+/g,' ').replace(/[. ]+$/g,'').slice(0,120).replace(/[. ]+$/g,'');
      if(!filename)filename=chat[1];
      if(/^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(filename))filename='_'+filename;
      const a=document.createElement('a');a.href='../__chat_md_download/'+chat[1]+'.md';
      a.download=filename+'.md';document.body.appendChild(a);a.click();a.remove();
    });}else save.disabled=true;
    full.addEventListener('click',async()=>{
      const text=window.__archiveChatMarkdown;
      if(typeof text!=='string'||!text.trim()){
        status.textContent='Текст исходного чата пока недоступен';return;
      }
      if(text.length>4_000_000){status.textContent='Большой чат: используйте сохранение .md';return;}
      const ok=await copy(text);status.textContent=ok?'✓ Чат скопирован':'Не удалось скопировать; сохраните .md';
      setTimeout(()=>status.textContent='',3000);
    });
    actions.append(status,full,save,link);strip.append(actions);
  }
  function init(){
    toolbar();document.querySelectorAll('article').forEach(enhanceUser);
    document.querySelectorAll('article > .body pre').forEach(enhanceCode);
    // Alternative Markdown UI fragments are inserted lazily after switching.
    // Observe only newly inserted PRE nodes, not expensive math SVG mutations.
    if(window.MutationObserver){
      const observer=new MutationObserver(records=>{
        for(const record of records)for(const node of record.addedNodes){
          if(node.nodeType!==1)continue;
          if(node.tagName==='PRE')enhanceCode(node);
          else if(node.querySelectorAll)node.querySelectorAll('pre').forEach(enhanceCode);
        }
      });
      observer.observe(document.body,{childList:true,subtree:true});
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
