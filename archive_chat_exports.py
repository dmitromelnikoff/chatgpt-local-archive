#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7.3.16: derive read-only chat metadata and Markdown exports from the REAL
OpenAI conversation graph. Runs once during installation, not on each page view.
No edits to source JSON, media, recovered files or existing chat HTML.
"""
from __future__ import annotations
import csv
import html
from html.parser import HTMLParser
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, quote
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from chatgpt_local_archive import StreamJSON, ordered_nodes, find_shards, is_intelligent_ui, fallback_text
from intelligent_ui_markdown import markdownize_dil
from dil_template_safe import expand_template

ARCHIVE=ROOT/'ChatGPT_Local_Archive'
OUT=ARCHIVE/'chat_exports'
HTML_NAME=re.compile(r'^chats/chat_\d{7}_[0-9a-f]{8}\.html$')
IMG_TAG=re.compile(r'<img\b[^>]*>',re.I|re.S)
IMG_SRC=re.compile(r'\bsrc\s*=\s*[\'\"]([^\'\"]+)[\'\"]',re.I)
USER_ROLE=re.compile(r'<article\b[^>]*>\s*<div\s+class=[\'\"]role user[\'\"]',re.I)
VALID_IMG={'.png','.jpg','.jpeg','.webp','.gif','.svg','.bmp','.avif','.ico'}


def read_csv(path):
    if not path.is_file():return []
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f,delimiter=';'))


def image_keys(source):
    result=set()
    for tag in IMG_TAG.findall(source):
        m=IMG_SRC.search(tag)
        if not m:continue
        s=html.unescape(m.group(1)).replace('\\','/').split('?',1)[0]
        if not s.startswith('../assets/') and not s.startswith('/assets/') and not s.startswith('assets/'):
            continue
        name=unquote(s.rsplit('/',1)[-1])
        if Path(name).suffix.lower() in VALID_IMG:result.add(name)
    return sorted(result)


def text_from_part(obj):
    if isinstance(obj,str):return obj
    if isinstance(obj,dict):
        for key in ('raw_dil','dil','text','transcription','caption','description','code'):
            value=obj.get(key)
            if isinstance(value,str) and value.strip():return value
    return ''


def markdown_message(message):
    content=message.get('content') or {}
    ctype=str(content.get('content_type') or '') if isinstance(content,dict) else ''
    if ctype in ('thoughts','reasoning_recap','analysis','tool_result','execution_output'):
        return ''
    parts=content.get('parts') if isinstance(content,dict) else content
    if not isinstance(parts,list):parts=[parts] if parts is not None else []
    fallback=fallback_text(message,content) or ''
    texts=[]; attachments=[]
    for part in parts:
        raw=text_from_part(part)
        if raw and raw.strip():
            if is_intelligent_ui(raw):
                expanded,_=expand_template(raw)
                try:raw=markdownize_dil(expanded)
                except Exception:raw=fallback or raw
            texts.append(raw.strip())
        elif isinstance(part,dict):
            ptr=str(part.get('asset_pointer') or part.get('file_id') or part.get('file_url') or '')
            name=str(part.get('filename') or part.get('name') or part.get('file_name') or '')
            if ptr and (name or ptr):attachments.append('📎 '+(name or ptr))
    # Use official fallback if primary text is absent; never append it to the
    # primary DIL output or the same answer would be duplicated.
    if not texts and fallback:
        texts=[fallback.strip()]
    for attachment in attachments:
        if attachment not in '\n'.join(texts):texts.append(attachment)
    return '\n\n'.join(t for t in texts if t.strip()).strip()


def is_service(message):
    if not isinstance(message,dict):return True
    author=message.get('author') or {}
    role=author.get('role') if isinstance(author,dict) else author
    if role not in ('user','assistant'):return True
    meta=message.get('metadata') or {}
    channel=(meta.get('channel') or '') if isinstance(meta,dict) else ''
    if channel in ('analysis','commentary','notification','justify','confidence','summary'):
        return True
    content=message.get('content') or {}
    typ=content.get('content_type') if isinstance(content,dict) else ''
    if typ in ('thoughts','reasoning_recap','analysis','tool_result','execution_output'):
        return True
    return False


def make_markdown(conversation,href):
    title=str(conversation.get('title') or 'Без названия')
    result=['# '+title.replace('\n',' ').strip(),'']
    # Match the originally selected path (current_node), not every alternative
    # branch. Do NOT include service nodes even if they are visible in HTML.
    main,_=ordered_nodes(conversation)
    ix=0
    for node in main:
        message=node.get('message') if isinstance(node,dict) else None
        if is_service(message):continue
        author=message.get('author') or {}
        role=author.get('role') if isinstance(author,dict) else author
        value=markdown_message(message)
        if not value:continue
        ix+=1
        result+=['## '+('Вы' if role=='user' else 'ChatGPT'),'',value,'']
    if ix==0:result+=['*В основной ветке нет экспортированных текстовых сообщений.*','']
    return '\n'.join(result).rstrip()+'\n'


def archive_state(conversation):
    # Unlike the local archive itself, this flag must come from OpenAI metadata.
    val=conversation.get('is_archived')
    if not isinstance(val,bool):
        meta=conversation.get('metadata')
        val=meta.get('is_archived') if isinstance(meta,dict) else None
    return val if isinstance(val,bool) else None


def scan_html(archive,href):
    path=archive/href
    if not path.is_file():return 0,[]
    body=path.read_text(encoding='utf-8-sig',errors='replace')
    return len(USER_ROLE.findall(body)),image_keys(body)


def make_index(root=ROOT,archive=ARCHIVE,progress=print):
    root=Path(root).resolve();archive=Path(archive).resolve()
    OUT=archive/'chat_exports';OUT.mkdir(exist_ok=True)
    csv_rows=read_csv(archive/'conversations_index.csv')
    by_cid={};by_href={}
    for rec in csv_rows:
        cid=rec.get('conversation_id','');href=rec.get('html','')
        if not HTML_NAME.fullmatch(href):continue
        if cid:by_cid.setdefault(cid,[]).append(href)
        by_href[href]=rec
    if not by_href:raise ValueError('conversations_index.csv отсутствует или не содержит корректных имён чатов')
    index=[]
    for n,(href,rec) in enumerate(by_href.items(),1):
        questions,imgs=scan_html(archive,href)
        index.append({'href':href,'conversation_id':rec.get('conversation_id',''),
                      'questions':questions,'images':len(imgs),'image_assets':imgs,
                      'is_archived':None,'source_ready':False})
        if n%250==0:progress('  Проверены HTML:',n,'/',len(by_href))
    indexed={rec['href']:rec for rec in index}
    finished=set()
    shards=[p for p in sorted(root.glob('conversations-*.json'))
            if re.fullmatch('conversations-\\d+\\.json',p.name,re.I)]
    if not shards and (root/'conversations.json').is_file():shards=[root/'conversations.json']
    for shard in shards:
        progress('  Читаем источник',shard.name)
        with shard.open('r',encoding='utf-8-sig') as handle:
            for conv in StreamJSON(handle).conversations():
                if not isinstance(conv,dict):continue
                cid=str(conv.get('id') or conv.get('conversation_id') or '')
                candidate=by_cid.get(cid,[])
                href=next((h for h in candidate if h not in finished),None)
                if href is None:continue
                finished.add(href)
                rec=indexed[href];rec['is_archived']=archive_state(conv)
                try:
                    target=OUT/(Path(href).stem+'.md')
                    target.write_text(make_markdown(conv,href),encoding='utf-8')
                    rec['source_ready']=True
                except Exception as exc:
                    progress('  Предупреждение: ошибка MD',href,repr(exc))
    # Cache VERIFIED existing original export links by their exact source URL
    # and chat, so .md exports refer to local files even without a recovery event.
    link_groups={}
    for row in read_csv(archive/'generated_files_report.csv'):
        href=str(row.get('HTML чата') or '')
        src=normalized_link(str(row.get('Ссылка в JSON') or ''))
        asset=str(row.get('Локальный файл') or '')
        if href not in indexed or not src or not asset or not (archive/'assets'/asset).is_file():continue
        if not re.fullmatch(r'[^/\\]+',asset):continue
        link_groups.setdefault(href,{}).setdefault(src,set()).add('../assets/'+quote(asset,safe=''))
    linksdir=OUT/'links';linksdir.mkdir(exist_ok=True)
    for href,entry in link_groups.items():
        # Ambiguous source refs must NOT be resolved at random.
        verified={src:next(iter(items)) for src,items in entry.items() if len(items)==1}
        (linksdir/(Path(href).stem+'.json')).write_text(json.dumps(verified,ensure_ascii=False),encoding='utf-8')
    output=archive/'chat_metadata_index.json'
    temp=output.with_suffix('.json.tmp')
    temp.write_text(json.dumps({'version':'7.3.16','chats':index},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temp.replace(output)
    progress('Готово: индексов',len(index),'MD из исходного JSON:',sum(x['source_ready'] for x in index))
    return index


def normalized_link(value):
    return html.unescape(unquote(value)).replace('\\','/').strip()


def resolved_markdown(archive,href,md,registry):
    """Only rewrite links by exact origin reference or uniquely identified local
    filename among recovered items belonging to THIS chat. Never guess globally.
    Relative ../assets paths work when .md is placed in chat_exports/.
    """
    from archive_recovery import existing_asset,norm_name
    exact={};names={}
    # Baseline links: files that existed at initial conversion.
    initial=Path(archive)/'chat_exports'/'links'/(Path(href).stem+'.json')
    try:
        if initial.is_file():
            old=json.loads(initial.read_text(encoding='utf-8'))
            for src,target in old.items():
                asset=unquote(target.rsplit('/',1)[-1])
                if (Path(archive)/'assets'/asset).is_file():
                    exact.setdefault(src,set()).add(target)
    except (OSError,ValueError):pass
    for entry in registry.values():
        if not isinstance(entry,dict):continue
        related=entry.get('hrefs') or [entry.get('href','')]
        if href not in related:continue
        asset=entry.get('asset_name','')
        if not existing_asset(Path(archive)/'assets',asset):continue
        dest='../assets/'+quote(asset,safe='')
        for src in entry.get('refs',[]) or []:
            src=normalized_link(str(src))
            if src:exact[src]={dest}
        if entry.get('name'):
            names.setdefault(norm_name(entry['name']),set()).add(dest)
    def changed(match):
        # Conservative replacement: only URL in an existing Markdown link.
        pre,url,post=match.group(1,2,3)
        key=normalized_link(url)
        cands=exact.get(key,set())
        if not cands and key.startswith(('sandbox:','file-service:','sediment:')):
            cands=names.get(norm_name(key),set())
        return pre+next(iter(cands))+post if len(cands)==1 else match.group(0)
    # Handles normal paths and spaces, while preserving the existing label,
    # image-vs-download semantics and links without a confirmed match.
    return re.sub(r'(!?\[[^\]\n]{0,1000}\]\()([^\n)]{1,2048})(\))',changed,md)

if __name__=='__main__':
    make_index()
