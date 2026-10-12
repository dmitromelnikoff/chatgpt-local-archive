# -*- coding: utf-8 -*-
"""Bounded, declarative subset of DIL templates. NEVER evaluates JavaScript.

Supported: static literal arrays / object literals in {#each X as item,i},
{#if i<2}, {#else}, and property interpolation {item.t}, {i}.
Unknown expressions are preserved verbatim rather than misrendered.
"""
from __future__ import annotations
import ast
import html
import json
import re

DIRECTIVE = re.compile(
    r'\{#each\s+.*?\s+as\s+[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)?\s*\}'
    r'|\{#if\s+[^{}]{1,180}\}'
    r'|\{#else\s*\}|\{/if\s*\}|\{/each\s*\}', re.S)
EACH = re.compile(r'\{#each\s+(.*?)\s+as\s+([A-Za-z_]\w*)(?:\s*,\s*([A-Za-z_]\w*))?\s*\}',re.S)
IF = re.compile(r'\{#if\s+([^{}]{1,180})\}',re.S)
INTERPOLATION = re.compile(r'\{([a-zA-Z_]\w*(?:\.[A-Za-z_]\w*)*)\}')
FENCES = re.compile(r'(?ms)^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1\2[ \t]*(?:\n|$)')
MATH = re.compile(r'(?s)\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$')
MAX_DEPTH = 12
MAX_ITERATIONS = 100
MAX_OUTPUT = 800_000


def protect_source(raw):
    """Prevent template interpolation from changing code fences and TeX."""
    protected = []
    def hide(m):
        key = f'ARCHIVE_SAFE_TEMPLATE_HIDDEN_{len(protected):06d}_END'
        protected.append((key,m.group(0)))
        return key
    work=FENCES.sub(hide,raw)
    work=MATH.sub(hide,work)
    return work,protected


def _quote_object_keys(source):
    # Turn simple JS literals like [{t:"A",ic:"check"}] into strict JSON,
    # without modifying strings that contain colons or braces.
    result=[]
    i=0
    quote=None
    escaped=False
    while i<len(source):
        c=source[i]
        if quote:
            result.append(c)
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c==quote:quote=None
            i+=1;continue
        if c in ('"',"'"):
            # JSON only accepts double quotes; simple JS single string quotes.
            if c=="'":
                j=i+1; buf=[];esc=False
                while j<len(source):
                    x=source[j]
                    if esc:buf.append(x);esc=False
                    elif x=='\\':esc=True
                    elif x=="'":break
                    else:buf.append(x)
                    j+=1
                if j>=len(source):raise ValueError('Unclosed string')
                result.append(json.dumps(''.join(buf),ensure_ascii=False));i=j+1;continue
            quote=c;result.append(c);i+=1;continue
        if c in '{,':
            result.append(c);i+=1
            m=re.match(r'(\s*)([A-Za-z_]\w*)\s*:',source[i:])
            if m:
                result.append(m.group(1)+json.dumps(m.group(2))+':')
                i+=len(m.group(0))
            continue
        result.append(c);i+=1
    return ''.join(result)


def _literal(source):
    if len(source)>18_000:raise ValueError('Oversized expression')
    value=json.loads(_quote_object_keys(source))
    if not isinstance(value,list) or len(value)>MAX_ITERATIONS:
        raise ValueError('Only bounded static arrays are supported')
    if any(not isinstance(v,(str,int,float,bool,type(None),dict,list)) for v in value):
        raise ValueError('Not a static array')
    return value


def _name(expr,env):
    parts=expr.split('.')
    if parts[0] not in env:raise ValueError('Unknown interpolation')
    val=env[parts[0]]
    for k in parts[1:]:
        if not isinstance(val,dict) or k not in val:raise ValueError('Unknown property')
        val=val[k]
    return val


def _condition(expr,env):
    expr=expr.replace('===','==').replace('!==','!=').replace('&&',' and ').replace('||',' or ')
    tree=ast.parse(expr,mode='eval')
    def go(n):
        if isinstance(n,ast.Constant) and isinstance(n.value,(str,int,float,bool,type(None))):return n.value
        if isinstance(n,ast.Name):return _name(n.id,env)
        if isinstance(n,ast.Attribute):
            parts=[];cur=n
            while isinstance(cur,ast.Attribute):parts.append(cur.attr);cur=cur.value
            if not isinstance(cur,ast.Name):raise ValueError('Complex expression')
            return _name('.'.join([cur.id]+list(reversed(parts))),env)
        if isinstance(n,ast.BoolOp) and isinstance(n.op,(ast.And,ast.Or)):
            vals=[bool(go(v)) for v in n.values]
            return all(vals) if isinstance(n.op,ast.And) else any(vals)
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return not go(n.operand)
        if isinstance(n,ast.Compare) and len(n.ops)==1 and len(n.comparators)==1:
            left,right=go(n.left),go(n.comparators[0]);op=n.ops[0]
            if isinstance(op,ast.Lt):return left<right
            if isinstance(op,ast.LtE):return left<=right
            if isinstance(op,ast.Gt):return left>right
            if isinstance(op,ast.GtE):return left>=right
            if isinstance(op,ast.Eq):return left==right
            if isinstance(op,ast.NotEq):return left!=right
        raise ValueError('Expression not supported')
    return bool(go(tree.body))


def _replace_vars(raw,env):
    def sub(m):
        try:
            value=_name(m.group(1),env)
            if not isinstance(value,(str,int,float,bool)):return m.group(0)
            value=html.escape(str(value),quote=True)
            # If inside attribute name={item.ic}, make it a quoted HTML value.
            before=raw[max(0,m.start()-100):m.start()]
            if re.search(r'[\w-]+\s*=\s*$',before):return '"'+value+'"'
            return value
        except ValueError:return m.group(0)
    return INTERPOLATION.sub(sub,raw)


def _closing(raw,start):
    """Find the closing of a nested {#each}/{#if}; split optional #else."""
    depth=1;alt=None
    for m in DIRECTIVE.finditer(raw,start):
        token=m.group(0)
        if token.startswith(('{#each','{#if')):depth+=1
        elif token.startswith(('{/each','{/if')):
            depth-=1
            if depth==0:return m.start(),m.end(),alt
        elif token.startswith('{#else') and depth==1:alt=(m.start(),m.end())
    raise ValueError('Unclosed DIL template block')


def _expand(raw,env,depth,limit):
    if depth>MAX_DEPTH:raise ValueError('Too many nested template blocks')
    output=[];at=0
    for match in DIRECTIVE.finditer(raw):
        if match.start()<at:continue
        token=match.group(0)
        if not token.startswith(('{#each','{#if')):continue
        output.append(_replace_vars(raw[at:match.start()],env))
        try:
            end_start,end_end,alt=_closing(raw,match.end())
            if token.startswith('{#each'):
                m=EACH.fullmatch(token)
                if not m:raise ValueError('Unrecognized loop')
                collection=_literal(m.group(1));pieces=[]
                for idx,val in enumerate(collection):
                    inner=dict(env);inner[m.group(2)]=val
                    if m.group(3):inner[m.group(3)]=idx
                    pieces.append(_expand(raw[match.end():end_start],inner,depth+1,limit))
                rendered=''.join(pieces)
            else:
                m=IF.fullmatch(token)
                if not m:raise ValueError('Unrecognized condition')
                condition=_condition(m.group(1),env)
                if alt:
                    from_pos,to_pos=(match.end(),alt[0]) if condition else (alt[1],end_start)
                else:
                    from_pos,to_pos=(match.end(),end_start) if condition else (end_start,end_start)
                rendered=_expand(raw[from_pos:to_pos],env,depth+1,limit)
            output.append(rendered)
        except (ValueError,TypeError,IndexError,KeyError,RecursionError,json.JSONDecodeError):
            # Never execute or guess an unknown template; preserve its source.
            try: end_start,end_end,alt=_closing(raw,match.end())
            except ValueError:end_end=match.end()
            output.append(raw[match.start():end_end])
        at=end_end
        if sum(map(len,output))>limit:raise ValueError('Output size limit')
    output.append(_replace_vars(raw[at:],env))
    joined=''.join(output)
    if len(joined)>limit:raise ValueError('Output size limit')
    return joined


def expand_template(raw):
    """Return (expanded, changed); leave raw untouched if a limit is exceeded."""
    if len(raw)>MAX_OUTPUT:return raw,False
    if '{#each' not in raw and '{#if' not in raw:return raw,False
    try:
        work,hidden=protect_source(raw)
        out=_expand(work,{},0,MAX_OUTPUT)
        for key,source in hidden:out=out.replace(key,source)
        return out,out!=raw
    except (ValueError,TypeError,RecursionError):return raw,False
