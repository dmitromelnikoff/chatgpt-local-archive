/* v7.3.3: additive controls for the ORIGINAL full Files ChatGPT list.
 * Does not delete, truncate, reorder, or rebuild existing <section> entries.
 * Injected only by our token-protected loopback server.
 */
(() => {
  'use strict';
  const list = document.getElementById('items');
  if (!list) return;
  const rowsDOM = Array.from(list.children).filter(node => node.tagName === 'SECTION');
  const apiRoot = new URL('__recovery/api/', document.baseURI);
  const stats = document.createElement('div');
  stats.id = 'file-recovery-stats';
  stats.textContent = 'Сверка полного списка с отчётом…';
  const toolbar = document.createElement('div');
  toolbar.id = 'file-recovery-toolbar';
  const search = document.createElement('input');
  search.type = 'search';
  search.placeholder = 'Найти файл, чат или ссылку — весь список';
  search.setAttribute('aria-label', 'Поиск по полному списку файлов');
  const statusSelect = document.createElement('select');
  for (const [value, label] of [['all','Все файлы'],['missing','Только отсутствующие'],['found','Только найденные']]) {
    const option = document.createElement('option');
    option.value = value; option.textContent = label;
    statusSelect.append(option);
  }
  statusSelect.setAttribute('aria-label', 'Фильтр по наличию файла');
  const update = document.createElement('button');
  update.type = 'button'; update.textContent = '↻ Обновить статусы';
  update.addEventListener('click', () => load().catch(showError));
  toolbar.append(search, statusSelect, update);
  list.before(stats, toolbar);
  const extra = document.createElement('details');
  extra.id = 'file-recovery-extra';
  list.after(extra);
  let rows = [];
  let goodRows = 0;
  let invalid = 0;
  let promptBox;
  let promptFile;
  let active = null;

  function showError(err) {
    stats.textContent = 'Не удалось получить статусы: ' + String(err && err.message || err);
    stats.classList.add('recover-error');
  }
  function text(tag, className, value) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (value !== undefined) e.textContent = value;
    return e;
  }
  function makeDownload(row) {
    const anchor = text('a', 'recovery-local-link', '↓ Скачать восстановленный файл');
    // The server guarantees these local paths are inside assets/. Encode each segment.
    anchor.href = 'assets/' + row.local.split('/').map(encodeURIComponent).join('/');
    anchor.download = '';
    return anchor;
  }
  function setupUpload(section, item) {
    const bar = text('div', 'recovery-upload-bar');
    const b = text('button', 'recovery-file-button', '⬆ Восстановить файл');
    b.type = 'button';
    if (!item.key) {
      b.disabled = true;
      b.title = 'Отсутствует однозначная запись файла для безопасного сопоставления';
    } else b.addEventListener('click', () => selectFile(item, section, b));
    bar.append(b);
    if (item.size) bar.append(text('small','recover-size','Ожидаемый размер: '+item.size+' байт'));
    section.append(bar);
  }
  function markRow(section, item) {
    const badge = section.querySelector(':scope > b');
    section.classList.remove('good','bad');
    section.classList.add(item.found ? 'good':'bad');
    if (badge) badge.textContent = item.found ? (item.recovered?'✓ Восстановлен':'✓ Найден') : '⚠ Отсутствует';
    const oldBar = section.querySelector(':scope > .recovery-upload-bar');
    if (oldBar) oldBar.remove();
    const oldLocal = section.querySelector(':scope > a.recovery-local-link');
    if (oldLocal) oldLocal.remove();
    if (item.found) {
      // An old static page may still contain the missing-file source reference.
      const oldMissing = section.querySelector(':scope > small');
      if (oldMissing) oldMissing.hidden = true;
      if (!section.querySelector(':scope > a[download]') && item.local) {
        section.append(makeDownload(item));
      }
    } else {
      const oldMissing = section.querySelector(':scope > small');
      if (oldMissing) oldMissing.hidden = false;
      setupUpload(section, item);
    }
  }
  function validatedRow(section, item) {
    const a = section.querySelector(':scope > a[href]');
    const code = section.querySelector(':scope > div > code');
    if (!a || !code) return false;
    return a.getAttribute('href') === item.href && code.textContent === item.name;
  }
  function applyFilter() {
    const needle = search.value.trim().toLocaleLowerCase();
    const selected = statusSelect.value;
    let displayed = 0;
    rowsDOM.forEach((node,i)=>{
      const info = rows[i];
      const statusOK = !info || selected==='all' || (selected==='found' ? info.found : !info.found);
      const textOK = !needle || node.textContent.toLocaleLowerCase().includes(needle) ||
        (info && info.ref.toLocaleLowerCase().includes(needle));
      const visible = Boolean(statusOK && textOK);
      node.hidden = !visible;
      if (visible) displayed++;
    });
    const number = document.getElementById('recover-visible-counter');
    if (number) number.textContent = ' · показано: ' + displayed;
  }
  function updateOriginalHeader(data) {
    // The original explanatory paragraph and CSV link are intentionally preserved.
    const heading = document.querySelector('h1');
    const paragraph = heading && heading.nextElementSibling;
    if (paragraph && paragraph.tagName==='P' && paragraph.firstChild && paragraph.firstChild.nodeType===Node.TEXT_NODE) {
      paragraph.firstChild.textContent = paragraph.firstChild.textContent.replace(
        /Найдено:\s*\d+\s*·\s*Отсутствуют:\s*\d+/, 'Найдено: '+data.found+' · Отсутствуют: '+data.missing);
    }
  }
  function makeExtras(items) {
    extra.replaceChildren();
    if (!items.length) return;
    extra.append(text('summary','', 'Дополнительные отсутствующие записи Library вне исходного списка: ' + items.length));
    const container = text('div','recovery-extra-items');
    for (const item of items) {
      const card = text('section','bad recovery-extra-entry');
      card.append(text('b','', '⚠ Отсутствует'));
      card.append(text('div','',item.name));
      const details = [item.chat, item.file_id, item.expected_size ? 'Ожидаемый размер: '+item.expected_size+' байт' : ''].filter(Boolean).join(' · ');
      card.append(text('small','',details));
      if (item.href) {
        const a = text('a', '', 'Открыть чат');
        a.href = item.href;
        a.target = '_blank';
        a.rel = 'noopener';
        const linkRow = text('div', '');
        linkRow.append(a);
        card.append(linkRow);
      }
      setupUpload(card,{key:item.key,name:item.name,size:item.expected_size,href:item.href});
      container.append(card);
    }
    extra.append(container);
  }
  async function load() {
    update.disabled = true;
    try {
      const res = await fetch(new URL('full-list', apiRoot), {cache:'no-store'});
      if (!res.ok) throw new Error('HTTP '+res.status);
      const data = await res.json();
      if (data.rows.length !== rowsDOM.length) {
        throw new Error('Число строк HTML ('+rowsDOM.length+') не совпадает с CSV ('+data.rows.length+'). Исходный список сохранён; загрузка отключена, чтобы не перепутать файлы.');
      }
      rows = data.rows;
      invalid = 0; goodRows = 0;
      rowsDOM.forEach((section,i) => {
        if (!validatedRow(section, rows[i])) {
          invalid++;
          const bar = section.querySelector(':scope > .recovery-upload-bar');
          if (bar) bar.remove();
          return;
        }
        goodRows++;
        markRow(section,rows[i]);
      });
      makeExtras(data.additional);
      updateOriginalHeader(data);
      stats.classList.remove('recover-error');
      stats.replaceChildren(document.createTextNode(
        'Полный исходный список: '+data.total+' · найдено: '+data.found+' · отсутствуют: '+data.missing+
        ' · восстановлено вручную: '+data.recovered+' · проверено строк: '+goodRows));
      const num = text('span','', ''); num.id = 'recover-visible-counter'; stats.append(num);
      if (invalid) stats.append(text('span','recover-error',' · ВНИМАНИЕ: '+invalid+' строк не совпали с CSV; на них кнопки отключены'));
      applyFilter();
    } finally { update.disabled = false; }
  }
  function selectFile(item, section, button) {
    if (active) return;
    if (!promptFile) {
      promptFile = document.createElement('input');
      promptFile.type = 'file'; promptFile.hidden = true; promptFile.setAttribute('aria-label','Выберите исходный файл для восстановления');
      document.body.append(promptFile);
    }
    active = {item,section,button};
    promptFile.value = '';
    promptFile.onchange = () => {
      const chosen = promptFile.files && promptFile.files[0];
      if (!chosen) {active=null;return;}
      if (!confirm('Восстановить «'+item.name+'» из файла «'+chosen.name+'» ('+chosen.size+' байт)?')) {active=null;return;}
      upload(item, section, button, chosen);
    };
    promptFile.click();
  }
  function upload(item, section, button, file) {
    button.disabled = true;
    const progress = document.createElement('progress'); progress.max=100;progress.value=0;
    const message = text('small','recovery-upload-message',' Загрузка локального файла…');
    const bar = button.closest('.recovery-upload-bar');
    bar.append(progress,message);
    const xhr = new XMLHttpRequest();
    xhr.open('POST',new URL('upload/'+encodeURIComponent(item.key),apiRoot));
    xhr.setRequestHeader('Content-Type','application/octet-stream');
    xhr.setRequestHeader('X-Original-Filename',encodeURIComponent(file.name));
    xhr.upload.onprogress = ev => {if(ev.lengthComputable) progress.value=Math.round(100*ev.loaded/ev.total);};
    xhr.onload = async () => {
      active=null;
      try {
        const result=JSON.parse(xhr.responseText);
        if(xhr.status!==200) throw new Error(result.error||'HTTP '+xhr.status);
        message.textContent=' ✓ Восстановлено, обновляем статусы…';
        await load();
      } catch(err) {
        button.disabled=false;message.textContent='Ошибка: '+err.message;
      }
    };
    xhr.onerror = () => {active=null;button.disabled=false;message.textContent='Ошибка локального соединения';};
    xhr.send(file);
  }
  search.addEventListener('input',applyFilter);
  statusSelect.addEventListener('change',applyFilter);
  load().catch(showError);
})();
