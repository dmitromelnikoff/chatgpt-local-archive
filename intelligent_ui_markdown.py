# -*- coding: utf-8 -*-
"""Read-only DIL -> meaningful Markdown fallback; does not modify ChatGPT's math pipeline.

Unsafe dynamic DIL is never evaluated. SVG drawing primitives are represented by
visible text labels, rather than shown as noisy XML. Original Markdown is kept in
source order, including tables and TeX math blocks.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from html.parser import HTMLParser
from html import unescape
import re

@dataclass
class Node:
    tag: str = ''
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

class DILParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), [])
        self.stack[-1].children.append(node)
        if tag not in ('br','hr','img','input','meta','link','rect','path','circle',
                       'line','polygon','polyline','ellipse','stop','divider','icon'):
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs), []))

    def handle_endtag(self, tag):
        # Never accidentally close the surrounding Markdown on invalid markup.
        for idx in range(len(self.stack)-1, 0, -1):
            if self.stack[idx].tag == tag:
                del self.stack[idx:]
                break

    def handle_data(self, value):
        if value.strip() or ('\n' in value and len(self.stack)==1):
            self.stack[-1].children.append(value)

    def handle_entityref(self, name):
        self.handle_data(unescape('&'+name+';'))

    def handle_charref(self, name):
        self.handle_data(unescape('&#'+name+';'))


def compact_text(value):
    return re.sub(r'\s+', ' ', value).strip()


def text_content(node):
    if isinstance(node, str):
        return node
    if node.tag in ('path','rect','circle','line','ellipse','polygon','polyline'):
        return ''
    return ''.join(text_content(child) for child in node.children)


def _bold_once(value):
    """Avoid Markdown delimiter nesting, which Mistune displays literally.

    DIL containers (<badge>, <title>, <strong>) may already hold a Markdown
    strong span. Wrapping it again creates ****label****, not bold text.
    Do not modify existing Markdown, fenced code or TeX contents.
    """
    content=value.strip()
    if not content:
        return ''
    if '**' in content:
        return content
    return '**'+content+'**'


def to_markdown(node, depth=0):
    if isinstance(node, str):
        return node
    tag = node.tag
    if tag == 'svg':
        # A diagram is not reproducible in Markdown. Preserve only its real
        # original text labels, never invent arrows/relationships.
        labels=[]
        def visit(cur):
            if isinstance(cur,str): return
            if cur.tag in ('text','title','desc'):
                value=compact_text(text_content(cur))
                if value: labels.append(value)
                return
            for child in cur.children:visit(child)
        visit(node)
        return '\n\n> **Схема (текстовые подписи):** '+ ' · '.join(labels) + '\n\n' if labels else '\n\n*[Схема SVG — см. режим Intelligent UI]*\n\n'
    if tag in ('rect','path','circle','ellipse','polygon','polyline','line','defs','g','stop'):
        return ''
    if tag=='icon':
        icons={'arrow-down':'↓','arrow-up':'↑','arrow-left':'←','arrow-right':'→',
               'check':'✓','x':'×','alert-triangle':'⚠'}
        return icons.get(str(node.attrs.get('name','')).lower(),'')
    if tag=='divider' or tag=='hr': return '\n\n---\n\n'
    if tag=='br':return '\n'
    if tag in ('image','asyncimage'):
        return str(node.attrs.get('alt') or node.attrs.get('description') or '[Изображение — см. визуальный режим]')
    if tag in ('script','style','iframe','object','embed'):
        return ''
    if tag in ('listitem','li'):
        return '\n- ' + compact_text(''.join(to_markdown(child,depth+1) for child in node.children))
    if tag in ('row','tr'):
        pieces=[compact_text(to_markdown(child,depth+1)) for child in node.children]
        pieces=[p for p in pieces if p and not p.isspace()]
        if not pieces: return ''
        # Keep all visible labels and values, but drop empty graphical bars.
        return '\n\n' + (' — '.join(pieces) if len(pieces)<=3 else ' · '.join(pieces)) + '\n\n'
    contents=''.join(to_markdown(child,depth+1) for child in node.children)
    if tag in ('badge','tag'):
        return _bold_once(compact_text(contents))
    if tag in ('title',):
        return '\n\n'+_bold_once(compact_text(contents))+'\n\n' if compact_text(contents) else ''
    if tag in ('caption',):
        return '\n\n*'+compact_text(contents)+'*\n\n' if compact_text(contents) else ''
    if tag in ('strong','bold'):return _bold_once(contents)
    if tag in ('em','italic'):return '*'+contents.strip()+'*'
    if tag in ('list','ul','ol'):
        return '\n\n'+contents+'\n\n'
    if tag == 'box' and not compact_text(contents) and re.fullmatch(r'#[0-9A-Fa-f]{3,8}',str(node.attrs.get('background') or '')):
        # A DIL color swatch has no text children. Markdown cannot represent
        # its appearance, but the HEX label preserves its actual information.
        return ' `'+str(node.attrs['background'])+'` '
    if tag in ('grid','grid-item','columns','column','stack','box','card','container','callout','blockquote','table','thead','tbody'):
        return '\n\n'+contents.strip()+'\n\n' if contents.strip() else ''
    if tag in ('codeblock','writingblock'):
        return '\n\n```\n'+contents.strip()+'\n```\n\n'
    if tag in ('link','entity','cite'):
        # Fallback labels stay readable; URLs from untrusted DIL are not injected.
        return contents or str(node.attrs.get('value') or '')
    # <text>, <p>, <span>, unrecognized harmless DIL structures:
    return contents


def markdownize_dil(raw: str) -> str:
    # Protect fenced code blocks from HTMLParser: code is text, not DIL markup.
    fences=[]
    pattern=re.compile(r'(?ms)^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1\2[ \t]*(?:\n|$)')
    def protect(match):
        idx=len(fences)
        fences.append(match.group(0))
        return f'\n\nARCHIVEFENCETOKEN{idx:06d}END\n\n'
    protected=pattern.sub(protect,raw.replace('\r\n','\n'))
    parser=DILParser()
    parser.feed(protected)
    parser.close()
    text=to_markdown(parser.root)
    for idx, original in enumerate(fences):
        text=text.replace(f'ARCHIVEFENCETOKEN{idx:06d}END',original.strip('\n'))
    # Trim only excessive blank lines. Do not normalize TeX or code bodies.
    text=re.sub(r'\n[ \t]*\n(?:[ \t]*\n){2,}', '\n\n', text)
    return text.strip()+'\n'


def render_markdown_fallback(raw: str):
    """Convert DIL source to a safe HTML document fragment plus exact MD text."""
    from archive_render_v7 import render_markdown_v7
    md=markdownize_dil(raw)
    return render_markdown_v7(md), md

# --- v7.3.10: recovered links + bounded template expansion ------------------

def _normalize_source_url(value):
    from recovery_source_links import normalized_url
    value=normalized_url(value)
    # Old generated_files_report.csv occasionally included one extra closing
    # parenthesis (the Markdown link delimiter) in a source reference.
    while value.endswith(')') and value.count(')')>value.count('('):
        value=value[:-1]
    return value


def recovered_links_for_source(archive, filename):
    """Resolve only VERIFIED recovered assets belonging to the exact chat.

    A basename fallback is allowed *only* if that name uniquely identifies a
    recovered asset in the same chat, never on a global name match.
    """
    from pathlib import Path
    from archive_recovery import RecoveryManager, existing_asset, norm_name
    from urllib.parse import quote
    import re

    if not re.fullmatch(r'chat_\d{7}_[a-f0-9]{8}_ui_\d{4}\.txt',filename):
        return {},{}
    chat='chats/'+filename.split('_ui_',1)[0]+'.html'
    manager=RecoveryManager(archive)
    entries=[]
    for record in manager.registry().values():
        if not isinstance(record,dict):continue
        hrefs=record.get('hrefs') or [record.get('href','')]
        if chat not in hrefs:continue
        name=record.get('asset_name','')
        if not existing_asset(manager.assets,name):continue
        # Real local images/downloads are served from /chats/../assets.
        info={'url':'../assets/'+quote(name,safe=''),
              'name':str(record.get('name') or name)}
        entries.append((record,info))
    urls={};names={}
    for rec,info in entries:
        for src in rec.get('refs',[]):
            if not isinstance(src,str) or not src.startswith(('sandbox:','file-service:','sediment:')):
                continue
            key=_normalize_source_url(src)
            urls.setdefault(key,[]).append(info)
        # Only exact names, never fuzzy matching: ambiguous duplicates unresolved.
        for name in (rec.get('name'),):
            if name:names.setdefault(norm_name(name),[]).append(info)
    def unique_map(mapping):
        result={}
        for key,candidates in mapping.items():
            by_url={info['url']:info for info in candidates}
            if len(by_url)==1:result[key]=next(iter(by_url.values()))
        return result
    return unique_map(urls),unique_map(names)


def _resolved_for_url(url,exact,names):
    from archive_recovery import norm_name
    key=_normalize_source_url(url)
    info=exact.get(key)
    if info:return info
    if key.startswith(('sandbox:','file-service:','sediment:')):
        return names.get(norm_name(key))
    return None


def _render_recovered_markdown(md_text,exact,names):
    """Original archive Markdown renderer, with role-preserving exact recovery.

    This override is used ONLY for this alternative reading view: the original
    converter and MathJax plugins are not changed.
    """
    import html as h
    from archive_render_v7 import (LocalHTMLRenderer, mistune, dollar_math,
        backslash_math, double_dollar_inline, _safe_link)

    class ReadingRenderer(LocalHTMLRenderer):
        def resolved(self,label,url,is_image):
            info=_resolved_for_url(url,exact,names)
            if not info:
                return _safe_link(url,None,label,is_image)
            target=h.escape(info['url'],quote=True)
            label_safe=h.escape(re.sub(r'<[^>]*>','',label).strip() or info['name'],quote=True)
            if is_image:
                return ('<a target="_blank" rel="noopener" href="'+target+'">'
                        '<img class="inline-img" loading="lazy" src="'+target+'" alt="'+label_safe+'"></a>')
            return '<a download href="'+target+'">📎 '+label+'</a>'
        def link(self,text,url,title=None):return self.resolved(text,url,False)
        def image(self,text,url,title=None):return self.resolved(text,url,True)

    renderer=mistune.create_markdown(renderer=ReadingRenderer(),plugins=[
        'table','strikethrough','task_lists','url',dollar_math,backslash_math,double_dollar_inline])
    try:return renderer(md_text.replace('\x00',''))
    except (ValueError,RuntimeError,RecursionError):
        return '<pre class="dil-parse-fallback"><code>'+h.escape(md_text)+'</code></pre>'


def _restore_rendered_link_warnings(html_result,raw,exact,names):
    """When enhanced ON DIL is rebuilt, restore recovered warning spans
    using the EXACT source Markdown link label and URL, never by guesswork.
    """
    from recovery_source_links import links_in_text, normalized_label
    import html as h
    links={}
    for source_url,label,is_image in links_in_text(raw):
        info=_resolved_for_url(source_url,exact,names)
        if info and label:links.setdefault(label,[]).append((info,is_image))
    accepted={}
    for label,found in links.items():
        variants={(i['url'],role) for i,role in found}
        if len(variants)==1:accepted[label]=found[0]
    pattern=re.compile(r'<span class="missing-file">⚠ ([\s\S]*?) \(нет локальной копии\)</span>')
    def replace(m):
        label=h.unescape(re.sub(r'<[^>]*>','',m.group(1)))
        entry=accepted.get(normalized_label(label))
        if not entry:return m.group(0)
        info,is_image=entry
        target=h.escape(info['url'],quote=True)
        safe_label=h.escape(label,quote=True)
        if is_image:
            return '<a target="_blank" rel="noopener" href="'+target+'"><img class="inline-img" loading="lazy" src="'+target+'" alt="'+safe_label+'"></a>'
        return '<a download href="'+target+'">📎 '+h.escape(label)+'</a>'
    return pattern.sub(replace,html_result)


def render_ui_variants(raw,archive,filename):
    """Returns (Markdown-HTML, Markdown source, optional enhanced ON-HTML).

    Returns enhanced ON HTML only if a supported static template was expanded.
    Otherwise original ON content is never touched.
    """
    from dil_template_safe import expand_template
    from archive_render_v7 import render_dil_v7
    expanded,changed=expand_template(raw)
    exact,names=recovered_links_for_source(archive,filename)
    md=markdownize_dil(expanded)
    md_html=_render_recovered_markdown(md,exact,names)
    enhanced=None
    if changed:
        # The legacy DIL parser splits a Markdown link when an inline <icon/>
        # appears INSIDE its label. Flatten only that decoration, never its
        # target URL or the distinction between images and download links.
        on_source=re.sub(r'\[\s*<icon\b[^>]*?/>\s*([^\]]+)\]\(',
                         lambda m: '['+m.group(1)+'](',expanded,flags=re.I)
        enhanced=render_dil_v7(on_source)
        enhanced=_restore_rendered_link_warnings(enhanced,on_source,exact,names)
    return md_html,md,enhanced
