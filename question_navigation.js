/* ChatGPT Local Archive v7.3.5 – table of contents for USER prompts.
 * Loaded only inside generated chat HTML by the existing loopback server.
 * No storage, network calls, history modifications, or parent-frame access.
 */
(() => {
  'use strict';
  if (window.__archiveQuestionNavigationV735) return;
  window.__archiveQuestionNavigationV735 = true;

  const style = document.createElement('style');
  style.textContent = `
    :root{--archive-questions-width:254px}
    body.archive-questions-enabled{max-width:none!important;width:auto!important;margin:0!important;padding:28px calc(var(--archive-questions-width) + 30px) 70px 28px!important}
    body.archive-questions-enabled > :not(.archive-questions-sidebar):not(.archive-questions-toggle){max-width:980px;margin-left:auto;margin-right:auto}
    #archive-questions-sidebar{box-sizing:border-box;position:fixed;z-index:99;top:0;right:0;bottom:0;width:var(--archive-questions-width);display:flex;flex-direction:column;background:#fbfbfc;border-left:1px solid #e6e8ed;font:13px/1.45 system-ui,-apple-system,'Segoe UI',Arial,sans-serif;color:#535d69;box-shadow:-2px 0 11px rgba(0,0,0,.025)}
    #archive-questions-sidebar *{box-sizing:border-box}
    .archive-questions-heading{flex:none;display:flex;align-items:center;justify-content:space-between;min-height:60px;padding:20px 15px 12px 18px;font-size:11px;letter-spacing:.035em;font-weight:600;color:#6e7885;border-bottom:1px solid #f1f2f4}
    .archive-questions-heading strong{font-weight:650;color:#535d69}
    #archive-questions-list{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#c5cbd3 transparent;padding:9px 8px 25px}
    #archive-questions-list::-webkit-scrollbar{width:6px}
    #archive-questions-list::-webkit-scrollbar-thumb{border-radius:6px;background:#c5cbd3}
    .archive-question-item{display:flex;gap:7px;align-items:flex-start;width:100%;border:0;border-left:3px solid transparent;border-radius:0 7px 7px 0;margin:2px 0;padding:8px 8px 8px 7px;background:transparent;text-align:left;color:#697584;cursor:pointer;font:12.5px/1.5 system-ui,-apple-system,'Segoe UI',Arial,sans-serif;overflow-wrap:anywhere}
    .archive-question-item:hover{background:#f0f1f4;color:#303b47}
    .archive-question-item.active{background:#ebeff5;color:#293644;border-left-color:#2f77dd}
    .archive-question-item:focus-visible{outline:2px solid #377edf;outline-offset:-2px}
    .archive-question-number{flex:0 0 auto;min-width:15px;text-align:right;font-variant-numeric:tabular-nums;color:inherit}
    .archive-question-label{min-width:0;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;line-clamp:3;overflow:hidden;white-space:normal;overflow-wrap:anywhere}
    #archive-questions-toggle,.archive-questions-close{display:none}
    @media(max-width:900px){
      body.archive-questions-enabled{max-width:980px!important;margin:0 auto!important;padding:28px 24px 70px!important}
      body.archive-questions-enabled > :not(.archive-questions-sidebar):not(.archive-questions-toggle){max-width:none}
      #archive-questions-sidebar{width:min(310px,85vw);transform:translateX(102%);transition:transform .18s ease;box-shadow:-10px 0 28px rgba(0,0,0,.15)}
      body.archive-questions-open #archive-questions-sidebar{transform:translateX(0)}
      #archive-questions-toggle{position:fixed;z-index:98;right:12px;top:12px;display:inline-flex;align-items:center;justify-content:center;gap:5px;border:1px solid #cbd4df;border-radius:9px;background:#fff;color:#364858;box-shadow:0 2px 9px rgba(0,0,0,.10);padding:8px 11px;font:600 12px/1.3 system-ui,-apple-system,'Segoe UI',Arial,sans-serif;cursor:pointer}
      body.archive-questions-open #archive-questions-toggle{visibility:hidden}
      .archive-questions-close{display:inline-flex;justify-content:center;align-items:center;width:30px;height:30px;border:0;background:transparent;border-radius:7px;color:#65717d;cursor:pointer;font-size:22px;line-height:1}
      .archive-questions-close:hover{background:#e7ebf0}
    }
    @media(max-width:640px){body.archive-questions-enabled{padding:14px 14px 65px!important}#archive-questions-toggle{right:7px;top:7px}}
    @media(prefers-reduced-motion:reduce){#archive-questions-sidebar{transition:none}}
    @media print{#archive-questions-sidebar,#archive-questions-toggle{display:none!important}body.archive-questions-enabled{padding:12px!important;max-width:none!important}}
  `;
  document.head.appendChild(style);

  function userArticles() {
    return Array.from(document.querySelectorAll('article')).filter(article => {
      // Work with original chat markup: a direct role cell and body cell.
      const role = Array.from(article.children).find(e => e.classList?.contains('role'));
      const body = Array.from(article.children).find(e => e.classList?.contains('body'));
      return Boolean(role && role.classList.contains('user') && body);
    });
  }

  function promptText(article) {
    const body = Array.from(article.children).find(e => e.classList?.contains('body'));
    if (!body) return 'Запрос пользователя';
    // Read text nodes without cloning image-heavy HTML or loading assets again.
    const ignore = '.archive-copy-actions,.generated-output,.ui-source,.link-confidence,.candidate-files,script,style,button,svg';
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return node.parentElement && !node.parentElement.closest(ignore)
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    const collected = [];
    let length = 0;
    while (walker.nextNode() && length < 1400) {
      const value = walker.currentNode.nodeValue || '';
      collected.push(value);
      length += value.length;
    }
    const normalized = collected.join(' ').replace(/[\s\u00a0]+/g, ' ').trim();
    if (normalized) return normalized.slice(0, 1200);
    if (body.querySelector('img,picture,svg,figure.attachment')) return 'Прикреплено изображение';
    if (body.querySelector('a[download],.download,input[type="file"]')) return 'Прикреплён файл';
    return 'Запрос пользователя';
  }

  function boot() {
    const questions = userArticles();
    if (!questions.length) return;
    const sidebar = document.createElement('aside');
    sidebar.id = 'archive-questions-sidebar';
    sidebar.setAttribute('aria-label','Оглавление запросов пользователя');
    const heading = document.createElement('div');
    heading.className = 'archive-questions-heading';
    const headingText = document.createElement('span');
    headingText.innerHTML = 'QUESTIONS: <strong></strong>';
    headingText.querySelector('strong').textContent = String(questions.length);
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'archive-questions-close';
    close.setAttribute('aria-label', 'Закрыть оглавление');
    close.textContent = '×';
    heading.append(headingText,close);
    const nav = document.createElement('nav');
    nav.id = 'archive-questions-list';
    nav.setAttribute('aria-label','Список вопросов');
    sidebar.append(heading,nav);

    const toggle = document.createElement('button');
    toggle.id='archive-questions-toggle';
    toggle.type='button';
    toggle.textContent = '☷ Вопросы (' + questions.length + ')';
    toggle.setAttribute('aria-label','Показать оглавление запросов');
    toggle.setAttribute('aria-expanded','false');
    toggle.setAttribute('aria-controls','archive-questions-sidebar');

    const elements=[];
    let activeIndex=-1;
    let lastAutoScroll=0;
    function closeMenu() {
      document.body.classList.remove('archive-questions-open');
      toggle.setAttribute('aria-expanded','false');
    }
    toggle.addEventListener('click',()=>{
      const open=document.body.classList.toggle('archive-questions-open');
      toggle.setAttribute('aria-expanded',String(open));
    });
    close.addEventListener('click',closeMenu);
    document.addEventListener('keydown',event=>{
      if (event.key === 'Escape') closeMenu();
    });

    const fragment=document.createDocumentFragment();
    questions.forEach((article,index)=>{
      if (!article.id) article.id='archive-question-'+(index+1);
      const button=document.createElement('button');
      button.type='button';
      button.className='archive-question-item';
      const caption=promptText(article);
      button.title=(index+1)+'. '+caption;
      const number=document.createElement('span');
      number.className='archive-question-number';
      number.textContent=(index+1)+'.';
      const label=document.createElement('span');
      label.className='archive-question-label';
      label.textContent=caption;
      button.append(number,label);
      button.addEventListener('click',()=>{
        // Scroll only the chat inside its own iframe; never scroll the parent.
        article.scrollIntoView({block:'start',behavior:'auto'});
        setActive(index,true);
        lastAutoScroll=performance.now();
        closeMenu();
      });
      elements.push(button);
      fragment.appendChild(button);
    });
    nav.appendChild(fragment);
    document.body.append(sidebar,toggle);
    document.body.classList.add('archive-questions-enabled');

    function setActive(index,forceNavScroll=false) {
      index=Math.max(0,Math.min(index,questions.length-1));
      if (index === activeIndex && !forceNavScroll) return;
      if (activeIndex >= 0) {
        elements[activeIndex].classList.remove('active');
        elements[activeIndex].removeAttribute('aria-current');
      }
      activeIndex=index;
      elements[index].classList.add('active');
      elements[index].setAttribute('aria-current','location');
      // Scroll the independent TOC only when necessary: do not interfere with
      // a user who is browsing the prompt list manually.
      const item=elements[index];
      const itemBox=item.getBoundingClientRect();
      const listBox=nav.getBoundingClientRect();
      // Adjust only the sidebar scroll container, never the chat or iframe.
      if (itemBox.top < listBox.top + 10) {
        nav.scrollTop += itemBox.top - listBox.top - 14;
      } else if (itemBox.bottom > listBox.bottom - 10) {
        nav.scrollTop += itemBox.bottom - listBox.bottom + 14;
      } else if (forceNavScroll && itemBox.height > nav.clientHeight) {
        nav.scrollTop += itemBox.top - listBox.top;
      }
    }

    function indexAtScroll() {
      // Binary search through DOM-ordered USER messages, not assistant replies;
      // active question remains selected throughout its answer.
      let lo=0,hi=questions.length-1,answer=0;
      const threshold=90;
      while (lo<=hi) {
        const mid=(lo+hi)>>1;
        if (questions[mid].getBoundingClientRect().top <= threshold) {
          answer=mid;
          lo=mid+1;
        } else hi=mid-1;
      }
      return answer;
    }
    let queued=false;
    const update=()=>{
      if (queued) return;
      queued=true;
      requestAnimationFrame(()=>{
        queued=false;
        // Clicking an item already selected it synchronously; allow layout
        // to settle before following scroll events.
        if (performance.now()-lastAutoScroll < 90) return;
        setActive(indexAtScroll());
      });
    };
    window.addEventListener('scroll',update,{passive:true});
    window.addEventListener('resize',update,{passive:true});
    // The viewer can open #message-N directly from the Files list.
    window.addEventListener('hashchange',update,{passive:true});
    requestAnimationFrame(()=>setActive(indexAtScroll(),true));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
