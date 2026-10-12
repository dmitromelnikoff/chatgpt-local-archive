/* ChatGPT Local Archive — calendar + statistics extension, v7.3.15.
 * Pure index-page enhancement. No source export, chat, file registry, iframe,
 * recovery UI, DIL, or MathJax modifications. No external dependencies.
 */
(function () {
  'use strict';
  if (window.__archiveCalendarStatsLoaded) return;
  window.__archiveCalendarStatsLoaded = true;
  const sidebar = document.querySelector('.sidebar');
  const main = document.querySelector('.main');
  const searchWrap = document.querySelector('.search-wrap');
  const search = document.getElementById('search');
  if (!sidebar || !main || !searchWrap || !search || typeof CHATS === 'undefined' ||
      typeof renderRows !== 'function' || typeof filtered === 'undefined') return;

  const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
  const formatCount = n => Number(n).toLocaleString('ru-RU');
  const monthDate = chat => {
    const m = String(chat[2] || '').match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s|$)/);
    if (!m) return '';
    const d = Number(m[1]), mo = Number(m[2]), y = Number(m[3]);
    if (d < 1 || d > 31 || mo < 1 || mo > 12 || y < 1970 || y > 2100) return '';
    return String(y) + '-' + String(mo).padStart(2, '0');
  };
  const chatMonths = Array.from(CHATS, monthDate);
  const monthCounts = new Map(), yearCounts = new Map();
  let undated = 0;
  for (const key of chatMonths) {
    if (!key) { undated++; continue; }
    monthCounts.set(key, (monthCounts.get(key) || 0) + 1);
    const y = key.slice(0,4);
    yearCounts.set(y, (yearCounts.get(y) || 0) + 1);
  }
  const years = [...yearCounts.keys()].sort((a,b) => b.localeCompare(a));
  let filter = ''; // ''=all, '2025'=year, '2025-11'=month, 'unknown'=undated
  let calendarOpen = false;
  let statisticsOpen = false;

  const make = (tag, className, content) => {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (content !== undefined) e.textContent = content;
    return e;
  };
  const toolbar = make('div', 'archive-cal-toolbar');
  const dateBtn = make('button', 'archive-cal-action', '📅 Даты · Все');
  dateBtn.type = 'button'; dateBtn.setAttribute('aria-expanded','false');
  dateBtn.setAttribute('aria-controls','archive-calendar-panel');
  const statsBtn = make('button', 'archive-cal-action', '▥ Статистика');
  statsBtn.type = 'button'; statsBtn.setAttribute('aria-pressed','false');
  toolbar.append(dateBtn, statsBtn);
  searchWrap.insertAdjacentElement('afterend', toolbar);

  const calendar = make('section', 'archive-cal-menu');
  calendar.id = 'archive-calendar-panel';
  calendar.hidden = true;
  calendar.setAttribute('aria-label','Выбор года и месяца');
  sidebar.appendChild(calendar);
  sidebar.classList.add('archive-cal-sidebar');

  const overlay = make('section', 'archive-stats-overlay');
  overlay.hidden = true;
  overlay.setAttribute('role', 'region');
  overlay.setAttribute('aria-label', 'Общая статистика архива ChatGPT');
  main.appendChild(overlay);

  function humanFilter() {
    if (!filter) return 'Все даты';
    if (filter === 'unknown') return 'Без даты';
    if (filter.length === 4) return filter + ' год';
    return MONTHS[Number(filter.slice(5,7)) - 1] + ' ' + filter.slice(0,4);
  }

  function syncCalendarPosition() {
    const a = toolbar.getBoundingClientRect();
    const b = sidebar.getBoundingClientRect();
    calendar.style.top = Math.max(0, a.bottom - b.top + 4) + 'px';
  }
  function closeCalendar() {
    calendarOpen = false;
    calendar.hidden = true;
    dateBtn.setAttribute('aria-expanded','false');
  }
  function showCalendar() {
    calendarOpen = true;
    syncCalendarPosition();
    calendar.hidden = false;
    dateBtn.setAttribute('aria-expanded','true');
    calendar.focus({preventScroll:true});
  }
  function setFilter(v) {
    filter = v;
    dateBtn.textContent = '📅 ' + humanFilter();
    drawCalendar();
    applyFilters();
    closeCalendar();
  }
  function drawCalendar() {
    calendar.replaceChildren();
    const head = make('div', 'archive-cal-menu-head');
    head.append(make('strong', '', 'Переписки по датам'));
    const close = make('button', 'archive-cal-close', '×');
    close.type='button'; close.title='Закрыть календарь'; close.addEventListener('click', closeCalendar);
    head.append(close); calendar.append(head);
    const sub = make('p','archive-cal-helper', 'Группировка по последнему изменению диалога в экспорте.');
    calendar.append(sub);
    const all = make('button', 'archive-cal-period' + (!filter ? ' is-active' : ''), 'Все даты');
    all.type='button';
    const allNum = make('span','archive-cal-num',formatCount(CHATS.length));
    all.append(allNum); all.addEventListener('click',()=>setFilter(''));
    calendar.append(all);

    for (const year of years) {
      const group = make('details','archive-cal-year');
      group.open = !!(filter && filter.startsWith(year)) || (filter==='' && year===years[0]);
      const heading = make('summary','archive-cal-year-summary');
      heading.append(make('span','',year));
      heading.append(make('span','archive-cal-num',formatCount(yearCounts.get(year))));
      group.append(heading);
      const body = make('div','archive-cal-months');
      const yearButton = make('button','archive-cal-period archive-cal-year-button' + (filter===year?' is-active':''),'Весь '+year+' год');
      yearButton.type='button';yearButton.append(make('span','archive-cal-num',formatCount(yearCounts.get(year))));
      yearButton.addEventListener('click',()=>setFilter(year));
      body.append(yearButton);
      for (let m=12; m>=1; m--) {
        const key = year+'-'+String(m).padStart(2,'0');
        const n=monthCounts.get(key);
        if (!n) continue;
        const button=make('button','archive-cal-period' + (filter===key?' is-active':''),MONTHS[m-1]);
        button.type='button';button.append(make('span','archive-cal-num',formatCount(n)));
        button.addEventListener('click',()=>setFilter(key));body.append(button);
      }
      group.append(body);calendar.append(group);
    }
    if (undated) {
      const btn=make('button','archive-cal-period'+(filter==='unknown'?' is-active':''),'Без даты');
      btn.type='button';btn.append(make('span','archive-cal-num',formatCount(undated)));
      btn.addEventListener('click',()=>setFilter('unknown'));calendar.append(btn);
    }
  }

  function dateMatches(key) {
    if (!filter) return true;
    if (filter === 'unknown') return !key;
    if (filter.length === 4) return key.startsWith(filter+'-');
    return key===filter;
  }
  function applyFilters() {
    // Mutate the EXISTING global filtered list used by the virtualized sidebar.
    // Do not duplicate its renderer or change the conversation iframe.
    const q=search.value.trim().toLocaleLowerCase();
    const output=[];
    for (let i=0; i<CHATS.length; i++) {
      if (!dateMatches(chatMonths[i])) continue;
      if (q && !String(CHATS[i][0]).toLocaleLowerCase().includes(q)) continue;
      output.push(i);
    }
    filtered=output;
    const c=document.getElementById('count');
    if (c) c.textContent='Найдено: '+formatCount(output.length)+' / '+formatCount(CHATS.length)+
      (filter?' · '+humanFilter():'');
    const lst=document.getElementById('list');
    lst.scrollTop=0;
    renderRows();
    if (!output.length) {
      const r=document.getElementById('rows');
      const s=document.getElementById('spacer');
      if (r) r.replaceChildren(make('div','empty-list','По выбранным условиям диалогов нет'));
      if (s) s.style.height='50px';
    }
  }

  // The legacy archive has already registered input('input', doSearch).
  // Capture phase intentionally runs before that listener and replaces only
  // its LIST FILTERING behavior. No other search behavior changes.
  search.addEventListener('input', ev => {
    ev.stopImmediatePropagation();
    applyFilters();
  }, true);

  dateBtn.addEventListener('click',()=>calendarOpen?closeCalendar():showCalendar());
  document.addEventListener('pointerdown', ev => {
    if (calendarOpen && !calendar.contains(ev.target) && !dateBtn.contains(ev.target)) closeCalendar();
  });
  document.addEventListener('keydown', ev => {
    if (ev.key==='Escape') { closeCalendar(); hideStats(); }
  });
  window.addEventListener('resize',()=>{if(calendarOpen)syncCalendarPosition();});

  const statsHeader = make('div','archive-stats-head');
  const statsTitleWrap=make('div','');
  statsTitleWrap.append(make('h2','','Статистика архива'),
    make('p','','Сводка по локальному экспорту и восстановленным файлам'));
  const back=make('button','archive-stats-back','× Закрыть');
  back.type='button';back.addEventListener('click',hideStats);
  statsHeader.append(statsTitleWrap,back);
  const statsBody=make('div','archive-stats-body');
  overlay.append(statsHeader,statsBody);
  function hideStats() {
    statisticsOpen=false; overlay.hidden=true;statsBtn.setAttribute('aria-pressed','false');
  }
  function showStats() {
    closeCalendar();statisticsOpen=true;overlay.hidden=false;
    statsBtn.setAttribute('aria-pressed','true');
    statsBody.replaceChildren(make('p','archive-stats-loading','Загружаем статистику…'));
    updateStats();
  }
  statsBtn.addEventListener('click',()=>statisticsOpen?hideStats():showStats());
  // Clicking a chat/gallery/files tab should leave the statistics overlay.
  document.getElementById('list').addEventListener('click',hideStats,true);
  const nav=document.querySelector('.gallery-nav');
  if(nav) nav.addEventListener('click',hideStats,true);

  async function fetchText(path) {
    const r=await fetch(path,{cache:'no-store'});
    if(!r.ok) throw new Error(String(r.status));
    return await r.text();
  }
  async function fetchJSON(path) {
    const r=await fetch(path,{cache:'no-store'});
    if(!r.ok) throw new Error(String(r.status));
    return await r.json();
  }
  // Semicolon CSV with BOM, CRLF and quoted multiline fields.
  function parseCSV(text) {
    let rows=[],row=[],cell='',quoted=false;
    const s=text.replace(/^\uFEFF/,'');
    for(let i=0;i<s.length;i++) {
      const ch=s[i];
      if(quoted) {
        if(ch==='"'&&s[i+1]==='"'){cell+='"';i++;}
        else if(ch==='"')quoted=false;
        else cell+=ch;
      } else if(ch==='"')quoted=true;
      else if(ch===';'){row.push(cell);cell='';}
      else if(ch==='\n'){row.push(cell.replace(/\r$/,''));rows.push(row);row=[];cell='';}
      else cell+=ch;
    }
    if(cell!==''||row.length){row.push(cell.replace(/\r$/,''));rows.push(row);}
    return rows;
  }
  function metric(parent,label,value,detail){
    const tile=make('div','archive-stats-tile');
    tile.append(make('span','archive-stats-caption',label),make('strong','archive-stats-big',value));
    if(detail)tile.append(make('span','archive-stats-explainer',detail));
    parent.append(tile);
  }
  function statLine(parent,text){parent.append(make('p','archive-stats-note',text));}

  async function updateStats() {
    // Read original archive reports on demand. A recovered file is determined
    // by the recovery API's live filesystem+registry evaluation, NOT old CSV.
    const results=await Promise.allSettled([
      fetchText('conversations_index.csv'),
      fetchText('gallery.html'),
      fetchJSON('__recovery/api/full-list')
    ]);
    if(!statisticsOpen)return;
    statsBody.replaceChildren();
    const cards=make('div','archive-stats-tiles');
    metric(cards,'Переписок',formatCount(CHATS.length),'Включая чаты с ошибкой конвертации');
    metric(cards,'Период',years.length?years[years.length-1]+'–'+years[0]:'Нет дат',
      formatCount(years.length)+' лет в архиве');

    if(results[0].status==='fulfilled') {
      const records=parseCSV(results[0].value),head=records.shift()||[];
      const idx=head.indexOf('mapping_messages');
      const statusidx=head.indexOf('status');
      if(idx>=0){
        let total=0,valid=0,errors=0;
        for(const row of records){const n=Number(row[idx]);if(Number.isFinite(n)&&n>=0){total+=n;valid++;}
          if(statusidx>=0 && row[statusidx]==='ERROR')errors++;}
        metric(cards,'Узлов mapping',formatCount(total),'Содержит служебные записи; не равно числу видимых сообщений');
        if(errors)metric(cards,'Чатов с ошибкой',formatCount(errors),'Сохранены как страницы ошибки');
      }
    } else {
      metric(cards,'Узлов mapping','—','Отчёт conversations_index.csv недоступен');
    }
    if(results[1].status==='fulfilled') {
      const m=results[1].value.match(/Найдено:\s*(\d[\d\s]*)\s*\./);
      if(m)metric(cards,'Изображений в галерее',formatCount(Number(m[1].replace(/\s/g,''))),
        'Количество при первоначальной сборке галереи');
    }
    if(results[2].status==='fulfilled'){
      const data=results[2].value;
      const x=Array.isArray(data.rows)?data.rows:[];
      const extra=Array.isArray(data.additional)?data.additional:[];
      const available=x.filter(a=>a.found).length;
      const missing=x.length-available;
      const recovered=x.filter(a=>a.recovered).length;
      metric(cards,'Записей о выходных файлах',formatCount(x.length),
        'Упоминания в отчёте; один файл может встречаться несколько раз');
      metric(cards,'Доступно',formatCount(available),'Статус проверен по текущим локальным файлам');
      metric(cards,'Отсутствует',formatCount(missing+extra.filter(a=>!a.found).length),
        'Включая дополнительные записи Library: '+formatCount(extra.length));
      metric(cards,'Восстановлено вручную',formatCount(recovered),'Среди записей основного списка файлов');
    } else {
      metric(cards,'Файлы ChatGPT','—','Запустите архив через локальный сервер восстановления');
    }
    statsBody.append(cards);
    const period=make('section','archive-stats-section');
    period.append(make('h3','','Активность по месяцам'));
    statLine(period,'Дата соответствует последнему изменению чата в экспорте, а не обязательно дате его создания.');
    const counts=[...monthCounts.entries()].sort((a,b)=>b[0].localeCompare(a[0]));
    const max=Math.max(1,...counts.map(x=>x[1]));
    const barWrap=make('div','archive-stats-bars');
    for(const [key,n] of counts){
      const line=make('button','archive-stats-month');line.type='button';
      line.title='Показать чаты за '+humanMonth(key);
      line.append(make('span','archive-stats-month-label',humanMonth(key)));
      const track=make('span','archive-stats-track');
      const fill=make('span','archive-stats-fill');fill.style.width=(n/max*100).toFixed(2)+'%';
      track.append(fill);line.append(track,make('strong','archive-stats-month-n',formatCount(n)));
      line.addEventListener('click',()=>{setFilter(key);hideStats();});
      barWrap.append(line);
    }
    period.append(barWrap);statsBody.append(period);
    const info=make('section','archive-stats-section');
    info.append(make('h3','','Как читать эти числа'));
    statLine(info,'Чаты: количество страниц в этом архиве. «Узлы mapping» включают служебные и промежуточные сообщения, а также могут включать пустые узлы.');
    statLine(info,'Выходные файлы: количество упоминаний из отчёта, а не уникальных документов. Дополнительные отсутствующие записи Library подсчитываются отдельно.');
    statLine(info,'Восстановленные файлы учитываются по актуальному состоянию локальной папки и реестра, поэтому старое «отсутствует» из CSV не должно завышать текущие потери.');
    statsBody.append(info);
  }
  function humanMonth(key){return MONTHS[Number(key.slice(5))-1]+' '+key.slice(0,4);}
  drawCalendar();
  applyFilters();
})();
