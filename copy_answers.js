/* ChatGPT Local Archive – copy assistant answer v7.3.4
 * Runs inside a sandboxed chat iframe. Only reads the DOM of each answer;
 * does not modify the archive on disk and sends nothing over the network.
 */
(() => {
  'use strict';
  if (window.__archiveAnswerCopyV734) return;
  window.__archiveAnswerCopyV734 = true;

  const css = `
    .archive-copy-actions{display:flex;align-items:center;gap:9px;margin:12px 0 0;padding:6px 0 0;border-top:1px solid #f0f1f3;grid-column:2}
    .archive-copy-btn{display:inline-flex;gap:6px;align-items:center;justify-content:center;border:1px solid transparent;border-radius:7px;background:transparent;color:#63717c;cursor:pointer;font:500 12px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;padding:4px 7px}
    .archive-copy-btn:hover,.archive-copy-btn:focus-visible{color:#0b7865;background:#edf7f3;border-color:#d7ebe4}
    .archive-copy-btn:focus-visible{outline:2px solid #16826b;outline-offset:2px}
    .archive-copy-btn svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
    .archive-copy-btn[disabled]{cursor:wait;opacity:.6}
    .archive-copy-status{font:12px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;color:#28745b}
    .archive-copy-status.error{color:#a33b36}
    @media(max-width:640px){.archive-copy-actions{grid-column:1}}
  `;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const IGNORE = '.archive-copy-actions,.link-confidence,.ui-source,.copy-code-button,[data-copy-ui]';
  const BLOCK_TAGS = new Set(['P','DIV','SECTION','ARTICLE','HEADER','FOOTER','H1','H2','H3','H4','H5','H6','UL','OL','LI','PRE','BLOCKQUOTE','TABLE','FIGURE','HR','DETAILS','FIGCAPTION','SUMMARY']);
  const clean = value => (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n').trim();
  const compact = value => clean(value).replace(/\s*\n\s*/g, ' ');
  const attrLink = (node, field) => (node.getAttribute(field) || '').trim();
  const isSkipped = node => node.nodeType === 1 && node.matches(IGNORE);
  const inlineChildren = node => Array.from(node.childNodes).map(child => inline(child)).join('');
  const escapeMarkdownUrl = url => url.replace(/</g, '%3C').replace(/>/g, '%3E').replace(/\s/g, '%20');
  const escapeLabel = label => label.replace(/\]/g, '\\]');
  const strongestTicks = text => Math.max(0, ...(text.match(/`+/g) || []).map(x => x.length)) + 1;

  function mathSource(node) {
    try {
      const math = window.MathJax && window.MathJax.startup && window.MathJax.startup.document && window.MathJax.startup.document.math;
      if (math && typeof math[Symbol.iterator] === 'function') {
        for (const item of math) {
          if (item.typesetRoot && (item.typesetRoot === node || node.contains(item.typesetRoot))) {
            const source = item.math;
            if (typeof source === 'string' && source) return item.display ? `$$\n${source}\n$$` : `\\(${source}\\)`;
          }
        }
      }
    } catch (_) {}
    return null;
  }

  function inline(node) {
    if (node.nodeType === 3) return node.nodeValue.replace(/\s+/g, ' ');
    if (node.nodeType !== 1 || isSkipped(node)) return '';
    const tag = node.tagName;
    if (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE'].includes(tag)) return '';
    if (tag === 'BR') return '\n';
    if (tag === 'IMG') {
      const src = attrLink(node,'src');
      const alt = attrLink(node,'alt') || attrLink(node,'title') || 'Изображение';
      return src ? `![${escapeLabel(alt)}](${escapeMarkdownUrl(src)})` : `[Изображение: ${alt}]`;
    }
    if (tag === 'SVG') {
      const title = node.querySelector('title,desc')?.textContent?.trim() ||
         Array.from(node.querySelectorAll('text')).map(e => e.textContent?.trim()).filter(Boolean).join(' · ');
      return title ? `[SVG: ${title}]` : '[SVG-графика]';
    }
    if (tag === 'MJX-CONTAINER') return mathSource(node) || '[Формула]';
    if (tag === 'CODE' && node.closest('pre')) return node.textContent;
    const inner = inlineChildren(node);
    if (tag === 'CODE') {
      const ticks = '`'.repeat(strongestTicks(inner));
      return `${ticks}${inner.startsWith('`') || inner.endsWith('`') ? ' ' : ''}${inner}${inner.startsWith('`') || inner.endsWith('`') ? ' ' : ''}${ticks}`;
    }
    if (tag === 'STRONG' || tag === 'B') return compact(inner) ? `**${compact(inner)}**` : '';
    if (tag === 'EM' || tag === 'I') return compact(inner) ? `*${compact(inner)}*` : '';
    if (tag === 'DEL' || tag === 'S' || tag === 'STRIKE') return compact(inner) ? `~~${compact(inner)}~~` : '';
    if (tag === 'A') {
      const title = compact(inner) || compact(node.textContent) || 'Ссылка';
      const href = attrLink(node, 'href');
      return href && !href.toLowerCase().startsWith('javascript:') ? `[${escapeLabel(title)}](${escapeMarkdownUrl(href)})` : title;
    }
    if (tag === 'SUP') return `^${compact(inner)}`;
    if (tag === 'SUB') return `_${compact(inner)}`;
    if (node.matches('.math,.math-inline,.math-display')) {
      const mjx = node.querySelector('mjx-container');
      if (mjx) return mathSource(mjx) || compact(inner);
      const text = compact(inner);
      return text;
    }
    return inner;
  }

  function blocks(children) {
    const result = [];
    let inlineParts = [];
    const flush = () => {
      const s = compact(inlineParts.join(''));
      if (s) result.push(s);
      inlineParts = [];
    };
    for (const node of children) {
      if (node.nodeType === 1 && isSkipped(node)) continue;
      if (node.nodeType === 1 && BLOCK_TAGS.has(node.tagName)) {
        flush();
        const rendered = block(node);
        if (rendered) result.push(rendered);
      } else {
        inlineParts.push(inline(node));
      }
    }
    flush();
    return result.join('\n\n');
  }

  function list(node, indent = 0) {
    const isOrdered = node.tagName === 'OL';
    let start = Number(node.getAttribute('start') || 1);
    const lines = [];
    Array.from(node.children).filter(el=>el.tagName === 'LI').forEach((item,index) => {
      const marker = isOrdered ? `${start+index}. ` : '- ';
      const sublists = Array.from(item.children).filter(el=>el.tagName === 'UL' || el.tagName === 'OL');
      const rest = Array.from(item.childNodes).filter(ch=>!sublists.includes(ch));
      const content = blocks(rest).replace(/\n\n/g,'\n');
      const prefix = ' '.repeat(indent) + marker;
      lines.push(prefix + (content || '').replace(/\n/g,'\n'+' '.repeat(indent+marker.length)));
      sublists.forEach(nested=>lines.push(list(nested, indent+2)));
    });
    return lines.filter(Boolean).join('\n');
  }

  function table(node) {
    const rows = Array.from(node.querySelectorAll('tr')).map(tr=>Array.from(tr.children)
      .filter(td=>td.tagName==='TH'||td.tagName==='TD')
      .map(td=>compact(inlineChildren(td)).replace(/\|/g,'\\|').replace(/\n/g,'<br>')));
    if (!rows.length) return '';
    const width = Math.max(...rows.map(row=>row.length));
    if (!width) return '';
    const normalize = arr => Array.from({length:width},(_,i)=>arr[i]||'');
    const toLine = arr => '| '+normalize(arr).join(' | ')+' |';
    const res = [toLine(rows[0]),toLine(Array(width).fill('---'))];
    for (const row of rows.slice(1)) res.push(toLine(row));
    return res.join('\n');
  }

  function block(node) {
    if (node.nodeType === 3) return compact(node.nodeValue);
    if (node.nodeType !== 1 || isSkipped(node)) return '';
    const tag = node.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEMPLATE') return '';
    if (/^H[1-6]$/.test(tag)) return '#'.repeat(+tag[1])+' '+compact(inlineChildren(node));
    if (tag === 'P') return compact(inlineChildren(node));
    if (tag === 'PRE') {
      const code = node.querySelector('code') || node;
      const language = (code.className || '').match(/(?:^|\s)(?:language|lang)-([\w+#-]+)/)?.[1] || '';
      const content = code.textContent.replace(/^\n+|\n+$/g,'');
      const fence = '`'.repeat(Math.max(3,strongestTicks(content)));
      return fence+language+'\n'+content+'\n'+fence;
    }
    if (tag === 'UL' || tag === 'OL') return list(node);
    if (tag === 'BLOCKQUOTE') return blocks(node.childNodes).split('\n').map(line => line ? '> '+line : '>').join('\n');
    if (tag === 'TABLE') return table(node);
    if (tag === 'HR') return '---';
    if (tag === 'FIGURE') return blocks(node.childNodes);
    if (tag === 'DETAILS') {
      const summary = node.querySelector(':scope > summary');
      const other = Array.from(node.childNodes).filter(e=>e!==summary);
      return blocks([...(summary ? [summary] : []),...other]);
    }
    if (tag === 'SUMMARY' || tag === 'FIGCAPTION') return compact(inlineChildren(node));
    if (tag === 'MJX-CONTAINER') return mathSource(node) || '[Формула]';
    // DIL and other renderer wrappers: preserve their visible children.
    return blocks(node.childNodes);
  }

  function prepareMarkdown(body) {
    const markdown = blocks(body.childNodes)
      .replace(/\n{3,}/g, '\n\n').trim();
    return markdown || clean(body.innerText || body.textContent);
  }

  function legacyCopy(value) {
    const input = document.createElement('textarea');
    input.value = value;
    input.setAttribute('readonly','');
    input.style.cssText = 'position:fixed;top:0;left:-10000px;width:1px;height:1px;opacity:0';
    document.body.appendChild(input);
    input.focus({preventScroll:true});
    input.select();
    let success = false;
    try { success = !!document.execCommand('copy'); }
    finally { input.remove(); }
    return success;
  }

  async function writeCopy(markdown) {
    // In the archive iframe (sandbox without allow-same-origin), the modern
    // Clipboard API is often not available. The legacy selection copy works
    // with a direct user click in Chromium/Edge; try it synchronously first.
    if (legacyCopy(markdown)) return true;
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(markdown); return true; }
      catch (_) { /* Browser or permissions disallow clipboard access. */ }
    }
    return false;
  }

  const icon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"></rect><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"></path></svg>';
  function enhance(article) {
    if (article.dataset.archiveCopyReady === '1') return;
    const role = Array.from(article.children).find(ch=>ch.classList?.contains('role'));
    const body = Array.from(article.children).find(ch=>ch.classList?.contains('body'));
    if (!role || !role.classList.contains('assistant') || !body) return;
    article.dataset.archiveCopyReady = '1';
    const actions = document.createElement('div');
    actions.className = 'archive-copy-actions';
    actions.setAttribute('data-copy-ui','');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'archive-copy-btn';
    button.title = 'Скопировать текст ответа с форматированием Markdown';
    button.setAttribute('aria-label','Скопировать ответ');
    button.innerHTML = icon+'<span>Скопировать ответ</span>';
    const status = document.createElement('span');
    status.className = 'archive-copy-status';
    status.setAttribute('role','status');
    status.setAttribute('aria-live','polite');
    actions.append(button,status);
    body.appendChild(actions);
    let timer;
    button.addEventListener('click', async () => {
      const markdown = prepareMarkdown(body);
      if (!markdown) { status.textContent = 'Пустой ответ'; return; }
      button.disabled = true;
      status.textContent = '';
      let success = false;
      try { success = await writeCopy(markdown); } catch(_) {}
      button.disabled = false;
      clearTimeout(timer);
      status.textContent = success ? '✓ Скопировано' : 'Не удалось скопировать: выделите текст вручную';
      status.classList.toggle('error',!success);
      if (success) {
        timer=setTimeout(()=>{status.textContent='';status.classList.remove('error')},2200);
      }
    });
  }
  function init() {
    document.querySelectorAll('article').forEach(enhance);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
  // Late recovery cards need buttons too, but don't run a full rescanning
  // observer while MathJax changes its own SVG/DOM.
})();
