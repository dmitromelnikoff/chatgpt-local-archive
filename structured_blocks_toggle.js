/* ChatGPT Local Archive v7.3.6 – global per-chat visibility switch.
 * Controls existing "Структурированная часть сообщения · JSON с переносами"
 * blocks only. DOES NOT modify their data, markup or native <details> state.
 * Off on every chat load, including pages reached from Files ChatGPT.
 * Read-only; no network, storage, iframe/parent access or history changes.
 */
(() => {
  'use strict';
  if (window.__archiveStructureToggleV736) return;
  window.__archiveStructureToggleV736 = true;

  const classHidden = 'archive-structures-hidden';
  const classBlock = 'archive-structure-json-target';
  const classOnly = 'archive-structure-only-message';

  function isTarget(details) {
    if (!details.matches('details.ui-source.structure')) return false;
    const summary = Array.from(details.children).find(child => child.tagName === 'SUMMARY');
    if (!summary) return false;
    const label = (summary.textContent || '').replace(/\s+/g, ' ').trim();
    return label.startsWith('Структурированная часть сообщения') && label.includes('JSON с переносами');
  }

  // No innerHTML mutation or removal. The original <details> stays untouched.
  function hasOtherContent(root, hiddenBlocks) {
    const skip = new Set(hiddenBlocks);
    const ignored = '.archive-copy-actions,script,style,noscript,template';
    const meaningfulEmptyTags = new Set(['IMG', 'PICTURE', 'SVG', 'CANVAS', 'VIDEO', 'AUDIO',
      'IFRAME', 'OBJECT', 'EMBED', 'INPUT', 'TEXTAREA', 'BUTTON', 'SELECT', 'HR']);
    const keepEvenEmpty = '.library-media,.library-file,.generated-output,.dil-box,.dil-grid,.dil-row,.file-entry,.download';
    function scan(node) {
      if (node.nodeType === Node.TEXT_NODE) return Boolean(node.nodeValue.trim());
      if (node.nodeType !== Node.ELEMENT_NODE) return false;
      if (skip.has(node) || node.matches(ignored)) return false;
      if (meaningfulEmptyTags.has(node.tagName) || node.matches(keepEvenEmpty)) return true;
      // Defensive: never accidentally hide a media/form/link-bearing wrapper.
      if (node.tagName === 'A' && node.hasAttribute('href')) return true;
      for (const child of node.childNodes) if (scan(child)) return true;
      return false;
    }
    return scan(root);
  }

  function boot() {
    const header = document.querySelector('body > header');
    if (!header) return;

    const blocks = Array.from(document.querySelectorAll('article > .body details.ui-source.structure')).filter(isTarget);
    if (!blocks.length) return;
    const byArticle = new Map();
    for (const block of blocks) {
      const article = block.closest('article');
      if (!article) continue;
      const role = Array.from(article.children).find(node => node.classList?.contains('role'));
      if (!role || !role.classList.contains('assistant')) continue;
      block.classList.add(classBlock);
      if (!byArticle.has(article)) byArticle.set(article, []);
      byArticle.get(article).push(block);
    }
    if (!byArticle.size) return;

    let fullMessages = 0;
    let totalBlocks = 0;
    for (const [article, related] of byArticle) {
      totalBlocks += related.length;
      const body = Array.from(article.children).find(node => node.classList?.contains('body'));
      if (body && !hasOtherContent(body, related)) {
        article.classList.add(classOnly);
        fullMessages++;
      }
    }

    const style = document.createElement('style');
    style.id = 'archive-structured-switch-styles';
    style.textContent = `
      body.${classHidden} .${classBlock}{display:none!important}
      body.${classHidden} article.${classOnly}{display:none!important}
      #archive-structured-toggle{display:flex;align-items:center;gap:10px;margin-top:10px;width:fit-content;max-width:100%;cursor:pointer;color:#566271;font:500 12px/1.45 system-ui,-apple-system,'Segoe UI',Arial,sans-serif;user-select:none}
      #archive-structured-toggle:focus-within{outline:2px solid #408ecb;outline-offset:3px;border-radius:5px}
      #archive-structured-toggle .archive-switch-track{position:relative;display:inline-block;flex:none;width:34px;height:20px;border-radius:99px;background:#aab3c0;transition:background .12s ease}
      #archive-structured-toggle .archive-switch-track::after{content:"";position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#fff;box-shadow:0 1px 2px #0002;transition:transform .12s ease}
      #archive-structured-toggle input:checked + .archive-switch-track{background:#19876e}
      #archive-structured-toggle input:checked + .archive-switch-track::after{transform:translateX(14px)}
      #archive-structured-toggle input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
      #archive-structured-toggle .archive-switch-label{white-space:normal}
      #archive-structured-toggle .archive-switch-count{font-size:11px;font-weight:400;color:#838b96}
      @media(prefers-reduced-motion:reduce){#archive-structured-toggle .archive-switch-track,#archive-structured-toggle .archive-switch-track::after{transition:none}}
      @media print{#archive-structured-toggle{display:none!important}}
    `;
    document.head.appendChild(style);

    const switchLabel = document.createElement('label');
    switchLabel.id = 'archive-structured-toggle';
    switchLabel.title = 'Показывает или скрывает служебные JSON-блоки во всей переписке. Содержимое блоков не меняется.';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.id = 'archive-show-structured';
    input.setAttribute('role', 'switch');
    input.setAttribute('aria-label', 'Показывать служебные блоки');
    input.setAttribute('aria-checked', 'false');
    input.checked = false;
    const track = document.createElement('span');
    track.className = 'archive-switch-track';
    track.setAttribute('aria-hidden', 'true');
    const text = document.createElement('span');
    text.className = 'archive-switch-label';
    text.textContent = 'Служебные блоки';
    const count = document.createElement('span');
    count.className = 'archive-switch-count';
    count.textContent = '(' + totalBlocks + ')';
    count.title = 'Служебных JSON-блоков: ' + totalBlocks + '. Полностью служебных сообщений: ' + fullMessages;
    switchLabel.append(input, track, text, count);

    // Immediately below the original conversation timestamp; no other chat UI touched.
    const date = header.querySelector('.date');
    if (date && date.parentNode === header) date.insertAdjacentElement('afterend', switchLabel);
    else header.appendChild(switchLabel);

    function apply() {
      document.body.classList.toggle(classHidden, !input.checked);
      input.setAttribute('aria-checked', String(input.checked));
      switchLabel.title = input.checked
        ? 'Служебные блоки показаны. Нажмите, чтобы скрыть их во всём чате.'
        : 'Служебные блоки скрыты. Нажмите, чтобы показать их во всём чате.';
    }
    input.addEventListener('change', apply);
    apply();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
