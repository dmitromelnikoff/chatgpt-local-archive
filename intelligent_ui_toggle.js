/* ChatGPT Local Archive v7.3.14: Intelligent UI ON = original, OFF = readable Markdown.
 * Does not alter saved HTML, MathJax configuration, recovery, or copied files.
 * Server builds safe Markdown HTML from ORIGINAL FULL DIL source. The alternate
 * is a single contiguous document: normal paragraphs, SVG labels, tables and
 * TeX all retain their original position. No raw DIL in the reading view.
 */
(() => {
  'use strict';
  if (window.__archiveIntelligentUiToggleV739) return;
  window.__archiveIntelligentUiToggleV739 = true;
  const parts = [];
  const pending = new Map();
  let enabled = true;
  let observer = null;
  const filenameRegex = /^chat_\d{7}_[a-f0-9]{8}_ui_\d{4}\.txt$/;

  // v7.3.14: fix EXACT user-exported HTML where Markdown-in-DIL <row>
  // is rendered as UNCLASSIFIED <pre><code>**Label**</code></pre>.
  // Based on an anonymized DIL regression case containing nested labels.
  // Previous patches matched only
  // <pre class="dil-v7-code"> so could never repair these genuine cases.
  // v7.3.13: also recognize short, whole-bold labels rendered as DIL codeblocks.
  // v7.3.12: process text at ANY depth inside rendered DIL, not just
  // immediate text children. v7.3.11 missed nested spans and pill/code labels
  // with fully bold labels. Never touch raw source, actual code
  // blocks, TeX, SVG or ordinary chat Markdown.
  const dilSelector = '[class*="dil-v7-"],[class*="dil-"]';
  const protectedSelector = 'pre,kbd,samp,script,style,textarea,svg,.math,.MathJax,mjx-container,details.ui-source,.archive-intelligent-text,.archive-intelligent-markdown';
  const inlineBoldPattern = /(^|[^\\*])\*\*(?!\*)([^\*\r\n]*?\S[^\*\r\n]*?)\*\*(?!\*)/g;
  const wholeBoldPattern = /^\*\*([^*\r\n]*\S[^*\r\n]*)\*\*$/;

  // These are emitted by archive_render_v7.py for <codeblock> nodes:
  // <pre class="dil-v7-code"><code>**Example Label**</code></pre>.
  // V7.3.11/12 explicitly skipped <pre>, so no amount of span/badge traversal
  // could change those labels. Scope to DIL *codeblock* classes only, and to
  // a SINGLE short label, never general code, MathJax or source previews.
  function repairDILCodeLabel(pre) {
    if (!pre || pre.tagName !== 'PRE') return;
    const explicitDILCode = pre.matches('pre.dil-v7-code,pre.dil-code');
    // Mistune sometimes emits <pre><code> without ANY class for Markdown
    // content nested directly in a DIL <row>. Precisely constrain the fix
    // to those directly contained UI rows; do not reinterpret normal code.
    const unclassedDILRowLabel = !pre.hasAttribute('class') &&
      pre.parentElement?.matches('.dil-v7-row,.dil-row') &&
      pre.closest('.dil-v7-box,.dil-box');
    if (!explicitDILCode && !unclassedDILRowLabel) return;
    if (!pre.closest('article > .body') || pre.closest('details.ui-source,.archive-intelligent-text,.archive-intelligent-markdown,.math,mjx-container,svg')) return;
    const children=Array.from(pre.children);
    if (children.length > 1 || (children.length===1 && children[0].tagName!=='CODE')) return;
    const code=children.length===1 ? children[0] : pre;
    if (code!==pre && (code.className && /(?:language-|lang-|hljs|highlight)/i.test(String(code.className)))) return;
    if (code.querySelector('*')) return;
    const raw=code.textContent;
    if (!raw || raw.length>245 || raw.trim().includes('\n') || raw.trim().includes('\r')) return;
    const match=/^\s*\*\*([^*\r\n]{1,210}\S)\*\*\s*$/.exec(raw);
    if (!match) return;
    // Preserve existing dimensions/appearance and convert only this one
    // whole-bold UI label. TextContent is used: no HTML execution possible.
    const strong=document.createElement('strong');
    strong.textContent=match[1];
    code.replaceChildren(strong);
  }

  function repairBoldTextNode(node) {
    if (!node || node.nodeType !== 3 || !node.data.includes('**') || node.data.length > 50000) return;
    const parent = node.parentElement;
    if (!parent || !parent.closest(dilSelector)) return;
    // Process DIL-generated <pre> before protectedSelector rejects it.
    const pre=parent.closest('pre');
    if (pre) { repairDILCodeLabel(pre); return; }
    if (parent.closest(protectedSelector)) return;

    // Inline <code> within a visual DIL label can contain a single Markdown
    // emphasis token. Convert only whole, single-line labels. Genuine fenced
    // code (<pre>, .dil-v7-code), snippets, or arbitrary code are untouched.
    if (parent.tagName === 'CODE') {
      const label = parent.textContent;
      const match = label.length <= 240 ? wholeBoldPattern.exec(label) : null;
      if (!match || parent.closest('.dil-v7-code') || parent.childNodes.length !== 1) return;
      // In UI badges/titles an inline-code wrapper is not a code sample.
      const nearestDIL = parent.closest(dilSelector);
      if (!nearestDIL || !nearestDIL.matches('.dil-v7-badge,.dil-v7-pill,.dil-v7-tag,.dil-v7-button,.dil-v7-title,.dil-v7-box')) return;
      // A larger box is only treated as a label when the code is its
      // sole meaningful child, never a snippet in a normal DIL text span.
      if (nearestDIL.matches('.dil-v7-box')) {
        const nonblank = Array.from(nearestDIL.childNodes).filter(x => x.nodeType===1 || x.textContent.trim());
        if (nonblank.length !== 1 || nonblank[0] !== parent) return;
      }
      const strong = document.createElement('strong');
      strong.textContent = match[1];
      parent.replaceWith(strong);
      return;
    }
    if (parent.closest('code')) return;

    const original = node.data;
    const fragment = document.createDocumentFragment();
    let cursor = 0, found = false, match;
    inlineBoldPattern.lastIndex = 0;
    while ((match = inlineBoldPattern.exec(original)) !== null) {
      const label = match[2];
      if (!label || label.trim() !== label) continue;
      const start = match.index + match[1].length;
      fragment.appendChild(document.createTextNode(original.slice(cursor, start)));
      const strong = document.createElement('strong');
      strong.textContent = label;
      fragment.appendChild(strong);
      cursor = start + label.length + 4;
      found = true;
    }
    if (found) {
      fragment.appendChild(document.createTextNode(original.slice(cursor)));
      node.replaceWith(fragment);
    }
  }

  function repairDILBold(root) {
    if (!root) return;
    const nodes = [];
    if (root.nodeType === 3) { nodes.push(root); }
    else if (root.nodeType === 1 || root.nodeType === 9 || root.nodeType === 11) {
      // Narrow to UI subtrees even on thousand-message archive pages.
      const roots = [];
      if (root.nodeType === 1 && root.closest(dilSelector)) roots.push(root);
      else if (root.querySelectorAll) {
        for (const el of root.querySelectorAll(dilSelector)) {
          if (!el.parentElement || !el.parentElement.closest(dilSelector)) roots.push(el);
        }
      }
      for (const uiRoot of roots) {
        const walk = document.createTreeWalker(uiRoot, NodeFilter.SHOW_TEXT);
        let t;
        while ((t = walk.nextNode())) if (t.data.includes('**')) nodes.push(t);
      }
    }
    // DOM replacements are done after traversal; no iterator invalidation.
    for (const n of nodes) repairBoldTextNode(n);
  }

  function watchNewDILBold() {
    if (!window.MutationObserver || !document.body) return;
    const obs = new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.nodeType === 3) {
            if (node.data.includes('**')) repairBoldTextNode(node);
          } else if (node.nodeType === 1) {
            if (node.closest(dilSelector) || node.querySelector(dilSelector)) repairDILBold(node);
          }
        }
      }
    });
    obs.observe(document.body, {childList: true, subtree: true});
  }

  const create = (tag, className, value) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = value;
    return el;
  };
  const summary = el => Array.from(el.children).find(x=>x.tagName==='SUMMARY')?.textContent?.trim()||'';
  function filenameOf(source) {
    const link = source.querySelector('a[download][href]');
    const match = /^\.\.\/dil_sources\/([^?#]+)$/.exec(link?.getAttribute('href') || '');
    if (!match) return null;
    try { const name=decodeURIComponent(match[1]);return filenameRegex.test(name)?name:null; }
    catch (_) { return null; }
  }
  const hasDIL = node => node.nodeType === 1 &&
    (Array.from(node.classList).some(c=>c.startsWith('dil-v7-')||c.startsWith('dil-')) ||
     Boolean(node.querySelector('[class*="dil-v7-"],[class*="dil-"]')));
  const sourceBoundary = node => node.nodeType === 1 && node.matches('details.ui-source');

  function renderedNodes(source) {
    // The exporter generates <rendered source> directly before <details.ui-source>.
    // Every node between the previous UI source and this <details> belongs to
    // THIS source — including Markdown headings, tables and formulas. Hiding
    // only .dil-* nodes (v7.3.8 bug) left these fragments detached/duplicated.
    const group=[];
    let n=source.previousElementSibling;
    while(n && !sourceBoundary(n) &&
          !n.matches('.archive-intelligent-text,.archive-copy-actions,.library-media,.generated-output,.file-entry')) {
      group.unshift(n);
      n=n.previousElementSibling;
    }
    if (!group.some(hasDIL)) return [];
    return group;
  }
  function fallbackDetails(source) {
    const next=source.nextElementSibling;
    return next?.matches('details.ui-source') && /Текстовая версия Intelligent UI\s*\(fallbackMarkdown\)/i.test(summary(next)) ? next : null;
  }
  function register(source) {
    if (!source.matches('details.ui-source') || source.classList.contains('structure')) return;
    if (!/Исходн.*Intelligent UI|Исходная разметка Intelligent UI/i.test(summary(source))) return;
    const filename=filenameOf(source);
    if (!filename || !source.closest('article > .body')) return;
    const rendered=renderedNodes(source);
    if (!rendered.length) return;
    const fallback=fallbackDetails(source);
    const alt=create('section','archive-intelligent-text ui-source');
    alt.setAttribute('aria-label','Читаемая Markdown-версия Intelligent UI');
    alt.appendChild(create('div','archive-intelligent-caption','Markdown · читаемая версия Intelligent UI'));
    const reader=create('div','archive-intelligent-markdown');
    reader.appendChild(create('p','archive-intelligent-loading','Загрузка Markdown…'));
    alt.appendChild(reader);
    const link=source.querySelector('a[download]');
    if (link) {
      const action=link.cloneNode(true);
      action.textContent='📄 Скачать исходный DIL (без преобразования)';
      action.className='archive-intelligent-download';
      alt.appendChild(action);
    }
    (fallback||source).insertAdjacentElement('afterend',alt);
    rendered.forEach(node=>node.classList.add('archive-intelligent-rendered'));
    source.classList.add('archive-intelligent-original');
    if (fallback) fallback.classList.add('archive-intelligent-original');
    const part={source,rendered,fallback,alt,reader,filename,status:'initial'};
    parts.push(part);
  }
  function load(part) {
    if (part.status!=='initial') return;
    part.status='loading';
    const name=part.filename;
    if (!pending.has(name)) pending.set(name,[]);
    const callbacks=pending.get(name);callbacks.push(part);
    if (callbacks.length!==1) return;
    const script=document.createElement('script');
    script.src='../__intelligent_ui_markdown/'+encodeURIComponent(name);
    script.async=true;
    script.onerror=()=>{
      for (const p of pending.get(name)||[]) fail(p,'Не удалось загрузить Markdown.');
      pending.delete(name);script.remove();
    };
    script.onload=()=>script.remove();
    document.head.appendChild(script);
  }
  function fail(part,message) {
    part.status='error';
    part.reader.replaceChildren(create('p','archive-intelligent-error',message));
    if (part.fallback) {
      const fallback=create('div','archive-intelligent-fallback');
      Array.from(part.fallback.childNodes).filter(n=>n.nodeType!==1||n.tagName!=='SUMMARY')
        .forEach(n=>fallback.appendChild(n.cloneNode(true)));
      part.reader.appendChild(fallback);
    }
  }
  // Called only by the token-protected local server; HTML has already passed
  // through the escaping Mistune renderer. Raw DIL scripts are never evaluated.
  window.__archiveIntelligentUiMarkdownLoaded=(name,html,markdown,error,enhanced)=>{
    const items=pending.get(name)||[];pending.delete(name);
    for (const part of items) {
      if (typeof html!=='string') { fail(part,error||'Не удалось построить Markdown.');continue; }
      const wrap=create('div','archive-intelligent-content');
      wrap.innerHTML=html;
      part.reader.replaceChildren(wrap);
      part.status='loaded';
      // Only for sources with safely expanded declarative templates, replace
      // the incomplete ON rendering as a WHOLE. For every other source the
      // original visual rendering stays exactly as it was.
      if (typeof enhanced==='string' && enhanced.trim() && !part.enhanced) {
        const upgraded=create('div','archive-intelligent-enhanced');
        upgraded.innerHTML=enhanced;  // sanitized by the local Python DIL renderer
        repairDILBold(upgraded);
        const first=part.rendered[0];
        if (first?.parentNode) {
          first.parentNode.insertBefore(upgraded,first);
          part.rendered.forEach(x=>x.classList.add('archive-intelligent-template-original'));
          part.enhanced=upgraded;
          if (window.MathJax && typeof window.MathJax.typesetPromise==='function') {
            try {window.MathJax.typesetPromise([upgraded]).catch(()=>{});}catch(_){}
          }
        }
      }
      // Re-use the EXISTING local MathJax; no changes to TeX, parser, or options.
      if (window.MathJax && typeof window.MathJax.typesetPromise==='function') {
        try { window.MathJax.typesetPromise([wrap]).catch(()=>{}); } catch (_) {}
      }
    }
  };
  function prepareObserver() {
    if (!('IntersectionObserver' in window)) return;
    observer=new IntersectionObserver(entries=>{
      if (enabled) return;
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const part=parts.find(p=>p.alt===entry.target);
        if (part) load(part);
        observer.unobserve(entry.target);
      }
    },{rootMargin:'800px 0px'});
  }
  function setMode(value) {
    enabled=value;
    document.body.classList.toggle('archive-intelligent-off',!enabled);
    if (!enabled) {
      for (const part of parts) {
        if (part.status!=='initial') continue;
        if (observer) observer.observe(part.alt);
        else load(part);
      }
    } else if (observer) {
      for (const part of parts) observer.unobserve(part.alt);
    }
  }
  function boot() {
    repairDILBold(document); // Also works if a chat contains no switchable DIL source.
    watchNewDILBold(); // Also repair UI labels inserted after the initial page load.
    const header=document.querySelector('body > header');
    if (!header) return;
    document.querySelectorAll('article > .body > details.ui-source').forEach(register);
    if (!parts.length) return;
    const style=create('style');style.id='archive-intelligent-toggle-styles';
    style.textContent=`
      body.archive-intelligent-off .archive-intelligent-rendered,
      body.archive-intelligent-off .archive-intelligent-original {display:none!important}
      .archive-intelligent-template-original{display:none!important}
      body.archive-intelligent-off .archive-intelligent-enhanced{display:none!important}
      .archive-intelligent-text{display:none!important}
      body.archive-intelligent-off .archive-intelligent-text{display:block!important}
      .archive-intelligent-text{margin:12px 0 16px!important;border:1px solid #d8e4ee!important;border-radius:10px!important;background:#fff!important;padding:12px 16px!important;color:#263848!important;font-size:inherit!important;line-height:1.65!important}
      .archive-intelligent-caption{font-weight:650;color:#52667b;font-size:12px;margin-bottom:14px}
      .archive-intelligent-markdown .table-wrap{margin:12px 0 18px}
      .archive-intelligent-markdown table{width:max-content;min-width:100%}
      .archive-intelligent-markdown h1{font-size:21px;margin-top:8px}
      .archive-intelligent-markdown h2{font-size:18px}
      .archive-intelligent-markdown h3{font-size:16px}
      .archive-intelligent-markdown blockquote{background:#f6f9fa}
      .archive-intelligent-download{display:inline-block;font-size:12px;margin-top:14px}
      .archive-intelligent-error{color:#b34343}
      #archive-display-options{display:flex;flex-wrap:wrap;align-items:center;gap:12px 22px;margin:10px 0 2px}
      #archive-display-options > #archive-structured-toggle{margin:0}
      #archive-intelligent-toggle{display:inline-flex;align-items:center;gap:10px;max-width:100%;cursor:pointer;color:#566271;font:500 12px/1.45 system-ui,-apple-system,'Segoe UI',Arial,sans-serif;user-select:none}
      #archive-intelligent-toggle:focus-within{outline:2px solid #408ecb;outline-offset:3px;border-radius:5px}
      #archive-intelligent-toggle input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
      #archive-intelligent-toggle .archive-switch-track{position:relative;display:inline-block;flex:none;width:34px;height:20px;border-radius:99px;background:#aab3c0;transition:background .12s ease}
      #archive-intelligent-toggle .archive-switch-track::after{content:"";position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#fff;box-shadow:0 1px 2px #0002;transition:transform .12s ease}
      #archive-intelligent-toggle input:checked + .archive-switch-track{background:#19876e}
      #archive-intelligent-toggle input:checked + .archive-switch-track::after{transform:translateX(14px)}
      #archive-intelligent-toggle .archive-switch-label{white-space:normal}
      #archive-intelligent-toggle .archive-switch-count{font-size:11px;font-weight:400;color:#838b96}
      @media(prefers-reduced-motion:reduce){#archive-intelligent-toggle .archive-switch-track,#archive-intelligent-toggle .archive-switch-track::after{transition:none}}
      @media print{#archive-display-options{display:none!important}body.archive-intelligent-off .archive-intelligent-text{display:none!important}body.archive-intelligent-off .archive-intelligent-rendered,body.archive-intelligent-off .archive-intelligent-original{display:revert!important}}
    `;
    document.head.appendChild(style);
    const wrapper=create('div');wrapper.id='archive-display-options';
    const old=header.querySelector('#archive-structured-toggle');
    if (old) wrapper.appendChild(old); // preserve original switch/listeners
    const label=create('label');label.id='archive-intelligent-toggle';
    const input=create('input');input.id='archive-show-intelligent-ui';input.type='checkbox';
    input.checked=true;input.setAttribute('role','switch');
    input.setAttribute('aria-label','Показывать отрисованную разметку Intelligent UI');
    const track=create('span','archive-switch-track');track.setAttribute('aria-hidden','true');
    const title=create('span','archive-switch-label','Intelligent UI');
    const count=create('span','archive-switch-count','('+parts.length+')');
    label.append(input,track,title,count);wrapper.appendChild(label);
    const date=header.querySelector('.date');
    if (date?.parentNode===header) date.insertAdjacentElement('afterend',wrapper);
    else header.appendChild(wrapper);
    input.addEventListener('change',()=>{
      setMode(input.checked);input.setAttribute('aria-checked',String(input.checked));
      label.title=input.checked?'Визуализация Intelligent UI':'Читаемая версия Markdown';
    });
    prepareObserver();setMode(true);
    // Existing HTML may visibly contain unexpanded {#each}/{#if} markers.
    // Load ONLY those affected sources at startup, so Intelligent UI ON works
    // immediately, without forcing the user to toggle OFF and back first.
    for (const part of parts) {
      if (part.rendered.some(node=>/\{#(?:each|if)\b/.test(node.textContent||''))) load(part);
    }
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
