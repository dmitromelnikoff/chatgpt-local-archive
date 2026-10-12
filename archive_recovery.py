#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local-only recovery of generated ChatGPT files into an existing HTML archive.

No network, third-party packages, or bulk reconversion.  The capability token
and HTTP access controls are supplied by serve_archive.py.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

ALLOWED_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.avif', '.heic',
                '.pdf', '.md', '.txt', '.csv', '.json', '.jsonl', '.zip', '.docx',
                '.xlsx', '.pptx', '.html', '.htm', '.svg', '.xml', '.py', '.ipynb',
                '.rtf', '.odt', '.ods', '.odp', '.epub', '.mp3', '.mp4', '.wav',
                '.ogg', '.webm', '.mov', '.m4a', '.yaml', '.yml', '.log', '.js',
                '.css', '.sql', '.tsv', '.toml', '.ini', '.sh', '.bat', '.cmd', '.ps1'}
# Dangerous scripts may be archived but NEVER rendered as executable browser files.
DANGEROUS_BROWSER = {'.svg', '.html', '.htm', '.xml', '.js'}
MAX_BYTES = 1024 * 1024 * 1024
FILE_ID_RE = re.compile(r'^file[-_][a-zA-Z0-9_-]{6,}$')
INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')


def safe_name(s):
    s = unquote(html.unescape(str(s or '')).replace('\\', '/').split('/')[-1])
    s = INVALID_WIN.sub('_', s).strip(' .')
    if not s or s in {'.', '..'}:
        s = 'file.bin'
    stem, ext = os.path.splitext(s)
    stem = stem[: min(96, max(1, 119-len(ext)))] or 'file'
    if stem.upper() in {'CON','PRN','AUX','NUL','COM1','LPT1'}:
        stem = '_' + stem
    return stem + ext[:20]


def norm_name(name):
    if not name: return ''
    s = html.unescape(str(name)).strip().strip('"\'')
    # Strip markup from raw sandbox links, but never delete balanced parentheses.
    s = re.sub(r'(?:\*\*|__|~~)+$', '', s)
    while s.endswith(')') and s.count(')') > s.count('('): s = s[:-1]
    s = unquote(s.replace('\\', '/').split('?')[0].split('#')[0].rsplit('/', 1)[-1])
    return s.casefold()


def read_csv(path):
    if not path.is_file(): return [], []
    with path.open('r', newline='', encoding='utf-8-sig') as f:
        dialect = ';' if ';' in f.readline() else ','
        f.seek(0)
        r = csv.DictReader(f, delimiter=dialect)
        return list(r), list(r.fieldnames or [])


def write_csv_atomic(path, rows, columns):
    if not columns: return
    target = path.with_name(path.name + '.tmp')
    with target.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, delimiter=';', extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    os.replace(target, path)


def ensure_file_inside(root, relative, *, must_exist=False):
    p = (root / relative).resolve()
    try: p.relative_to(root.resolve())
    except ValueError: raise ValueError('Unsafe path outside archive')
    if must_exist and not p.is_file(): raise FileNotFoundError(str(p))
    return p


def existing_asset(assets, value):
    if not value:return False
    try:
        return ensure_file_inside(assets, value, must_exist=True).is_file()
    except (ValueError, OSError):
        return False


def hash_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def file_magic(path):
    with path.open('rb') as f: b = f.read(32)
    if b.startswith(b'\x89PNG\r\n\x1a\n'):return '.png'
    if b.startswith(b'\xff\xd8\xff'):return '.jpg'
    if b.startswith((b'GIF87a', b'GIF89a')):return '.gif'
    if b.startswith(b'RIFF') and b[8:12] == b'WEBP':return '.webp'
    if b.startswith(b'%PDF-'):return '.pdf'
    if b.startswith(b'PK\x03\x04'):return '.zip'
    if b.startswith(b'BM'):return '.bmp'
    return ''


def key_for(ref, href, lib_id=''):
    if lib_id and FILE_ID_RE.fullmatch(lib_id):
        return 'id_' + hashlib.sha256(lib_id.encode()).hexdigest()[:28]
    return 'ref_' + hashlib.sha256((href+'\n'+ref).encode()).hexdigest()[:28]


class RecoveryManager:
    def __init__(self, archive):
        self.archive = Path(archive).resolve()
        self.assets = self.archive / 'assets'
        self.root = self.archive.parent
        self.user_files = self.root / 'ChatGPT_Generated_Files' / 'Recovered_From_Browser'
        self.regpath = self.archive / 'recovered_files.json'
        self.lock = threading.RLock()

    def registry(self):
        if not self.regpath.is_file():return {}
        try:
            obj = json.loads(self.regpath.read_text('utf-8-sig'))
            return obj if isinstance(obj, dict) else {}
        except (ValueError, OSError):return {}

    def _save_registry(self, data):
        self.regpath.parent.mkdir(parents=True, exist_ok=True)
        temp = self.regpath.with_name(self.regpath.name+'.tmp')
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, self.regpath)

    def _records(self):
        """Aggregate missing generated refs + Library files by exact ID, not basename alone."""
        report, _ = read_csv(self.archive / 'generated_files_report.csv')
        bindings, _ = read_csv(self.archive / 'message_file_bindings.csv')
        library, _ = read_csv(self.archive / 'library_integrity_report.csv')
        convs, _ = read_csv(self.archive / 'conversations_index.csv')
        reg = self.registry()
        id_to_lib = {}
        for x in library:
            fid = x.get('ID файла Library','').strip()
            if FILE_ID_RE.fullmatch(fid):id_to_lib[fid] = x
        href_by_chat = {r.get('conversation_id',''):r.get('html','') for r in convs}
        chat_id_by_href = {r.get('html',''):r.get('conversation_id','') for r in convs}
        bind_by_id = {}
        for row in bindings:
            fid = row.get('file_id','')
            if FILE_ID_RE.fullmatch(fid):bind_by_id.setdefault(fid, []).append(row)
        lib_by_chat_name = {}
        for fid,entry in id_to_lib.items():
            chat = entry.get('ID чата','')
            name = norm_name(entry.get('Название',''))
            if chat and name:
                lib_by_chat_name.setdefault((chat, name), []).append(fid)

        result = {}
        def insert(ref, href, name, chat, fid='', filesize=None, local_in=''):
            if not ref and not fid:return
            k = key_for(ref, href, fid)
            lib = id_to_lib.get(fid, {})
            if filesize is None:
                try:filesize = int(lib.get('Размер в Library (байт)',''))
                except (ValueError, TypeError):filesize = None
            local = (local_in or lib.get('Локальная копия','') or '').replace('\\', '/')
            found = existing_asset(self.assets, local)
            if k in reg:
                local = reg[k].get('asset_name','')
                found = existing_asset(self.assets, local)
            if k in result:
                rec = result[k]
                rec['refs'] = list(dict.fromkeys(rec.get('refs', [])+[ref]))
                rec.setdefault('pairs', [])
                if href and ref and [href, ref] not in rec['pairs']:
                    rec['pairs'].append([href, ref])
                rec['hrefs'] = list(dict.fromkeys(rec.get('hrefs',[])+([href] if href else [])))
                if href and not rec['href']:
                    rec['href']=href
                    rec['chat_id']=chat_id_by_href.get(href,'') or rec['chat_id']
                if found:rec['found'] = True; rec['local'] = local
                return
            rows = bind_by_id.get(fid, ())
            # We only offer exact anchor determined during original conversion.
            row = next((v for v in rows if v.get('anchor') and (not href or v.get('url','').startswith(href))), None)
            if row is None:row = next((v for v in rows if v.get('origin_anchor')), None)
            anchor = (row or {}).get('anchor') or ''
            origin_anchor = (row or {}).get('origin_anchor') or ''
            target_href = href or href_by_chat.get(lib.get('ID чата',''), '') or (rows[0].get('url','').split('#')[0] if rows else '')
            result[k] = {
                'key':k,'ref':ref,'refs':[ref], 'pairs':[[href,ref]] if href and ref else [], 'href':target_href, 'hrefs':[href] if href else [],
                'chat':chat or next((v.get('chat','') for v in rows), ''),
                'chat_id':chat_id_by_href.get(target_href) or lib.get('ID чата',''),
                'name':name or lib.get('Название','') or 'unknown-file',
                'file_id':fid,'expected_size':filesize,
                'found':found,'local':local if found else '',
                'anchor':anchor,'origin_anchor':origin_anchor,
                'binding':(row or {}).get('binding') or '',
            }

        for row in report:
            ref = row.get('Ссылка в JSON','')
            href = row.get('HTML чата','')
            name = row.get('Имя файла','') or norm_name(ref)
            if not ref or not href:continue
            fid = ref.split(':',1)[-1] if ref.startswith('library:') else ''
            if not FILE_ID_RE.fullmatch(fid):
                # Exact ID from Library wins. If name uniquely matches in same chat,
                # store that relationship but NEVER choose between multiple versions.
                ch_id = chat_id_by_href.get(href,'')
                possible = lib_by_chat_name.get((ch_id,norm_name(name or ref)),[])
                if len(possible) == 1:fid = possible[0]
                else:fid = ''
            insert(ref, href, name, row.get('Чат',''), fid, local_in=row.get('Локальный файл',''))
        for fid, row in id_to_lib.items():
            if existing_asset(self.assets, row.get('Локальная копия','')):
                continue
            # Other missing Library entries must also be recoverable from this tab.
            ch_id = row.get('ID чата','')
            href = href_by_chat.get(ch_id,'')
            insert('library:'+fid, href, row.get('Название',''), '', fid)
        # Registry must keep recovered status even when legacy reports are stale.
        for k, rec in result.items():
            if k in reg:
                local = reg[k].get('asset_name','')
                rec['found'] = existing_asset(self.assets, local)
                rec['local'] = local if rec['found'] else ''
        return result

    def list(self):
        with self.lock:
            r = list(self._records().values())
            r.sort(key=lambda x: (x['found'], x['chat'].casefold(), x['name'].casefold()))
            return {'total':len(r), 'missing':sum(not v['found'] for v in r),
                    'recovered':len(self.registry()), 'items':r}

    def full_list(self):
        """Return rows in EXACT original generated_files.html order.

        The original static list is never replaced.  Each HTML <section> has a
        matching generated_files_report.csv row, verified again in the browser
        before adding an upload button.  Identity is (chat href, raw reference),
        never just the human-readable filename.
        """
        with self.lock:
            report, _ = read_csv(self.archive / 'generated_files_report.csv')
            records = self._records()
            recovered = self.registry()
            by_pair = {}
            for key, item in records.items():
                for pair in item.get('pairs', []):
                    by_pair[tuple(pair)] = key
            rows, used = [], set()
            for original in report:
                href = original.get('HTML чата', '')
                ref = original.get('Ссылка в JSON', '')
                key = by_pair.get((href, ref), '')
                rec = records.get(key, {})
                if key: used.add(key)
                local = rec.get('local', '') or original.get('Локальный файл', '')
                found = existing_asset(self.assets, local)
                name = original.get('Имя файла', '') or ref[:300]
                rows.append({
                    'name':name, 'href':href, 'ref':ref,
                    'key':key if not found else '',
                    'found':found, 'local':local if found else '',
                    'status':original.get('Статус', ''),
                    'recovered':bool(key in recovered and found),
                    'size':rec.get('expected_size'),
                })
            additional = [item for key,item in records.items()
                          if key not in used and not item['found']]
            additional.sort(key=lambda x:(x['chat'].casefold(),x['name'].casefold()))
            return {'rows':rows, 'additional':additional,
                    'total':len(rows), 'found':sum(r['found'] for r in rows),
                    'missing':sum(not r['found'] for r in rows),
                    'recovered':sum(r['recovered'] for r in rows)}

    def recover(self, key, name_header, content_length, reader):
        with self.lock:
            rec = self._records().get(key)
            if not rec:raise ValueError('The requested missing-file record no longer exists')
            if rec['found']:raise ValueError('File already present. Refresh the list.')
            if not isinstance(content_length,int) or content_length <= 0 or content_length > MAX_BYTES:
                raise ValueError('Invalid file size (maximum 1 GiB)')
            expected = rec.get('expected_size')
            if expected and content_length != expected:
                raise ValueError('Size differs from Library metadata: expected %d bytes, selected %d bytes' % (expected, content_length))
            source_name = safe_name(unquote(name_header))
            declared_name = safe_name(rec['name'])
            accepted_suffix = Path(declared_name).suffix.lower()
            submitted_suffix = Path(source_name).suffix.lower()
            if accepted_suffix and submitted_suffix and accepted_suffix != submitted_suffix:
                # ZIP signatures apply to office OOXML, so extension match is needed.
                raise ValueError('Filename extension mismatch: expected %s, got %s' % (accepted_suffix, submitted_suffix))
            if accepted_suffix and accepted_suffix not in ALLOWED_EXTS:
                raise ValueError('Unsupported filename extension: '+accepted_suffix)
            self.user_files.mkdir(parents=True, exist_ok=True)
            self.assets.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(prefix='.upload_', suffix='.part', dir=str(self.user_files))
            tmp = Path(tmp_path)
            size=0
            h=hashlib.sha256()
            try:
                with os.fdopen(tmp_fd,'wb') as f:
                    remaining = content_length
                    while remaining:
                        b = reader.read(min(1024 * 1024, remaining))
                        if not b:raise ValueError('Incomplete upload')
                        f.write(b);h.update(b);size += len(b);remaining -= len(b)
                    f.flush();os.fsync(f.fileno())
                magic = file_magic(tmp)
                if magic and accepted_suffix in {'.png','.jpg','.jpeg','.gif','.webp','.bmp','.pdf'}:
                    if magic not in ({'.jpg','.jpeg'} if accepted_suffix in {'.jpg','.jpeg'} else {accepted_suffix}):
                        raise ValueError('File content does not match expected format')
                if accepted_suffix == '.png' and magic != '.png':raise ValueError('Not a valid PNG')
                if accepted_suffix == '.pdf' and magic != '.pdf':raise ValueError('Not a valid PDF')
                # File identity is the selected record, never merely the display name.
                marker = rec['file_id'] or key
                short = hashlib.sha256(marker.encode()).hexdigest()[:12]
                basename = safe_name(declared_name)
                stem = Path(basename).stem[:70]
                ext = Path(basename).suffix or Path(source_name).suffix or '.bin'
                asset_name = safe_name(stem + '__' + short + ext)
                asset_path = ensure_file_inside(self.assets, asset_name)
                if asset_path.exists():
                    if hash_file(asset_path) != h.hexdigest():
                        raise ValueError('Existing asset under same ID has different content; no overwrite')
                else:shutil.copyfile(tmp, asset_path)
                if rec['file_id'] and FILE_ID_RE.fullmatch(rec['file_id']):
                    # Original builder recognizes file_ID.<extension> in its manual folder.
                    source_saved = self.user_files / (rec['file_id'] + ext)
                else:
                    source_saved = self.user_files / safe_name(rec['name'])
                if source_saved.exists():
                    if source_saved.stat().st_size != size or hash_file(source_saved)!=h.hexdigest():
                        raise ValueError('A different recovered file exists at manual-source path')
                else:shutil.copyfile(tmp, source_saved)
                recovered = self.registry()
                recovered[key] = {'file_id':rec['file_id'],'asset_name':asset_name,
                                  'source_name':str(source_saved.relative_to(self.root)),
                                  'name':rec['name'], 'href':rec['href'],
                                  'hrefs':rec['hrefs'],'refs':rec['refs'],
                                  'chat_id':rec['chat_id'],'sha256':h.hexdigest(),
                                  'size':size,'recovered_utc':datetime.now(timezone.utc).isoformat(),
                                  'anchor':rec['anchor'], 'origin_anchor':rec['origin_anchor'],
                                  'binding':rec['binding']}
                self._save_registry(recovered)
                self._sync_csv(rec, asset_name)
                self._patch_chats(recovered)
                return {'ok':True,'name':rec['name'], 'asset':asset_name,
                        'chat':rec['chat'],'href':rec['href'],
                        'placement':'message' if rec['anchor'] else 'origin' if rec['origin_anchor'] else 'summary',
                        'sha256':h.hexdigest()}
            finally:
                try:tmp.unlink()
                except OSError:pass

    def _sync_csv(self, rec, asset):
        for name in ('generated_files_report.csv','message_file_bindings.csv',
                     'library_integrity_report.csv','missing_generated_files.csv',
                     'unplaced_library_files.csv'):
            p = self.archive/name
            rows, fields=read_csv(p)
            if not fields:continue
            changed=False
            for r in rows:
                matches = False
                if name == 'generated_files_report.csv':
                    matches = (r.get('HTML чата') in rec['hrefs'] and
                               r.get('Ссылка в JSON','') in rec['refs']) or (
                               rec['file_id'] and r.get('Ссылка в JSON') == 'library:'+rec['file_id'])
                    if matches:
                        r['Локальный файл'] = asset
                        r['Статус'] = 'ВОССТАНОВЛЕН ПОЛЬЗОВАТЕЛЕМ'
                        r['Основание физического файла'] = 'manual browser upload; selected record; SHA256 stored'
                elif name in ('message_file_bindings.csv','missing_generated_files.csv',
                              'unplaced_library_files.csv'):
                    matches=bool(rec['file_id'] and r.get('file_id')==rec['file_id'] and
                                 (not rec['chat_id'] or r.get('chat_id')==rec['chat_id']))
                    if matches and name in ('message_file_bindings.csv','unplaced_library_files.csv'):
                        r['local']=asset
                        r['evidence']=(r.get('evidence','')+'; recovered by user upload').strip('; ')
                elif name == 'library_integrity_report.csv':
                    matches=bool(rec['file_id'] and r.get('ID файла Library')==rec['file_id'])
                    if matches:
                        r['Локальная копия']=asset
                        r['Метод идентификации']='user supplied file for exact Library ID'
                        r['Проверка размера']='MATCH' if not rec['expected_size'] else 'size exact'
                        r['Проверка содержимого']='provided by user, SHA-256 in recovered_files.json'
                if matches:changed=True
            if name=='missing_generated_files.csv':
                newrows=[r for r in rows if not (rec['file_id'] and r.get('file_id')==rec['file_id'])]
                changed = len(newrows)!=len(rows)
                rows=newrows
            if changed:
                backup=p.with_name(p.name+'.before_recovery.csv')
                if not backup.exists():shutil.copy2(p,backup)
                write_csv_atomic(p,rows,fields)

    def _patch_chats(self, reg):
        """Rebuild only affected chat HTML from its pre-recovery backup.

        The original v7.3 inserted media AFTER .body, creating a third CSS-grid
        child in the AUTHOR column.  This method instead restores Markdown
        image/download placeholders inside .body, or appends media INSIDE .body
        when no unambiguous placeholder exists. It is also safe to re-run for
        files already uploaded and never needs the source JSON shards.
        """
        # The report keeps the ORIGINAL sandbox/file-service reference and
        # precise assistant message timestamp even after its status changes.
        # This lets us ensure that replacing descriptive missing-link labels
        # is unambiguous. A single assistant answer can contain multiple
        # independent links (and many labels); do not guess in that case.
        report, _ = read_csv(self.archive / 'generated_files_report.csv')
        by_time = {}
        for row in report:
            ref = row.get('Ссылка в JSON', '')
            if ref and not ref.startswith('library:') and row.get('Дата сообщения (timestamp)'):
                k = (row.get('HTML чата', ''), row['Дата сообщения (timestamp)'])
                by_time.setdefault(k, set()).add(ref)

        by_href = {}
        for key, rec in reg.items():
            if not rec.get('asset_name') or not existing_asset(self.assets, rec['asset_name']):
                continue
            for href in dict.fromkeys(rec.get('hrefs') or [rec.get('href')]):
                if not href:
                    continue
                item = dict(rec)
                if href != rec.get('href'):
                    # Never reuse an anchor belonging to a DIFFERENT chat.
                    item['anchor'] = ''
                    item['origin_anchor'] = ''
                source_groups = []
                for row in report:
                    if (row.get('HTML чата') != href or
                        row.get('Ссылка в JSON', '').startswith('library:') or
                        row.get('Ссылка в JSON') not in item.get('refs', ())):
                        continue
                    group = by_time.get((href, row.get('Дата сообщения (timestamp)', '')), set())
                    if group:
                        source_groups.append(group)
                # Require ALL observed uses of this raw source in this chat
                # to be singleton; one clean occurrence is not sufficient.
                item['source_singleton'] = bool(source_groups and
                                                all(len(group) == 1 for group in source_groups))
                by_href.setdefault(href, []).append((key, item))

        # When one assistant answer contains multiple outputs, the original
        # HTML placeholder no longer includes the sandbox URL. Recover exact
        # Markdown label → URL mappings from the *original* export shard,
        # using the source message timestamp and rejecting ambiguous labels.
        # This is supplemental evidence; the old single-source path remains.
        try:
            from recovery_source_links import get_source_link_roles, labels_for_item, normalized_label
            unresolved = {href: entries for href, entries in by_href.items()
                          if any(not item.get('source_singleton') for _, item in entries)}
            source_roles = get_source_link_roles(self.root, self.archive, report, unresolved)
            for href, entries in by_href.items():
                for _, item in entries:
                    item['original_link_roles'] = labels_for_item(href, item, report, source_roles)
        except (ImportError, OSError, ValueError):
            # Never guess labels if the original export cannot be read.
            for entries in by_href.values():
                for _, item in entries:
                    item['original_link_roles'] = {}
            normalized_label = lambda s: ' '.join(html.unescape(str(s)).split()).casefold()

        def message_body_range(page, anchor):
            """Return the exact .body CONTENT offsets, never the role/grid cell.

            Converter output is <article id=...><div class=role>...</div>
            <div class=body>...</div></article>. Nested divs may appear inside
            the body, so its closing tag is the LAST </div> in the article.
            """
            m = re.search(r'<article\b[^>]*\bid=["\']' + re.escape(anchor) +
                          r'["\'][^>]*>', page, re.I)
            if not m:
                return None
            article_end = page.find('</article>', m.end())
            if article_end < 0:
                return None
            body = re.search(r'<div\b[^>]*\bclass=["\'][^"\']*\bbody\b[^"\']*["\'][^>]*>',
                             page[m.end():article_end], re.I)
            if not body:
                return None
            begin = m.end() + body.end()
            end = page.rfind('</div>', begin, article_end)
            if end < begin:
                return None
            return begin, end

        missing_span = re.compile(r'<span\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bmissing-file\b)[^>]*>'
                                  r'([\s\S]*?)</span>', re.I)

        def restore_placeholders(body, item, href, label, image):
            """Update original Markdown image and download links in place.

            Descriptive labels don't contain the filename, e.g. both
            'Агентный цирк' and 'Скачать мем №08' point to MEME_08.png.
            Only replace ALL labels if the source report proves the answer
            referenced ONE distinct missing file. Otherwise accept only a
            label explicitly identifying the file; leave ambiguity intact.
            """
            count = [0, 0]  # image replacements, download replacements
            canonical_name = norm_name(item.get('name', ''))
            def patch(m):
                raw = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
                title = re.sub(r'^\s*⚠\s*', '', raw).strip()
                title = re.sub(r'\s*\((?:нет локальной копии|локальный файл не найден)\)\s*$',
                               '', title, flags=re.I).strip()
                literal_name = norm_name(title)
                basename_matches = bool(canonical_name and
                                         (literal_name == canonical_name or
                                          canonical_name in raw.casefold()))
                original_role = item.get('original_link_roles', {}).get(normalized_label(title))
                if not (item.get('source_singleton') or basename_matches or
                        original_role is not None):
                    return m.group(0)
                # Never re-target a warning that lacks the expected missing
                # marker (may be an unrelated explanation, not a link).
                if 'нет локальной копии' not in raw and 'локальный файл не найден' not in raw:
                    return m.group(0)
                safe_title = html.escape(title or item.get('name','Файл'))
                # The original Markdown determines IMAGE versus DOWNLOAD.
                # A label such as "PNG в высоком разрешении" is a link,
                # despite the recovered file being a PNG.
                is_download = (not original_role if original_role is not None else
                               bool(re.search(r'\b(?:скачать|скачивание|download)\b|^[↓📎]', title, re.I)))
                if image and not is_download:
                    count[0] += 1
                    return ('<a href="' + href + '" target="_blank" rel="noopener" '
                            'data-recovery-link="image"><img class="inline-img" '
                            'loading="lazy" src="' + href + '" alt="' +
                            html.escape(title or item.get('name','Файл'), quote=True) + '"></a>')
                count[1] += 1
                return ('<a download href="' + href + '" data-recovery-link="download">📎 ' +
                        safe_title + '</a>')
            return missing_span.sub(patch, body), count

        # Different Library IDs may legitimately share one human filename.
        # Never delete their missing warnings by filename alone.
        lib_ids_by_name = {}
        raw_refs_by_name = {}
        for row in report:
            ref = row.get('Ссылка в JSON', '')
            name = norm_name(row.get('Имя файла', ''))
            target = row.get('HTML чата', '')
            if not name or not target:
                continue
            if ref.startswith('library:'):
                lib_ids_by_name.setdefault((target, name), set()).add(ref)
            elif ref:
                raw_refs_by_name.setdefault((target, name), set()).add(ref)

        def clean_missing_detail(match, entries, current_href):
            """Delete only genuinely recovered <li>, keep all other warnings."""
            detail = match.group(0)
            items = re.findall(r'<li\b[^>]*>[\s\S]*?</li>', detail, re.I)
            if not items:
                return detail
            names = [norm_name(rec.get('name', '')) for _, rec in entries]
            remove = []
            for element in items:
                literal = html.unescape(re.sub(r'<[^>]+>', '', element)).strip()
                normal_literal = norm_name(literal)
                matched = False
                for _, rec in entries:
                    fid = rec.get('file_id', '')
                    nm = norm_name(rec.get('name', ''))
                    if fid and fid in literal:
                        matched = True
                        break
                    lib_versions = lib_ids_by_name.get((current_href, nm), set())
                    raw_versions = raw_refs_by_name.get((current_href, nm), set())
                    ambiguous_filename = (len(lib_versions) > 1 or
                                          (not lib_versions and len(raw_versions) > 1))
                    if (nm and not ambiguous_filename and names.count(nm) == 1 and
                        (normal_literal == nm or normal_literal.startswith(nm+' —') or
                         normal_literal.startswith(nm+' - '))):
                        matched = True
                        break
                if matched:
                    remove.append(element)
            if not remove:
                return detail
            if len(remove) == len(items):
                return ''
            for old in remove:
                detail = detail.replace(old, '', 1)
            # All known messages have one number in the summary, update it.
            left = len(items) - len(remove)
            return re.sub(r'(<summary>[^<]*?)(\d+)(</summary>)',
                          lambda m:m.group(1)+str(left)+m.group(3), detail, count=1)

        for href, entries in by_href.items():
            if not re.fullmatch(r'chats/[a-zA-Z0-9_.-]+\.html', href):
                continue
            path = ensure_file_inside(self.archive, href, must_exist=True)
            original = path.read_text(encoding='utf-8')
            backup = path.with_name(path.name + '.before_recovery.html')
            # Crucial for already-recovered files: v7.3 replaced no original
            # placeholders. Reconstruct from the pre-recovery page and all
            # registry entries, rather than adding another card to bad markup.
            if (backup.is_file() and 'ARCHIVE_RECOVERY_START:' in original and
                'ARCHIVE_RECOVERY_START:' not in backup.read_text(encoding='utf-8')):
                page = backup.read_text(encoding='utf-8')
            else:
                page = original
                page = re.sub(r'<section class="files-overview" id="recovered-attachments">'
                              r'[\s\S]*?</section>\s*', '', page)
                page = re.sub(r'<!-- ARCHIVE_RECOVERY_START:[a-z0-9_]+ -->[\s\S]*?'
                              r'<!-- ARCHIVE_RECOVERY_END:[a-z0-9_]+ -->\n?', '', page)
            page = re.sub(r'<details\b[^>]*class="[^"]*missing-output[^"]*"[^>]*>'
                          r'[\s\S]*?</details>',
                          lambda m: clean_missing_detail(m, entries, href), page, flags=re.I)
            rendered = []
            for key, item in entries:
                local = item['asset_name']
                ref = '../assets/' + quote(local, safe='')
                label = html.escape(item['name'])
                uid = html.escape(key, quote=True)
                img = Path(local).suffix.lower() in {'.png','.jpg','.jpeg','.gif','.webp','.avif','.bmp'}
                inner = ('<a target="_blank" rel="noopener" href="'+ref+'">'
                         '<img loading="lazy" style="max-width:100%;max-height:700px;'
                         'border-radius:8px" src="'+ref+'" alt="'+label+'"></a>'
                         if img else '<a target="_blank" download href="'+ref+'">⬇ '+label+'</a>')
                block = ('<!-- ARCHIVE_RECOVERY_START:'+key+' -->\n'
                         '<div class="library-media recovered-media" data-recovered="'+uid+'">'
                         '<p style="font-size:12px;color:#24785c">✓ Восстановлено из личной копии</p>'+
                         inner+'</div>\n'
                         '<!-- ARCHIVE_RECOVERY_END:'+key+' -->\n')
                anchor = item.get('anchor') or ''
                inserted = False
                if item.get('binding') == 'synthesized' and not anchor and item.get('origin_anchor'):
                    origin = item['origin_anchor']
                    if re.fullmatch(r'message-\d+', origin):
                        pat = r'(<article\s+id="'+re.escape(origin)+r'"[^>]*>[\s\S]*?</article>)'
                        m = re.search(pat, page, re.I)
                        if m:
                            fake_anchor = 'recovered-generated-'+key
                            synthetic = ('<!-- ARCHIVE_RECOVERY_START:'+key+' -->\n'
                                '<article id="'+fake_anchor+'" class="synthetic-result">'
                                '<div class="role assistant">ChatGPT</div><div class="body">'
                                '<p class="synthetic-note">Результат генерации изображения · '
                                'восстановлено из Library; исходный текст ответа отсутствует</p>'
                                '<div class="library-media recovered-media" data-recovered="'+uid+'">'
                                +inner+'</div></div></article>\n'
                                '<!-- ARCHIVE_RECOVERY_END:'+key+' -->\n')
                            page = page[:m.end()]+'\n'+synthetic+page[m.end():]
                            anchor = fake_anchor
                            inserted = True
                elif anchor and re.fullmatch(r'(message|generated)-\d+', anchor):
                    pos = message_body_range(page, anchor)
                    if pos is not None:
                        start, end = pos
                        body = page[start:end]
                        body, n = restore_placeholders(body, item, ref, label, img)
                        # The recovered file must never become a direct child of
                        # article. Place a card ONLY if original image isn't
                        # already restored at its original Markdown position.
                        if n[0] == 0 and n[1] == 0 and ref not in body:
                            body += '\n' + block
                        # For explicit download-only responses, keep the
                        # original intent; don't force another image card.
                        page = page[:start]+body+page[end:]
                        inserted = True
                target_anchor = anchor if inserted else item.get('origin_anchor') or 'recovered-attachments'
                summary = ('<div class="file-entry" data-recovered="'+uid+'" style="margin:8px 0">'
                           '<span style="font-size:22px">'+('🖼' if img else '📄')+'</span>'
                           '<div class="file-entry-text">'
                           '<a href="'+ref+'" target="_blank" rel="noopener">'+label+'</a> · '
                           '<a href="#'+html.escape(target_anchor, quote=True)+'">↗ '+
                           ('сообщение' if inserted else
                            'исходный запрос' if target_anchor!='recovered-attachments' else 'в сводке')+'</a>'
                           '</div></div>')
                rendered.append('<!-- ARCHIVE_RECOVERY_START:'+key+' -->\n'+summary+
                                '\n<!-- ARCHIVE_RECOVERY_END:'+key+' -->\n')
            if rendered:
                head = ('<section class="files-overview" id="recovered-attachments">'
                        '<h2>✓ Восстановленные файлы</h2>'+''.join(rendered)+'</section>')
                page = page.replace('</body>',head+'</body>',1)
            if page != original:
                if not backup.exists():
                    shutil.copy2(path, backup)
                temp = path.with_name(path.name + '.recovery.tmp')
                temp.write_text(page, encoding='utf-8')
                os.replace(temp, path)


def upload_page():
    """Rendered only over loopback HTTP. Kept separate from untrusted message iframe."""
    return r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Файлы ChatGPT — восстановление</title>
<style>*{box-sizing:border-box}body{font:14px system-ui,Arial,sans-serif;color:#202124;max-width:1040px;margin:28px auto;padding:0 18px}h1{font-size:24px}.sub{color:#52616b;line-height:1.5}.bar{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}input[type="search"]{flex:1;min-width:220px;padding:12px;border:1px solid #bbb;border-radius:9px}button{padding:9px 15px;border:1px solid #1e8068;border-radius:8px;background:#0c8065;color:white;font:inherit;cursor:pointer}button:disabled{opacity:.5;cursor:default}.item{border:1px solid #e0e5e4;margin:9px 0;border-radius:10px;padding:14px;background:#fdfefe;overflow-wrap:anywhere}.file{font-weight:650;font-size:15px}.muted{font-size:12px;color:#637078;margin:8px 0}.success{color:#0c7750}.fail{color:#9c451a}.load{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:8px}input[type=file]{max-width:100%;font-size:12px}progress{width:160px}.tag{font-size:11px;color:#666;background:#f0f2f2;border-radius:5px;padding:3px 6px}a{color:#0b8062}#status{padding:12px 0}.hint{padding:12px;background:#f4f8f7;border-radius:8px}.hidden{display:none}</style></head>
<body><h1>📦 Файлы ChatGPT — восстановление</h1><p class="hint">Выберите отсутствующий файл и загрузите его из своей копии или из ChatGPT Library. Файл сохраняется <b>только на этом компьютере</b>. Имя и размер сверяются с записью, если она есть; при неоднозначной привязке файл помещается только в сводку чата. Никакой пересборки 1 ГБ экспорта не требуется.</p>
<div class="bar"><input type="search" id="filter" placeholder="Найти по имени или чату"><label><input type="checkbox" id="showall"> Показать найденные</label><button onclick="refresh()">Обновить список</button></div>
<div id="status">Загрузка записей…</div><div id="items"></div><p id="more"></p>
<script>
let all=[];let endpoint=location.pathname.replace(/generated_files\.html$/,'');
function el(tag,cls,text){let n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n}
async function refresh(){let res=await fetch(endpoint+'__recovery/api/list',{cache:'no-store'});if(!res.ok)throw Error('HTTP '+res.status);let d=await res.json();all=d.items;document.getElementById('status').textContent='Записей: '+d.total+' · отсутствуют: '+d.missing+' · восстановлены вручную: '+d.recovered;render()}
function render(){let q=document.getElementById('filter').value.toLocaleLowerCase();let allcheck=document.getElementById('showall').checked;let items=all.filter(x=>(allcheck||!x.found)&&((x.name+' '+x.chat+' '+x.file_id).toLocaleLowerCase().includes(q)));let box=document.getElementById('items');box.replaceChildren();items.slice(0,200).forEach(x=>{let a=el('section','item');let title=el('div','file',x.name);a.append(title);a.append(el('div','muted',(x.chat||'Чат не указан')+' · '+(x.file_id||x.ref)+' · '+(x.expected_size?'ожидаемый размер: '+x.expected_size+' байт':'размер не указан')));if(x.found){a.append(el('span','success','✓ Локальная копия найдена'));if(x.local){let dl=el('a','', ' · Скачать');dl.href='assets/'+x.local.split('/').map(encodeURIComponent).join('/');dl.download='';a.append(dl)}}else{let div=el('div','load'),inp=el('input');inp.type='file';inp.setAttribute('aria-label','Выбрать файл '+x.name);let send=el('button','', 'Загрузить');let meter=el('progress','');meter.max=100;meter.value=0;meter.className='hidden';let msg=el('small','muted','');send.onclick=()=>upload(x,inp,send,meter,msg);div.append(inp,send,meter,msg);a.append(div)}if(x.href){let link=el('a','', 'Открыть чат');link.href=x.href;link.target='_blank';a.append(el('div','muted')).append(link)}box.append(a)});document.getElementById('more').textContent=items.length>200?'Показаны первые 200 результатов. Уточните поиск.':''}
function upload(x,inp,button,meter,msg){let file=inp.files?.[0];if(!file){msg.textContent='Выберите файл';return}if(!confirm('Добавить «'+x.name+'» ('+file.size+' байт) в локальный архив?'))return;button.disabled=true;meter.classList.remove('hidden');msg.textContent='Копирование…';let xhr=new XMLHttpRequest();xhr.open('POST',endpoint+'__recovery/api/upload/'+encodeURIComponent(x.key));xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-Original-Filename',encodeURIComponent(file.name));xhr.upload.onprogress=e=>{if(e.lengthComputable)meter.value=Math.round(e.loaded/e.total*100)};xhr.onload=async()=>{button.disabled=false;try{let r=JSON.parse(xhr.responseText);if(xhr.status!==200)throw Error(r.error||'HTTP '+xhr.status);msg.textContent='✓ Файл восстановлен, чат обновлён';await refresh()}catch(e){msg.textContent='Ошибка: '+e.message}};xhr.onerror=()=>{button.disabled=false;msg.textContent='Ошибка локального соединения'};xhr.send(file)}
document.getElementById('filter').addEventListener('input',render);document.getElementById('showall').addEventListener('change',render);refresh().catch(e=>document.getElementById('status').textContent='Ошибка: '+e.message);
</script></body></html>'''.replace('\"', '"')
