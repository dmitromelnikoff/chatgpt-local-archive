#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover exact original Markdown link labels for an existing HTML chat.

The generated HTML can lose the target URL when replacing a missing sandbox
image/link by a human-readable warning. Never guess which file a descriptive
warning referred to when an assistant answer mentioned several outputs.

This module reads only the relevant original conversation shard, then uses
(message timestamp, original source URL, Markdown label, Markdown image flag).
It never changes original JSON or previously restored bytes.
"""
from __future__ import annotations
import csv
import html
import json
import re
from pathlib import Path
from urllib.parse import unquote

# Markdown links inside plain text or text embedded in rich/DIL parts.
# Handles normal links and links with balanced round parentheses in URLs.
OPEN_LINK = re.compile(r'(!?)\[([^\]\r\n]{1,1000})\]\(', re.S)


def normalized_label(s):
    s = html.unescape(re.sub(r'<[^>]+>', '', str(s or '')))
    return ' '.join(s.strip().split()).casefold()


def normalized_url(s):
    return html.unescape(unquote(str(s or '').strip().strip('<>'))).replace('\\ ', ' ').replace('\\', '/')


def links_in_text(text):
    """Return (url, label, is_image) preserving the original Markdown role."""
    if not isinstance(text, str):
        return
    for m in OPEN_LINK.finditer(text):
        i = m.end()
        depth = 1
        while i < len(text):
            char = text[i]
            if char == '\\':
                i += 2
                continue
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0:
                    break
            elif char == '\n' and i - m.end() > 800:
                break
            i += 1
        if i >= len(text) or depth != 0:
            continue
        url = normalized_url(text[m.end():i])
        if url.startswith(('sandbox:', 'file-service:', 'sediment:')):
            yield url, normalized_label(m.group(2)), bool(m.group(1))


class _StreamingJSON:
    """Read the top-level array of conversations without json.load of a shard."""
    def __init__(self, file):
        self.file, self.buf, self.pos, self.eof = file, '', 0, False
        self.decoder = json.JSONDecoder()

    def more(self):
        if self.pos:
            self.buf = self.buf[self.pos:]
            self.pos = 0
        if self.eof:
            return False
        data = self.file.read(262144)
        if not data:
            self.eof = True
            return False
        self.buf += data
        return True

    def peek(self):
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if not self.more():
                return ''

    def pop(self, ch):
        if self.peek() != ch:
            raise ValueError('Unexpected JSON array structure')
        self.pos += 1

    def value(self):
        self.peek()
        while True:
            try:
                val, end = self.decoder.raw_decode(self.buf, self.pos)
            except json.JSONDecodeError:
                if not self.more():
                    raise ValueError('Invalid/truncated conversations JSON')
            else:
                self.pos = end
                return val

    def array(self):
        self.pop('[')
        if self.peek() == ']':
            self.pop(']')
            return
        while True:
            yield self.value()
            if self.peek() == ']':
                self.pop(']')
                return
            self.pop(',')

    def conversations(self):
        if self.peek() == '[':
            yield from self.array()
            return
        self.pop('{')
        while self.peek() != '}':
            key = self.value()
            self.pop(':')
            if key in ('conversations','items','data') and self.peek() == '[':
                yield from self.array()
            else:
                self.value()
            if self.peek() == '}':
                break
            self.pop(',')
        self.pop('}')


def _message_strings(message):
    content = (message or {}).get('content') or {}
    if not isinstance(content, dict):
        return
    parts = content.get('parts')
    if isinstance(parts, list):
        for p in parts:
            if isinstance(p, str):
                yield p
            elif isinstance(p, dict):
                for key in ('text', 'fallbackMarkdown', 'fallback_markdown'):
                    if isinstance(p.get(key), str):
                        yield p[key]
    for key in ('text', 'fallbackMarkdown', 'fallback_markdown'):
        if isinstance(content.get(key), str):
            yield content[key]


def get_source_link_roles(root, archive, report, pending):
    """Return {(href, normalized_label, url, timestamp): bool(is_image)}.

    `pending` maps chat-href to a list of registry entries needing stronger
    evidence. Links are admitted only when a label unambiguously refers to
    exactly ONE original URL in the SAME original assistant message.
    """
    root, archive = Path(root), Path(archive)
    if not pending:
        return {}

    ci = archive / 'conversations_index.csv'
    if not ci.is_file():
        return {}
    with ci.open('r', encoding='utf-8-sig', newline='') as fp:
        sample = fp.readline(); fp.seek(0)
        conv_rows = list(csv.DictReader(fp, delimiter=';' if ';' in sample else ','))
    locations = {}
    for row in conv_rows:
        href = row.get('html') or row.get('HTML чата') or ''
        if href not in pending:
            continue
        shard = Path(row.get('shard') or '').name
        cid = row.get('conversation_id') or ''
        if shard and cid and (root / shard).is_file():
            locations[href] = (shard, cid)
    if not locations:
        return {}

    requests = {}
    for row in report:
        href = row.get('HTML чата', '')
        if href not in locations:
            continue
        ref = normalized_url(row.get('Ссылка в JSON', ''))
        if not ref.startswith(('sandbox:', 'file-service:', 'sediment:')):
            continue
        timestamp = row.get('Дата сообщения (timestamp)', '')
        requests.setdefault(href, set()).add(timestamp)

    shard_groups = {}
    for href, (shard, cid) in locations.items():
        shard_groups.setdefault(shard, {}).setdefault(cid, []).append(href)

    found = {}
    for shard, wanted in shard_groups.items():
        try:
            with (root / shard).open('r', encoding='utf-8-sig') as fp:
                for conv in _StreamingJSON(fp).conversations():
                    if not isinstance(conv, dict):
                        continue
                    cid = str(conv.get('id') or conv.get('conversation_id') or '')
                    if cid not in wanted:
                        continue
                    for href in wanted.pop(cid):
                        for node in (conv.get('mapping') or {}).values():
                            if not isinstance(node, dict):
                                continue
                            message = node.get('message') or {}
                            if not isinstance(message, dict):
                                continue
                            timestamp = str(message.get('create_time') or '')
                            if timestamp not in requests.get(href, ()):
                                continue
                            collected = []
                            for s in _message_strings(message):
                                collected.extend(links_in_text(s))
                            if collected:
                                found.setdefault((href, timestamp), []).extend(collected)
                    if not wanted:
                        break
        except (OSError, ValueError, TypeError):
            # No unsafe fallback: leave unresolved warnings unchanged.
            continue

    # A descriptive label shared by different original source URLs in one
    # message is ambiguous even if one of the files was already restored.
    result = {}
    for (href, timestamp), links in found.items():
        url_by_label = {}
        for url, label, is_image in links:
            if not label:
                continue
            url_by_label.setdefault(label, set()).add(url)
        roles_by_label_url = {}
        for url, label, is_image in links:
            roles_by_label_url.setdefault((label, url), set()).add(is_image)
        for (label, url), roles in roles_by_label_url.items():
            if len(url_by_label.get(label, ())) == 1 and len(roles) == 1:
                result[(href, timestamp, url, label)] = next(iter(roles))
    return result


def labels_for_item(href, item, report, source_roles):
    """Return label->is_image from URLs present in the selected recovery row.

    If the same label maps to conflicting source roles across source records,
    reject it rather than overriding with whatever record happens to be last.
    """
    refs = {normalized_url(r) for r in (item.get('refs') or [])}
    proposals = {}
    for row in report:
        if row.get('HTML чата') != href:
            continue
        url = normalized_url(row.get('Ссылка в JSON', ''))
        if url not in refs:
            continue
        timestamp = row.get('Дата сообщения (timestamp)', '')
        for (h, ts, src_url, label), role in source_roles.items():
            if h == href and ts == timestamp and src_url == url:
                proposals.setdefault(label, set()).add(role)
    return {label: next(iter(roles)) for label, roles in proposals.items() if len(roles) == 1}
