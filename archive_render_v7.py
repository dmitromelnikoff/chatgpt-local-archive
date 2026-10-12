# -*- coding: utf-8 -*-
"""Безопасный локальный рендер Markdown + статического DIL/SVG.

Никакой eval/JSX runtime, внешних запросов или исполняемого HTML из экспорта.
Python 3.9+; движок Markdown Mistune включён в поставку (vendor/mistune).
"""
import html
import re
import hashlib
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

# Mistune использует динамическую загрузку плагинов из ``mistune.plugins``.
# Добавляем ТОЛЬКО локальную папку vendor (без pip или site-packages).
sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
import mistune
from mistune.plugins.math import math as dollar_math

IMAGE_EXTS = {'.png','.jpg','.jpeg','.webp','.gif','.avif','.bmp','.svg'}
DIL_RENDER_EVENTS = []


def _safe_link(raw, assets, text, is_image=False, shown=None):
    """Результат Markdown-ссылки или изображения с контролем схемы."""
    raw = html.unescape(str(raw).strip()).replace('\\ ', '%20')
    local = None
    if assets:
        local = assets.resolve(raw, missing=True)
        if not local and (raw.startswith(('sandbox:', 'file-service:', 'sediment:')) or
                          assets.is_chatgpt_file_url(raw)):
            local = assets.resolve(re.sub(r'<[^>]+>', '', text), missing=True)
    label = re.sub(r'<[^>]*>', '', text).strip() or 'Файл'
    if local:
        if shown is not None: shown.add(local)
        href = assets.local_href(local)
        if is_image or Path(local).suffix.lower() in IMAGE_EXTS:
            return ('<a href="' + html.escape(href, quote=True) + '" target="_blank" rel="noopener">'
                    '<img class="inline-img" loading="lazy" src="' + html.escape(href, quote=True) +
                    '" alt="' + html.escape(label, quote=True) + '"></a>')
        return '<a download href="' + html.escape(href, quote=True) + '">📎 ' + text + '</a>'
    internal = raw.startswith(('sandbox:', 'file-service:', 'sediment:')) or (assets and assets.is_chatgpt_file_url(raw))
    if internal:
        alternatives = assets.alternative_html(raw, label) if assets else ''
        if alternatives: return alternatives
        return '<span class="missing-file">⚠ ' + html.escape(label) + ' (нет локальной копии)</span>'
    if urlsplit(raw).scheme.lower() in ('http', 'https', 'mailto'):
        if is_image:
            return ('<span class="external-image">🖼 ' + html.escape(label) +
                    ' — внешняя иллюстрация: <a rel="noopener noreferrer" target="_blank" href="' +
                    html.escape(raw, quote=True) + '">ссылка</a></span>')
        return '<a rel="noopener noreferrer" target="_blank" href="' + html.escape(raw, quote=True) + '">' + text + '</a>'
    return '<span class="missing-file">Недоступная ссылка: ' + html.escape(label) + '</span>'


class LocalHTMLRenderer(mistune.HTMLRenderer):
    def __init__(self, assets=None, shown=None):
        super().__init__(escape=True)
        self.assets = assets
        self.shown = shown

    def link(self, text, url, title=None):
        return _safe_link(url, self.assets, text, False, self.shown)

    def image(self, text, url, title=None):
        return _safe_link(url, self.assets, text, True, self.shown)

    def table(self, text):
        return '<div class="table-wrap"><table>' + text + '</table></div>'


def backslash_math(md):
    r"""Поддержка оригинальных \[...\] и \(...\) без изменения fenced code."""
    def parse_display(block, match, state):
        state.append_token({'type': 'block_math', 'raw': match.group('v7_display')})
        return match.end() + (0 if match.group(0).endswith('\n') else 1)

    def parse_inline(inline, match, state):
        state.append_token({'type': 'inline_math', 'raw': match.group('v7_inline')})
        return match.end()

    md.block.register('math_bracket', r'^ {0,3}\\\[[ \t]*(?P<v7_display>[\s\S]*?)[ \t]*\\\][ \t]*(?:\n|$)', parse_display, before='list')
    md.inline.register('math_parens', r'\\\((?P<v7_inline>[\s\S]+?)\\\)', parse_inline, before='escape')
    if md.renderer and md.renderer.NAME == 'html':
        from mistune.plugins.math import render_block_math, render_inline_math
        md.renderer.register('block_math', render_block_math)
        md.renderer.register('inline_math', render_inline_math)


def double_dollar_inline(md):
    """Отдельные формулы $$...$$ даже в однострочном Markdown."""
    from mistune.util import escape as escape_text
    def parse(inline, match, state):
        state.append_token({'type':'inline_display_math','raw':match.group('display_tex')})
        return match.end()
    md.inline.register('inline_display_math', r'\$\$(?P<display_tex>[\s\S]+?)\$\$', parse, before='inline_math')
    if md.renderer and md.renderer.NAME=='html':
        md.renderer.register('inline_display_math', lambda ren, tex:
            '<span class="math math-display">\\['+escape_text(tex)+'\\]</span>')


def render_markdown_v7(value, assets=None, shown=None):
    """Markdown без raw HTML. Все математические сегменты остаются для локального MathJax."""
    md = mistune.create_markdown(renderer=LocalHTMLRenderer(assets, shown),
                                  plugins=['table', 'strikethrough', 'task_lists', 'url', dollar_math, backslash_math, double_dollar_inline])
    try:
        return md(str(value).replace('\x00',''))
    except (ValueError, RuntimeError, RecursionError):
        return '<pre class="dil-parse-fallback"><code>' + html.escape(str(value)) + '</code></pre>'


CSS_TOKENS = {
    'surface': '#ffffff', 'surface-primary': '#ffffff', 'surface-secondary': '#e1e4e8',
    'surface-tertiary': '#e9edf1', 'subtle': '#94a3b8', 'primary':'#202123',
    'secondary':'#475569', 'tertiary':'#788294', 'success': '#16a34a',
    'border':'#d8dee5', 'muted':'#64748b', 'white':'#ffffff', 'black':'#000000',
}
SVG_ATTRS = {
    'x':'x','y':'y','x1':'x1','y1':'y1','x2':'x2','y2':'y2',
    'cx':'cx','cy':'cy','r':'r','rx':'rx','ry':'ry','width':'width','height':'height',
    'viewbox':'viewBox','preserveaspectratio':'preserveAspectRatio',
    'd':'d','points':'points','transform':'transform',
    'fill':'fill','stroke':'stroke','fillopacity':'fill-opacity',
    'strokeopacity':'stroke-opacity','strokewidth':'stroke-width',
    'strokelinecap':'stroke-linecap','strokelinejoin':'stroke-linejoin',
    'stroke-dasharray':'stroke-dasharray','opacity':'opacity',
    'fontweight':'font-weight','fontsize':'font-size','fontfamily':'font-family',
    'textanchor':'text-anchor','dominantbaseline':'dominant-baseline',
    'id':'id','offset':'offset','stopcolor':'stop-color','stopopacity':'stop-opacity',
}
SVG_TAGS = {'svg','g','rect','path','line','circle','ellipse','polyline','polygon',
            'text','tspan','defs','lineargradient','radialgradient','stop','clippath','title','desc'}
DIL_TAGS = {'box','row','column','columns','grid','stack','container','card','text',
            'caption','title','divider','icon','badge','grid-item','tag','button','list','listitem',
            'table','thead','tbody','tr','th','td','callout','blockquote','bold','strong','italic','em',
            'br','link','entity','cite','followup','image','asyncimage','asyncimagegroup',
            'codeblock','writingblock','appblock','progress','slider','stat','metric','chart',
            'tab','tabs','p','span','ul','ol','li'}
SKIP_TAGS = {'script','style','iframe','object','embed','foreignobject','video','audio',
             'form','input','textarea','select'}
VALID_DIM = re.compile(r'^\d+(?:\.\d+)?(?:px|%|em|rem|vh|vw)?$')
VALID_RGBA = re.compile(r'^rgba?\([\d., %]+\)$', re.I)
VALID_HEX = re.compile(r'^#[0-9a-fA-F]{3,8}$')
VALID_IDENT = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,70}$')
VALID_SVG_PATH = re.compile(r'^[MmLlHhVvCcSsQqTtAaZz0-9.eE, \t\r\n+\-]+$')
VALID_SVG_TRANSFORM = re.compile(r'^[\w\d .,()\-+]+$')


def _style_color(val):
    val = str(val or '').strip()
    if val in CSS_TOKENS: return CSS_TOKENS[val]
    if VALID_HEX.fullmatch(val) or VALID_RGBA.fullmatch(val): return val
    if val in ('currentColor','none','transparent','inherit'):
        return val
    # Небольшой явный список, чтобы нельзя было вставить css var/url() из архива.
    if val.lower() in ('red','green','blue','gray','grey','orange','purple','black','white'):
        return val.lower()
    return None


def _str_value(val):
    """Безопасное literal-значение из JSX props, выражения не выполняются."""
    if val is None: return ''
    s = str(val).strip()
    if re.fullmatch(r'\{\s*-?\d+(?:\.\d+)?\s*\}', s):
        return s[1:-1].strip()
    if re.fullmatch(r'\{\s*(?:true|false)\s*\}', s, re.I):
        return s[1:-1].strip().lower()
    if s.startswith('{') or s.startswith('${'):
        return ''
    return s


def _dimension(s):
    s = _str_value(s)
    if not s: return None
    if VALID_DIM.fullmatch(s):
        return s if re.search('[a-z%]', s, re.I) else (s+'px')
    if s == 'auto': return 'auto'
    return None


def _space(s):
    s = _str_value(s)
    if re.fullmatch(r'\d+(?:\.\d+)?', s):
        return f'{min(50, float(s)*4):g}px'
    return _dimension(s)


class DILTreeParser(HTMLParser):
    """Дерево, сохраняющее вложенность и SVG; не пытается выполнить JSX."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {'tag':'root','attrs':{},'children':[]}
        self.stack = [self.root]
        self.bad_nesting = 0
    def handle_starttag(self,tag,attrs):
        tag=tag.lower()
        attrs={str(k).lower():v for k,v in attrs if k}
        node={'tag':tag,'attrs':attrs,'children':[]}
        self.stack[-1]['children'].append(node)
        if tag not in {'br','hr','divider','icon','img','image','input','source','meta','link'}:
            self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        # For HTMLParser, self-closing e.g. <box .../> must pop explicitly.
        if self.stack[-1]['tag'] == tag.lower(): self.stack.pop()
    def handle_endtag(self,tag):
        tag=tag.lower()
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i]['tag']==tag:
                if i<len(self.stack)-1: self.bad_nesting+=1
                del self.stack[i:]
                return
    def handle_data(self,data):
        if data: self.stack[-1]['children'].append(data)


def _svg_attr(key, val):
    name = SVG_ATTRS.get(key)
    if not name: return None
    v = _str_value(val)
    if not v or len(v)>8192: return None
    if key in ('fill','stroke','stopcolor'):
        if v.startswith('url('):
            if not re.fullmatch(r'url\(#[a-zA-Z][\w-]{0,60}\)',v): return None
        elif not _style_color(v): return None
    elif key == 'd':
        if not VALID_SVG_PATH.fullmatch(v): return None
    elif key == 'transform':
        if not VALID_SVG_TRANSFORM.fullmatch(v): return None
    elif key == 'id':
        if not VALID_IDENT.fullmatch(v): return None
    elif key in ('fontfamily',):
        if not re.fullmatch(r'[a-zA-Z ,"\-]{1,75}',v): return None
    elif not re.fullmatch(r'[a-zA-Z0-9.,: %\-+_()]+',v):
        return None
    return name+'="'+html.escape(v,quote=True)+'"'


def _generic_style(tag,attrs):
    chunks=[]
    if tag == 'grid-item':
        chunks += ['min-width:0','display:block']
    elif tag in ('box','container','card','column','stack'):
        chunks += ['display:flex','flex-direction:column','min-width:0']
    elif tag == 'row':
        chunks += ['display:flex','flex-direction:row','align-items:flex-start','min-width:0']
    elif tag in ('grid','columns'):
        chunks += ['display:grid','grid-template-columns:repeat(2,minmax(0,1fr))','min-width:0']
    if tag == 'row' and _str_value(attrs.get('align')):
        x=_str_value(attrs.get('align')).lower()
        if x in ('start','center','end','stretch','baseline'):
            chunks.append('align-items:'+{'start':'flex-start','end':'flex-end'}.get(x,x))
    if 'justify' in attrs:
        j=_str_value(attrs['justify'])
        if j in ('start','end','center','between','around','evenly','space-between','space-around','space-evenly'):
            chunks.append('justify-content:'+{'start':'flex-start','end':'flex-end','between':'space-between','around':'space-around','evenly':'space-evenly'}.get(j,j))
    if 'wrap' in attrs and _str_value(attrs.get('wrap')).lower()!='false': chunks.append('flex-wrap:wrap')
    if 'gap' in attrs and _space(attrs['gap']): chunks.append('gap:'+_space(attrs['gap']))
    for key in ('padding','paddingx','paddingy','margin','marginx','marginy'):
        if key in attrs:
            val=_space(attrs[key])
            if val:
                prop={'paddingx':'padding-inline','paddingy':'padding-block',
                      'marginx':'margin-inline','marginy':'margin-block'}.get(key,key)
                chunks.append(prop+':'+val)
    for key in ('width','height','minwidth','maxwidth','minheight','maxheight'):
        if key in attrs:
            val = _dimension(attrs[key])
            if val:
                prop={'minwidth':'min-width','maxwidth':'max-width','minheight':'min-height','maxheight':'max-height'}.get(key,key)
                chunks.append(prop+':'+val)
    if 'alignself' in attrs:
        v=_str_value(attrs['alignself'])
        if v in ('start','end','center','stretch','baseline'):
            chunks.append('align-self:'+{'start':'flex-start','end':'flex-end'}.get(v,v))
    if 'flex' in attrs:
        s=_str_value(attrs['flex'])
        if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',s): chunks.append(f'flex:{s} 1 0%')
        elif s=='none': chunks.append('flex:none')
    if tag in ('grid','columns'):
        count=_str_value(attrs.get('columns') or attrs.get('cols') or attrs.get('count'))
        if count.isdigit() and 1 <= int(count) <= 6:
            chunks.append('grid-template-columns:repeat('+count+',minmax(0,1fr))')
    if 'background' in attrs:
        val=_style_color(_str_value(attrs['background']))
        if val: chunks.append('background:'+val)
    if 'color' in attrs:
        val=_style_color(_str_value(attrs['color']))
        if val: chunks.append('color:'+val)
    if 'radius' in attrs:
        r=_str_value(attrs['radius'])
        val={'xs':'3px','sm':'6px','md':'8px','lg':'12px','xl':'16px','full':'9999px'}.get(r,_dimension(r))
        if val:chunks.append('border-radius:'+val)
    if 'border' in attrs and _str_value(attrs.get('border'))!='false':
        chunks.append('border:1px solid #dee3e7')
    if 'clip' in attrs and _str_value(attrs.get('clip'))!='false':
        chunks.append('overflow:hidden')
    if 'size' in attrs and tag in ('text','caption','title'):
        val={'xs':'12px','sm':'13px','md':'15px','lg':'18px','xl':'23px','2xl':'28px'}.get(_str_value(attrs['size']))
        if val: chunks.append('font-size:'+val)
    if 'weight' in attrs:
        val={'medium':'500','semibold':'600','bold':'700','normal':'400','light':'300'}.get(_str_value(attrs['weight']))
        if val: chunks.append('font-weight:'+val)
    if 'linethrough' in attrs and _str_value(attrs.get('linethrough'))!='false':
        chunks.append('text-decoration:line-through')
    if 'tabularnums' in attrs and _str_value(attrs.get('tabularnums'))!='false':
        chunks.append('font-variant-numeric:tabular-nums')
    if tag in ('text','caption','title') and 'align' in attrs:
        val = _str_value(attrs['align'])
        if val in ('left','right','center','justify'):
            chunks.append('text-align:'+val)
    return ';'.join(chunks)


class DILRichRenderer:
    ICONS={'git-branch':'⑂','check':'✓','check-circle':'✓','alert-triangle':'⚠',
           'info':'ⓘ','file':'📄','image':'🖼','arrow-right':'→','clock':'◷','folder':'📁'}
    def __init__(self,assets=None,shown=None):
        self.assets=assets; self.shown=shown; self.stats={'svg':0,'layout':0,'unknown':0,'blocked':0}

    def render(self,raw):
        fences=[]
        pat = re.compile(r'(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1\s*$')
        def protect(m):
            fences.append(m.group())
            return '<v7fence index="'+str(len(fences)-1)+'"/>'
        work=pat.sub(protect,raw)
        parser=DILTreeParser()
        parser.feed(work);parser.close()
        self.stats['bad_nesting']=parser.bad_nesting
        return ''.join(render_markdown_v7(x,self.assets,self.shown) if isinstance(x,str) and x.strip()
                       else self.node(x,False,fences) for x in parser.root['children'])

    def node(self,node,inside_svg=False,fences=None):
        if isinstance(node,str):
            if not node.strip(): return '' if not inside_svg else html.escape(node)
            if inside_svg: return html.escape(node)
            # Whitespace is significant between adjacent <text> nodes. HTMLParser already
            # gives safe text chunks; dropping their leading/trailing spaces glued labels.
            value=node
            if re.search(r'(?:\*\*|~~|\]\(|\\\(|\\\[|\[[^\]]+\]\(https?://)',value):
                rendered=render_markdown_v7(value,self.assets,self.shown).strip()
                if rendered.startswith('<p>') and rendered.endswith('</p>') and rendered.count('<p>')==1:
                    rendered=rendered[3:-4]
                return rendered
            return html.escape(value)
        tag=node['tag']; attrs=node['attrs']; ch=node['children']
        if tag=='v7fence':
            try: return render_markdown_v7(fences[int(_str_value(attrs.get('index','-1')))],self.assets,self.shown)
            except (TypeError,ValueError,IndexError):return ''
        if tag in SKIP_TAGS:
            self.stats['blocked']+=1;return ''
        if inside_svg or tag=='svg':
            if tag not in SVG_TAGS:
                self.stats['blocked']+=1;return ''
            if tag=='svg':self.stats['svg']+=1
            attrlist=[]
            for k,v in attrs.items():
                attr=_svg_attr(k,v)
                if attr:attrlist.append(attr)
            if tag=='svg':
                attrlist.extend(['class="dil-v7-svg"','role="img"','xmlns="http://www.w3.org/2000/svg"'])
            tag_html = {'lineargradient':'linearGradient','radialgradient':'radialGradient',
                        'clippath':'clipPath'}.get(tag,tag)
            body=''.join(self.node(child,True,fences) for child in ch)
            return '<'+tag_html+(' '+' '.join(attrlist) if attrlist else '')+'>'+body+'</'+tag_html+'>'
        if tag=='codeblock':
            content=''.join(str(x) if isinstance(x,str) else '' for x in ch)
            return '<pre class="dil-v7-code"><code>'+html.escape(content)+'</code></pre>'
        if tag in ('divider','hr'):return '<hr class="dil-v7-divider">'
        if tag=='br':return '<br>'
        if tag=='icon':
            name=_str_value(attrs.get('name'))
            return '<span class="dil-v7-icon" title="'+html.escape(name,quote=True)+'">'+html.escape(self.ICONS.get(name,'◆'))+'</span>'
        if tag in ('img','image','asyncimage'):
            src=_str_value(attrs.get('src') or attrs.get('url') or attrs.get('asset_pointer'))
            return _safe_link(src,self.assets,html.escape(_str_value(attrs.get('alt')) or 'Изображение'),True,self.shown) if src else '<span>🖼 Изображение (без локального адреса)</span>'
        if tag=='link':
            url=_str_value(attrs.get('url'))
            label=html.escape(_str_value(attrs.get('title') or attrs.get('value')) or 'Ссылка')
            return _safe_link(url,self.assets,label,False,self.shown) if url else label
        if tag in ('entity','cite','followup'):
            return '<span class="dil-v7-badge">'+html.escape(_str_value(attrs.get('value') or attrs.get('title')) or tag)+'</span>'
        if tag not in DIL_TAGS:
            self.stats['unknown']+=1
            # Не отображаем опасные неизвестные элементы; текстовые потомки остаются доступными.
            return '<span class="dil-v7-unknown">'+''.join(self.node(x,False,fences) for x in ch)+'</span>'
        self.stats['layout']+=1
        alias={'box':'div','row':'div','column':'div','columns':'div','grid':'div','stack':'div',
               'container':'div','card':'div','grid-item':'div','text':'span','caption':'div','title':'h3',
               'badge':'span','tag':'span','button':'span','list':'ul','listitem':'li',
               'callout':'blockquote','writingblock':'section','codeblock':'pre',
               'appblock':'section','stat':'div','metric':'div','chart':'div',
               'slider':'span','progress':'span','tab':'div','tabs':'div',
               'bold':'strong','italic':'em'}.get(tag,tag)
        if alias not in {'div','span','h3','ul','li','blockquote','section','pre','strong','em',
                         'table','thead','tbody','tr','th','td','p','ol'}:
            alias='div'
        classes=['dil-v7-'+('box' if tag in ('box','card','container') else tag)]
        if tag in ('badge','button','tag'):classes.append('dil-v7-pill')
        styles=_generic_style(tag,attrs)
        at=' class="'+ ' '.join(classes)+'"'
        if styles:at+=' style="'+html.escape(styles,quote=True)+'"'
        body=''.join(self.node(x,False,fences) for x in ch)
        if tag=='appblock':body='<small>Интерактивная часть недоступна офлайн.</small>'+body
        return '<'+alias+at+'>'+body+'</'+alias+'>'


def render_dil_v7(raw, assets=None, shown=None, chat_id='', message_ids=()):
    renderer=DILRichRenderer(assets, shown)
    try:
        content=renderer.render(str(raw))
        if not content.strip():raise ValueError('DIL-разметка не дала видимого содержимого')
        status='svg' if renderer.stats['svg'] else ('layout' if renderer.stats['layout'] else 'fallback')
    except Exception as exc:
        content='<div class="dil-v7-error">Невозможно статически отобразить этот блок. См. исходник ниже.</div>'
        status='fallback'
        renderer.stats['error']=str(exc)[:250]
    DIL_RENDER_EVENTS.append({'chat_id':chat_id,'message_id':','.join(message_ids),
              'source_sha256':hashlib.sha256(str(raw).encode('utf-8','replace')).hexdigest()[:16],
              'render_mode':status,'svg_count':renderer.stats['svg'],'layout_nodes':renderer.stats['layout'],
              'unknown_nodes':renderer.stats['unknown'],'blocked_nodes':renderer.stats['blocked'],
              'bad_nesting':renderer.stats.get('bad_nesting',0),'error':renderer.stats.get('error','')})
    return content

DIL_V7_CSS = r'''
.dil-v7-box{max-width:100%;}
.dil-v7-row{min-width:0;column-gap:10px;}.dil-v7-row>.dil-v7-text{flex-shrink:0;}.dil-v7-grid,.dil-v7-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}.dil-v7-grid>.dil-v7-box{min-width:0;}
.dil-v7-column,.dil-v7-stack{min-width:0;}

.dil-v7-text{display:inline-block;min-width:0;}
.dil-v7-caption{font-size:13px;color:#5d6776;}
.dil-v7-title{font-size:17px;}
.dil-v7-badge,.dil-v7-pill{background:#e9f1f0;padding:3px 8px;border-radius:6px;font-size:12px;}
.dil-v7-icon{display:inline-flex;align-items:center;}
.dil-v7-divider{border:0;border-top:1px solid #e0e5e9;margin:8px 0;}
.dil-v7-svg{width:100%;max-width:100%;height:auto;display:block;overflow:visible;}
.dil-v7-unknown{white-space:pre-wrap}
.dil-v7-error{background:#fff4e7;border:1px solid #f0d4b1;padding:9px;border-radius:7px;}
.math{max-width:100%;overflow-x:auto;overflow-y:hidden;}
mjx-container[jax="SVG"]{max-width:100%;overflow-x:auto;overflow-y:hidden;}
'''
