#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ChatGPT Local Archive STABLE v7.3.16.1 (связь через виртуальные ID) -> локальный HTML-архив. Python 3.9+, только stdlib.

Поместите этот файл рядом с conversations-000.json ... conversations-018.json,
conversation_asset_file_names.json и файлами file-*/file_* (.dat или без расширения).
Запустите: python chatgpt_local_archive.py  (либо двойным щелчком).

Рабочая папка — папка со СКРИПТОМ, поэтому двойной щелчок тоже работает.
Папка результата: ChatGPT_Local_Archive; готовая точка входа: index.html.
"""

import csv
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, parse_qs
from html.parser import HTMLParser
from collections import defaultdict
from archive_render_v7 import render_markdown_v7, render_dil_v7, DIL_RENDER_EVENTS, DIL_V7_CSS

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "ChatGPT_Local_Archive"
ASSETS_DIR = DEST / "assets"
CHATS_DIR = DEST / "chats"
DIL_DIR = DEST / "dil_sources"  # полный исходник UI, отдельно от лёгких HTML
GENERATED_DIR = ROOT / "ChatGPT_Generated_Files"  # скачанные из Library файлы ассистента
MANIFEST = ROOT / "conversation_asset_file_names.json"
# Не ограничиваем экспорт жёстко 19 шардами: встречаются другие количества.
def find_shards():
    found = list(ROOT.glob("conversations-*.json"))
    found = [p for p in found if re.fullmatch(r"conversations-\d+\.json", p.name, re.I)]
    found.sort(key=lambda p: int(p.stem.split('-')[-1]))
    single = ROOT / "conversations.json"
    if single.exists() and not found:
        found.append(single)
    elif single.exists() and found:
        say("[!] Одновременно есть conversations.json и нумерованные части: используем только части, чтобы не создавать дубликаты")
    return found

READ_CHUNK = 256 * 1024

INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
RESERVED_WIN = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif", ".ico", ".svg"}
MEDIA_EXTS = IMAGE_EXTS | {".heic", ".heif", ".tif", ".tiff", ".svg", ".pdf", ".txt", ".csv", ".json", ".zip", ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".docx", ".xlsx", ".pptx"}
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])(?!file-service(?=://))file[-_][A-Za-z0-9_-]{5,}(?:\.[A-Za-z0-9]{1,8})?", re.IGNORECASE)
POINTER_RE = re.compile(r"(?:file-service|sediment|asset)://[^\s\"'<>()[\]{}]+", re.IGNORECASE)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$")
BULLET_RE = re.compile(r"^\s{0,3}[-*+]\s+(.+)$")
NUMBER_RE = re.compile(r"^\s{0,3}\d+[.)]\s+(.+)$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+)$")
LINK_RE = re.compile(r"(!?)\[([^\]\n]+)\]\((<[^>]+>|(?:[^\s()]|\([^()\s]*\))+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
TABLE_DIVIDER_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def say(message):
    print(message, flush=True)


def safe_name(name, default="file.bin"):
    """Имя в Windows, без каталогов/устройств; достаточно короткое для путей."""
    result = INVALID_WIN.sub("_", str(name or "")).strip().rstrip(" .")
    if not result or result in {".", ".."}:
        result = default
    stem, suffix = os.path.splitext(result)
    suffix = suffix[:24]
    stem = stem[: max(1, 125 - len(suffix))]
    if stem.upper() in RESERVED_WIN:
        stem = "_" + stem
    return (stem + suffix).rstrip(" .") or default


def asset_key(value):
    """Сводим file-service://file-ABC, file-ABC.dat и file-ABC к одному ключу."""
    if not isinstance(value, str) or not value.strip():
        return ""
    value = unquote(value.strip()).replace("\\", "/")
    value = value.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    value = value.rsplit("/", 1)[-1]
    if value.lower().endswith(".dat"):
        value = value[:-4]
    # В новых пакетах один ID может называться file_XXX в JSON
    # и file-XXX.dat на диске. Нормализуем только специальный префикс.
    if value[:5].lower() in ("file-", "file_"):
        value = "file_" + value[5:]
    return value.casefold()


def quoted_url(filename):
    return quote(filename, safe="")


def first_nonempty(obj, keys):
    for key in keys:
        val = obj.get(key)
        if val is not None and val != "":
            return val
    return None


def extension_from_signature(source):
    """Определение формата по магическим байтам, не по ошибочному имени .dat."""
    try:
        with source.open("rb") as f:
            start = f.read(64)
    except OSError:
        return ""
    if start.startswith(b"\x89PNG\r\n\x1a\n"): return ".png"
    if start.startswith(b"\xff\xd8\xff"): return ".jpg"
    if start.startswith((b"GIF87a", b"GIF89a")): return ".gif"
    if start[:4] == b"RIFF" and start[8:12] == b"WEBP": return ".webp"
    if start.startswith(b"%PDF-"): return ".pdf"
    if start.startswith(b"BM"): return ".bmp"
    if len(start) >= 12 and start[4:8] == b"ftyp" and b"avif" in start[8:24]: return ".avif"
    if len(start) >= 12 and start[4:8] == b"ftyp" and b"heic" in start[8:24]: return ".heic"
    if start.startswith(b"PK\x03\x04"): return ".zip"
    if start.startswith(b"ID3") or start.startswith(b"\xff\xfb"): return ".mp3"
    if start.startswith(b"OggS"): return ".ogg"
    if start.startswith(b"RIFF") and start[8:12] == b"WAVE": return ".wav"
    if len(start) > 12 and start[4:8] == b"ftyp": return ".mp4"
    if start.startswith(b"\x1a\x45\xdf\xa3"): return ".webm"
    return ""


def filename_aliases(name):
    """Literal basename plus up to two URL-decoded variants. No directory traversal."""
    if not isinstance(name, str):
        return []
    first = html.unescape(name.strip().strip('\"\''))
    # URLs can carry encoded slashes: decode before extracting basename as well.
    variants = []
    seen = set()
    for original in (first, unquote(first), unquote(unquote(first))):
        base = original.replace('\\', '/').rsplit('/', 1)[-1].strip()
        if base and base.casefold() not in seen and base not in {'.', '..'}:
            variants.append(base)
            seen.add(base.casefold())
    return variants


def normalize_output_url(raw):
    """Снимает ВНЕШНЮЮ Markdown-разметку с ссылки, не меняя имя файла.

    Примеры:
    **[Файл](sandbox:/mnt/data/book.md)** -> sandbox:/mnt/data/book.md
    [...](sandbox:/mnt/data/chart-1(20261003).png) -> имя со скобками остаётся.

    Нельзя просто .rstrip(')*_'): это удалит значимые скобки в имени.
    Сначала удаляем суффикс форматирования, затем только НЕпарные ')'.
    """
    if not isinstance(raw, str):
        return ''
    value = html.unescape(raw.strip())
    for _ in range(32):
        before = value
        # Пунктуация вне ссылки; точки внутри расширения не затрагиваются.
        value = value.rstrip('.,;!?')
        # Markdown bold/italic/strike может идти сразу за ')'.
        if value.endswith(('**', '__', '~~')):
            value = value[:-2]
        elif value.endswith('*'):
            value = value[:-1]
        # Скобки в basename (например, chart-1(123).png) сохраняются.
        elif value.endswith(')') and value.count(')') > value.count('('):
            value = value[:-1]
        if value == before:
            break
    return value


def candidate_keys(text):
    """Ключи из ID, sandbox:/, file-service:// и URL загрузки файлов ChatGPT."""
    if not isinstance(text, str) or not text or len(text) > 20000:
        return []
    text = html.unescape(text.strip().strip('"\''))
    candidates = []
    def push(x):
        if x and isinstance(x, str):
            for name in filename_aliases(x):
                if name not in candidates:
                    candidates.append(name)
    parts = urlsplit(text)
    if parts.scheme in {"http", "https"}:
        query = parse_qs(parts.query)
        for name in ("id", "file_id", "fileId", "asset_id", "filename", "name"):
            for v in query.get(name, []): push(v)
        pathparts = [v for v in parts.path.split("/") if v]
        for v in pathparts[-3:]: push(v)
    elif parts.scheme in {"file-service", "sediment", "asset", "sandbox", "file"}:
        push(parts.path)
        push(parts.netloc)
    else:
        push(text.split("?", 1)[0].split("#", 1)[0])
    for match in TOKEN_RE.finditer(text): push(match.group(0))
    return candidates


class AssetStore:
    """Manifest + физические файлы; сохраняет ссылки на реальные локальные копии."""
    def __init__(self):
        self.by_id = {}                  # ТОЛЬКО ID вида file-... / file_...
        self.by_name = {}                # Только ОДНОЗНАЧНЫЕ отображаемые имена
        self.ambiguous_names = set()     # При коллизии не возвращать первый попавшийся
        self.by_title = {}
        self.by_chat_id = {}
        self.by_message_id = {}
        self.library_by_chat = defaultdict(list)
        self.library_by_message = defaultdict(list)
        self.library_all = []
        self.bindings = []
        self.summary_bindings = {'exact':0,'inferred':0,'synthesized':0,'unplaced':0,'manual':0,'missing':0}
        self.problems = []
        self.binding_overrides = {}
        override_path = ROOT / 'ChatGPT_Binding_Overrides.json'
        if override_path.is_file():
            try:
                data = json.loads(override_path.read_text(encoding='utf-8-sig'))
                if isinstance(data, dict):
                    self.binding_overrides = data
                else:
                    self.problems.append('Overrides должен быть JSON-словарём')
            except (OSError, ValueError) as exc:
                self.problems.append('Невозможно прочитать Overrides: ' + str(exc))
        self.chat_locations = {}  # файл -> (заголовок, HTML-чат, якорь)
        self.current_chat_id = ''
        self.current_message_ids = ()
        self.used_names = set()
        self.copied = self.missing = self.failed = self.reused = 0
        self.found_without_manifest = 0
        self.unresolved = set()
        self.sources = {}
        self.source_collisions = set()
        self.manual_by_name = {}
        self.manual_ambiguous = set()
        self.id_with_extension = {}
        self.id_extension_ambiguous = set()
        self.generated_references = {}
        self.library_audit = []
        self.source_evidence = {}         # filename -> точный ID / ручное уникальное имя
        self.missing_library_by_chat = defaultdict(list)
        self.missing_library_by_message = defaultdict(list)
        self.missing_library_by_title = defaultdict(list)
        self.asset_times = {}
        self.asset_chats = {}
        self.asset_sources = {}
        self.by_exact_source = {}
        self.weak_ids = set()              # ID, inferred from filename/size, not proven
        self.asset_name_index = defaultdict(set)
        self.hash_cache = {}
        self.assigned_existing_assets = set() # don't merge distinct file IDs even if bytes equal
        # Already-converted assets may outlive the .dat originals. Never delete them.
        if ASSETS_DIR.is_dir():
            for item in ASSETS_DIR.iterdir():
                if item.is_file():
                    self._register_asset(item.name)
                    self.used_names.add(item.name.casefold())

        # НЕ сканируем произвольные папки (старые бэкапы, тестовые архивы):
        # это была ещё одна причина ложных совпадений в v4.
        physical_files = [p for p in ROOT.iterdir() if p.is_file()]
        if GENERATED_DIR.is_dir():
            physical_files += [p for p in GENERATED_DIR.rglob('*') if p.is_file()]
        for f in physical_files:
            folded = f.name.casefold()
            if folded in self.sources and self.sources[folded] != f:
                self.source_collisions.add(folded)
            else:
                self.sources.setdefault(folded, f)
            stem = f.stem.casefold()
            if stem.startswith(('file-', 'file_')) and f.suffix.lower() in MEDIA_EXTS | {'.dat'}:
                if stem in self.id_with_extension and self.id_with_extension[stem] != f:
                    self.id_extension_ambiguous.add(stem)
                else:
                    self.id_with_extension.setdefault(stem, f)
            if GENERATED_DIR in f.parents:
                if folded in self.manual_by_name and self.manual_by_name[folded] != f:
                    self.manual_ambiguous.add(folded)
                else:
                    self.manual_by_name.setdefault(folded, f)
        say(f"Исходных физических файлов верхнего уровня и вручную скачанных: {len(physical_files)}")

    def _register_asset(self, name):
        if not name or not (ASSETS_DIR / name).is_file():
            return
        variants = filename_aliases(name)
        # v5/v6 suffix for conflicting original names (sha1 of ID).
        stem, ext = os.path.splitext(name)
        stripped = re.sub(r'_[0-9a-f]{10}(?:_\d+)?$', '', stem, flags=re.I)
        if stripped != stem:
            variants.extend(filename_aliases(stripped + ext))
        for variant in variants:
            self.asset_name_index[variant.casefold()].add(name)

    def _digest(self, name):
        if name not in self.hash_cache:
            try:
                h = hashlib.sha256()
                with (ASSETS_DIR / name).open('rb') as fh:
                    for block in iter(lambda: fh.read(1024 * 1024), b''):
                        h.update(block)
                self.hash_cache[name] = h.hexdigest()
            except OSError:
                self.hash_cache[name] = None
        return self.hash_cache[name]

    def alternatives(self, reference, desired=None, expected_size=None):
        """Possible LOCAL files. Never assert identity just from a matching name."""
        names = set()
        for term in (reference, desired):
            for candidate in candidate_keys(term) if isinstance(term, str) else ():
                for alias in filename_aliases(candidate):
                    names.update(self.asset_name_index.get(alias.casefold(), ()))
        names = {x for x in names if (ASSETS_DIR / x).is_file()}
        if isinstance(expected_size, int) and expected_size > 0:
            names = {x for x in names if (ASSETS_DIR / x).stat().st_size == expected_size}
        return sorted(names, key=lambda x: x.casefold())

    def _unique_equivalent(self, names):
        """Only treat duplicates as interchangeable if SHA-256 proves equal content."""
        if len(names) == 1: return names[0]
        if not names: return None
        sizes = {(ASSETS_DIR / x).stat().st_size for x in names}
        if len(sizes) != 1: return None
        digests = {self._digest(x) for x in names}
        if len(digests) == 1 and None not in digests:
            return names[0]
        return None

    def _asset_fallback(self, reference, desired=None, expected_size=None):
        matches = self.alternatives(reference, desired, expected_size)
        if not matches: return None
        # Prefer unique/byte-identical matches. Never choose among different versions.
        return self._unique_equivalent(matches)

    def alternative_html(self, reference, desired=None):
        possibilities = self.alternatives(reference, desired)
        if not possibilities: return ''
        links = []
        for name in possibilities[:12]:
            href = self.local_href(name)
            links.append('<a href="'+href+'" target="_blank" rel="noopener" download="'+
                         html.escape(name, quote=True)+'">'+html.escape(name)+'</a>')
        more = ' и ещё '+str(len(possibilities)-12) if len(possibilities)>12 else ''
        return ('<span class="candidate-files">⚠ '+
                ('В архиве есть файл с похожим именем, но связь с ID не доказана: '
                 if len(possibilities)==1 else 'В архиве несколько возможных версий: ')+
                ' · '.join(links)+html.escape(more)+'</span>')

    def _unique_name(self, desired, file_id):
        wanted = safe_name(desired)
        if wanted.casefold() not in self.used_names:
            self.used_names.add(wanted.casefold())
            return wanted
        stem, ext = os.path.splitext(wanted)
        digest = hashlib.sha1(str(file_id).encode("utf-8", "replace")).hexdigest()[:10]
        for n in range(1, 100000):
            addition = "_" + digest + ("_" + str(n) if n != 1 else "")
            candidate = safe_name(stem[: 125 - len(ext) - len(addition)] + addition + ext)
            if candidate.casefold() not in self.used_names:
                self.used_names.add(candidate.casefold())
                return candidate
        raise RuntimeError("Слишком много повторяющихся имен файлов")

    def _source(self, file_id):
        """ТОЛЬКО прямое совпадение файлового ID с именем физического файла.

        Никаких подстановок по stem/basename документов: README.md в разных
        чатах не является одним и тем же файлом.
        """
        for candidate in candidate_keys(str(file_id)):
            if not candidate.lower().startswith(('file-', 'file_')):
                continue
            variants = [candidate]
            if candidate[:5].lower() in ('file-', 'file_'):
                variants.append(('file_' if candidate[4] == '-' else 'file-') + candidate[5:])
            for variant in variants:
                for physical_name in (variant, variant + '.dat'):
                    key = physical_name.casefold()
                    src = self.sources.get(key)
                    if (src and key not in self.source_collisions and src.is_file()):
                        return src
                # Вручную скачанный файл можно переименовать в file_ID.pdf/.png и т.п.
                # По ID выбираем файл с расширением лишь при ОДНОЗНАЧНОМ совпадении.
                key = variant.casefold()
                if key not in self.id_extension_ambiguous:
                    src = self.id_with_extension.get(key)
                    if src and src.is_file(): return src
        return None

    def _manual_source(self, file_name):
        """Разрешаем имя ТОЛЬКО внутри ChatGPT_Generated_Files, если оно уникально."""
        if not isinstance(file_name, str) or not file_name:
            return None
        key = file_name.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        if key in self.manual_ambiguous:
            return None
        source = self.manual_by_name.get(key)
        return source if source and source.is_file() else None

    def _remember(self, key, output_name, aliases=()):
        for alias in (key, *aliases):
            if not isinstance(alias, str) or not alias:
                continue
            for candidate in candidate_keys(alias):
                if candidate[:5].lower() in ('file-', 'file_'):
                    self.by_id.setdefault(asset_key(candidate), output_name)
                else:
                    basename = candidate.casefold()
                    if basename in self.ambiguous_names:
                        continue
                    existing = self.by_name.get(basename)
                    if existing and existing != output_name:
                        self.by_name.pop(basename, None)
                        self.ambiguous_names.add(basename)
                    elif not existing:
                        self.by_name[basename] = output_name

    def _copy(self, source, desired, ref):
        source_identity = str(source.resolve()).casefold()
        if source_identity in self.by_exact_source:
            return self.by_exact_source[source_identity]
        # Reruns must NOT duplicate assets into name_hash_hash... copies. Reuse only
        # files whose contents match byte-for-byte, not merely names/size/mtime.
        try:
            src_size = source.stat().st_size
            existing = [name for name in self.alternatives(str(desired))
                        if name not in self.assigned_existing_assets and
                        (ASSETS_DIR / name).stat().st_size == src_size]
            # Prefer the deterministic suffix of THIS ID from previous builds.
            stem, ext = os.path.splitext(safe_name(str(desired)))
            preferred_suffix = '_'+hashlib.sha1(str(ref).encode('utf-8','replace')).hexdigest()[:10]
            existing.sort(key=lambda n: (0 if n.casefold()==safe_name(stem+preferred_suffix+ext).casefold()
                                         else 1 if n.casefold()==safe_name(str(desired)).casefold() else 2, n))
            if existing:
                sha = hashlib.sha256()
                with source.open('rb') as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b''):
                        sha.update(chunk)
                for name in existing:
                    if self._digest(name) == sha.hexdigest():
                        self.by_exact_source[source_identity] = name
                        self.assigned_existing_assets.add(name)
                        self._remember(ref, name, (source.name, source.stem, str(desired)))
                        self.reused += 1
                        return name
        except OSError:
            pass
        stem, ext = os.path.splitext(str(desired))
        if not ext or ext.lower() in {".dat", ".bin"}:
            guess = extension_from_signature(source)
            desired = (stem if ext.lower() in {".dat", ".bin"} else str(desired)) + (guess or ".bin")
        name = self._unique_name(desired, ref)
        target = ASSETS_DIR / name
        try:
            if not (target.is_file() and target.stat().st_size == source.stat().st_size and
                    abs(target.stat().st_mtime - source.stat().st_mtime) < 2):
                shutil.copy2(source, target)
        except OSError as exc:
            self.failed += 1
            if len(self.problems) < 200:
                self.problems.append(f"Не удалось скопировать {source.name}: {exc}")
            return None
        self.copied += 1
        self.assigned_existing_assets.add(name)
        self._register_asset(name)
        self.by_exact_source[source_identity] = name
        try:
            self.asset_sources[name] = source.stat().st_mtime
        except OSError:
            self.asset_sources[name] = 0
        self._remember(ref, name, (source.name, source.stem, desired))
        return name

    @staticmethod
    def _rows(payload):
        if isinstance(payload, list): return payload
        if isinstance(payload, dict):
            for key in ("assets", "files", "items", "data", "entries", "mapping"):
                if isinstance(payload.get(key), list): return payload[key]
            rows = []
            for k, v in payload.items():
                if isinstance(v, str):
                    # ФОРМАТ ОФИЦИАЛЬНОГО ЭКСПОРТА: {"file-xxxx.dat": "photo.png"}
                    rows.append({"file_id": k, "original_file_name": v})
                elif isinstance(v, dict):
                    row = dict(v)
                    row.setdefault("file_id", k)
                    rows.append(row)
            return rows
        return []

    def load_and_copy(self):
        files = [MANIFEST]
        for extra_name in ('library-files.json', 'library_files.json'):
            extra = ROOT / extra_name
            if extra.is_file(): files.append(extra)
        for manifest in files:
            if not manifest.is_file():
                say(f'[!] Нет манифеста: {manifest.name}')
                continue
            try:
                with manifest.open('r', encoding='utf-8-sig') as f:
                    records = self._rows(json.load(f))
            except (OSError, ValueError) as exc:
                self.problems.append(f'Ошибка JSON манифеста {manifest.name}: {exc}')
                continue
            is_library = manifest.name.lower() in {'library_files.json', 'library-files.json'}
            say(f'{manifest.name}: {len(records)} записей')
            for n, entry in enumerate(records, 1):
                if not isinstance(entry, dict): continue
                file_id = first_nonempty(entry, ('file_id','asset_id','fileId','fileIdInLibrary'))
                if not file_id and isinstance(entry.get('id'),str):
                    file_id = entry['id']
                file_name = first_nonempty(entry, ('original_file_name','original_filename',
                    'original_name','name','file_name','filename','display_name','title'))
                if not file_id and not file_name: continue
                file_id = str(file_id or file_name)
                key = asset_key(file_id)
                existing = self.by_id.get(key)
                source = self._source(file_id)
                method = 'точный ID исходного файла'
                check_size = 'не проверялся'
                expected_size = entry.get('file_size_bytes') if is_library else None
                if source is None and is_library:
                    source = self._manual_source(str(file_name or ''))
                    if source is not None:
                        method = 'по уникальному имени из ChatGPT_Generated_Files (проверить версию)'
                        # Одного имени недостаточно. Размер из Library — доп. критерий.
                        if isinstance(expected_size, int) and expected_size > 0:
                            if source.stat().st_size != expected_size:
                                check_size = f'НЕ СОВПАЛ: ожидалось {expected_size}, найдено {source.stat().st_size}'
                                source = None
                                method = 'ручной файл отклонён: размер отличается'
                            else:
                                check_size = 'размер совпадает (не криптографическая проверка)'
                if is_library and check_size == 'не проверялся':
                    compare = source or (ASSETS_DIR / existing if existing else None)
                    if compare is not None and compare.is_file() and isinstance(expected_size, int) and expected_size > 0:
                        actual_size = compare.stat().st_size
                        check_size = ('размер совпадает' if actual_size == expected_size else
                                      f'НЕ СОВПАЛ: ожидалось {expected_size}, найдено {actual_size}')
                if existing:
                    output_name = existing
                    self.reused += 1
                    method = self.source_evidence.get(output_name, 'сопоставленный ID')
                elif source is None and is_library:
                    # Existing assets can have a decoded name, while Library uses %20.
                    # This is evidence by filename + byte length, NOT a proof of file_id.
                    output_name = self._asset_fallback(str(file_name or ''), expected_size=expected_size)
                    if output_name:
                        method = 'восстановлен из assets по имени и размеру — ID НЕ подтверждён'
                        self.weak_ids.add(key)
                        self._remember(file_id, output_name, (str(file_name or ''),))
                        self.source_evidence.setdefault(output_name, method)
                        check_size = ('размер совпадает (ID не подтверждён)' if expected_size
                                      else 'только имя (ID не подтверждён)')
                    else:
                        self.missing += 1
                        if len(self.problems) < 200:
                            matches = self.alternatives(str(file_name or ''))
                            self.problems.append(('Неоднозначные варианты: ' if matches else 'Нет файла с ID ') +
                                                 f'{file_id} ({file_name})' +
                                                 (f': {len(matches)} возможных копий' if matches else ''))
                elif source is None:
                    output_name = None
                    self.missing += 1
                    if len(self.problems) < 200:
                        self.problems.append(f'Нет физического файла с ID {file_id} ({file_name})')
                else:
                    mime = str(first_nonempty(entry, ('mime_type','mime','content_type')) or '')
                    display = str(file_name or source.name)
                    if not os.path.splitext(display)[1] and mime:
                        ext = {'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp',
                               'application/pdf':'.pdf'}.get(mime.lower())
                        display += ext or (mimetypes.guess_extension(mime) or '')
                    output_name = self._copy(source, display, file_id)
                    if output_name: self.source_evidence[output_name] = method

                if is_library and not output_name:
                    absent = (file_id, str(file_name or file_id))
                    chat_id = entry.get('origination_thread_id') or entry.get('conversation_id')
                    msg_id = entry.get('origination_message_id')
                    if chat_id: self.missing_library_by_chat[str(chat_id)].append(absent)
                    if msg_id: self.missing_library_by_message[str(msg_id)].append(absent)
                    if entry.get('conversation_title'):
                        self.missing_library_by_title[str(entry['conversation_title'])].append(absent)
                if is_library:
                    library_entry = {
                        'file_id':file_id, 'file_name':str(file_name or file_id),
                        'local':output_name or '',
                        'chat_id':str(entry.get('origination_thread_id') or entry.get('conversation_id') or ''),
                        'message_id':str(entry.get('origination_message_id') or ''),
                        'generation_id':str(entry.get('image_gen_generation_id') or ''),
                        'kind':str(entry.get('library_artifact_type') or ''),
                        'state':str(entry.get('state') or ''),
                        'created':str(entry.get('created_at') or entry.get('file_upload_time') or ''),
                        'actor':str((entry.get('version_provenance') or {}).get('actor') or ''),
                        'file_size':entry.get('file_size_bytes'),
                        'method':method,
                    }
                    self.library_all.append(library_entry)
                    if library_entry['chat_id']:
                        self.library_by_chat[library_entry['chat_id']].append(library_entry)
                    if library_entry['message_id']:
                        self.library_by_message[library_entry['message_id']].append(library_entry)
                    self.library_audit.append({
                        'file_id':file_id, 'file_name':str(file_name or ''),
                        'state':str(entry.get('state') or ''),
                        'kind':str(entry.get('library_artifact_type') or ''),
                        'image_gen_id':str(entry.get('image_gen_generation_id') or ''),
                        'chat_id':str(entry.get('origination_thread_id') or ''),
                        'message_id':str(entry.get('origination_message_id') or ''),
                        'local':output_name or '', 'size_expected':expected_size or '',
                        'size_check':check_size,
                        'method':self.source_evidence.get(output_name, '') if output_name else method if method.startswith('ручной файл') else 'не найден по ID/ручному имени'})
                if not output_name: continue
                self._remember(file_id, output_name, (str(file_name or ''),))
                for ref_field in ('asset_pointer','download_url','file_url','url','source_id'):
                    alias = entry.get(ref_field)
                    if isinstance(alias, str): self._remember(alias, output_name)
                chat_id = first_nonempty(entry, ('conversation_id','chat_id','origination_thread_id','thread_id'))
                msg_id = entry.get('origination_message_id')
                title = first_nonempty(entry, ('conversation_title','chat_title','title'))
                if chat_id: self.by_chat_id.setdefault(str(chat_id), set()).add(output_name)
                if msg_id: self.by_message_id.setdefault(str(msg_id), set()).add(output_name)
                if title: self.by_title.setdefault(str(title), set()).add(output_name)
                if n % 500 == 0: say(f'  Обработано {n}/{len(records)}')
        say(f'Из манифестов: {self.copied} скопировано; {self.missing} записей без физического файла')

    def observe(self, names, timestamp, chat_title="", chat_href=""):
        """Связываем изображения с сообщениями для обратной хронологии галереи."""
        try:
            when = float(timestamp or 0)
        except (ValueError, TypeError):
            when = 0.0
        for name in names:
            if name and when >= self.asset_times.get(name, 0):
                self.asset_times[name] = when
                if chat_href:
                    self.asset_chats[name] = (chat_title, chat_href)

    def resolve(self, possible_id, desired=None, missing=False):
        if not isinstance(possible_id, str) or not possible_id or len(possible_id) > 20000:
            return None
        for candidate in candidate_keys(possible_id):
            is_id = candidate[:5].lower() in ('file-', 'file_')
            if is_id:
                mapped = self.by_id.get(asset_key(candidate))
            else:
                mapped = None
                if self.current_chat_id:
                    contenders = [r for r in self.library_by_chat.get(self.current_chat_id, ())
                                  if r.get('local') and r.get('file_name','').casefold() == candidate.casefold()]
                    if len(contenders) > 1:
                        limited = [r for r in contenders
                                   if r.get('message_id') in self.current_message_ids]
                        if len(limited) == 1: contenders = limited
                    distinct = {r['local'] for r in contenders}
                    if len(distinct) == 1: mapped = next(iter(distinct))
                    elif len(distinct) > 1: continue
                if not mapped:
                    mapped = None if candidate.casefold() in self.ambiguous_names else self.by_name.get(candidate.casefold())
            if mapped: return mapped
            # Восстанавливаем неизвестные манифесту файлы только по точному file_id.
            if is_id:
                source = self._source(candidate)
                if source:
                    result = self._copy(source, desired or source.name, candidate)
                    if result:
                        self.source_evidence[result] = 'точный ID, не указанный в манифестах'
                        self.found_without_manifest += 1
                        self._remember(candidate, result, (desired or '',))
                        return result
            # The files are present from a prior conversion in assets/ even if the
            # original .dat files have been moved/deleted. Resolve by filename only
            # when one candidate (or all candidates have identical SHA-256 bytes).
            if not is_id:
                recovered = self._asset_fallback(candidate)
                if recovered:
                    self.source_evidence.setdefault(recovered, 'сохранённая копия assets по имени (проверить версию)')
                    return recovered
            # Файл без ID может быть отдельно скачан в ChatGPT_Generated_Files.
            # В v6.2 проверка ошибочно была под `elif is_id`: поэтому обычное
            # sandbox:/mnt/data/report.md НЕ находило вручную скачанный report.md.
            if not is_id and candidate.casefold() not in self.ambiguous_names:
                manual = self._manual_source(candidate)
                if manual:
                    result = self._copy(manual, desired or manual.name, candidate)
                    if result:
                        self.source_evidence[result] = 'уникальное имя в ChatGPT_Generated_Files (версия не подтверждена ID)'
                        self.found_without_manifest += 1
                        self._remember(candidate, result)
                        return result
        if missing and ('file-' in possible_id.lower() or 'file_' in possible_id.lower() or
                        possible_id.startswith(('sandbox:', 'file-service:', 'sediment:')) or
                        self.is_chatgpt_file_url(possible_id)):
            if len(self.unresolved) < 5000: self.unresolved.add(possible_id[:300])
        return None

    def reference_evidence(self, reference, local):
        for candidate in candidate_keys(reference):
            if candidate[:5].lower() in ('file-', 'file_') and self.by_id.get(asset_key(candidate)) == local:
                if asset_key(candidate) in self.weak_ids:
                    return 'возможная копия по имени и размеру; ID не подтверждён'
                return 'совпадение идентификатора'
        return 'совпадение имени (проверить соответствие ссылке)'

    @staticmethod
    def is_chatgpt_file_url(url):
        parts = urlsplit(str(url))
        host = (parts.hostname or "").lower()
        return host in {"chatgpt.com", "chat.openai.com", "files.oaiusercontent.com"} and (
            "file" in parts.path.lower() or "content" in parts.path.lower() or
            "asset" in parts.path.lower() or "file" in parts.query.lower())

    def local_href(self, filename):
        return "../assets/" + quoted_url(filename)

    def from_text(self, value):
        found = set()
        if not isinstance(value, str) or len(value) > 300000: return found
        match = self.resolve(value)
        if match: found.add(match)
        for m in TOKEN_RE.finditer(value):
            item = self.resolve(m.group(0), missing=True)
            if item: found.add(item)
        for m in POINTER_RE.finditer(value):
            item = self.resolve(m.group(0), missing=True)
            if item: found.add(item)
        # В Markdown могут быть абсолютные URL, в которых нет file-идентификатора.
        for m in re.finditer(r"(?:sandbox:/|https?://)[^\s<>\)\]\"']{5,}", value):
            u = m.group(0).rstrip(".,;!")
            if u.startswith("sandbox:") or self.is_chatgpt_file_url(u):
                item = self.resolve(u, missing=True)
                if item: found.add(item)
        return found

    def from_object(self, obj):
        found = set()
        stack, count = [obj], 0
        while stack and count < 35000:
            value = stack.pop()
            count += 1
            if isinstance(value, str):
                found.update(self.from_text(value))
            elif isinstance(value, dict):
                fid = first_nonempty(value, ("file_id", "asset_pointer", "download_url", "file_url", "image_url", "file_path", "asset_id"))
                if fid and isinstance(fid, str):
                    desired = first_nonempty(value, ("name", "filename", "file_name", "original_file_name"))
                    match = self.resolve(fid, str(desired) if desired else None, missing=True)
                    if match: found.add(match)
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
        return found

    def import_loose_images(self):
        """Дополнительный импорт изображений только из файлов с признаками ID."""
        for key, source in sorted(self.sources.items()):
            if key in self.source_collisions: continue
            if key.startswith(('file-', 'file_')) and (
                    source.suffix.lower() in IMAGE_EXTS or
                    (source.suffix.lower() in ('.dat','') and extension_from_signature(source) in IMAGE_EXTS)):
                self.resolve(source.name)
            elif GENERATED_DIR in source.parents and source.suffix.lower() in IMAGE_EXTS:
                # Вручную скачанное изображение без ссылки всё равно доступно в галерее.
                if source.name.casefold() not in self.manual_ambiguous:
                    self.resolve(source.name)

    def image_names(self):
        """Новейшее сообщение/чат -> начало; include earlier assets after rerun."""
        images = {p.name for p in ASSETS_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS}
        for name in images:
            if name not in self.asset_sources:
                try: self.asset_sources[name] = (ASSETS_DIR / name).stat().st_mtime
                except OSError: self.asset_sources[name] = 0
        return sorted(images, key=lambda n: (-(self.asset_times.get(n) or self.asset_sources.get(n, 0)), n.casefold()))


class StreamJSON:
    """Потоковое чтение верхнего JSON-массива без json.load(гигантского файла)."""
    def __init__(self, file):
        self.file = file
        self.buffer = ""
        self.pos = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def _more(self):
        # Освобождаем уже использованную часть буфера.
        if self.pos:
            self.buffer = self.buffer[self.pos:]
            self.pos = 0
        if self.eof:
            return False
        data = self.file.read(READ_CHUNK)
        if not data:
            self.eof = True
            return False
        self.buffer += data
        return True

    def peek(self):
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if not self._more():
                return ""

    def pop(self, expected):
        found = self.peek()
        if found != expected:
            raise ValueError(f"Ожидалось {expected!r}, получено {found!r}")
        self.pos += 1

    def value(self):
        self.peek()
        while True:
            try:
                result, end = self.decoder.raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError as exc:
                if not self._more():
                    raise ValueError(f"Некорректный или неполный JSON: {exc}") from exc
            else:
                self.pos = end
                return result

    def array(self):
        self.pop("[")
        if self.peek() == "]":
            self.pop("]")
            return
        while True:
            yield self.value()
            separator = self.peek()
            if separator == "]":
                self.pop("]")
                return
            self.pop(",")

    def conversations(self):
        start = self.peek()
        if start == "[":
            yield from self.array()
            return
        if start != "{":
            raise ValueError("Корень файла должен быть JSON-массивом или объектом")
        self.pop("{")
        if self.peek() == "}":
            self.pop("}")
            return
        found_array = False
        while True:
            key = self.value()
            if not isinstance(key, str):
                raise ValueError("Ожидалось строковое имя поля JSON")
            self.pop(":")
            if key in {"conversations", "items", "data"} and self.peek() == "[":
                yield from self.array()
                found_array = True
            else:
                self.value()  # Внешние метаданные, обычно небольшие.
            if self.peek() == "}":
                self.pop("}")
                break
            self.pop(",")
        if not found_array:
            raise ValueError("В объекте нет массива conversations/items/data")


def inline_markdown(value, assets=None, shown=None):
    """Экранирование HTML + локальные ссылки. Скрипты из экспорта не исполняются."""
    value = str(value).replace("\x00", "")
    placeholders = []
    if shown is None: shown = set()

    def hold(rendered):
        placeholders.append(rendered)
        return "\x00" + str(len(placeholders) - 1) + "\x00"

    value = INLINE_CODE_RE.sub(lambda m: hold("<code>" + html.escape(m.group(1)) + "</code>"), value)

    def make_link(match):
        is_image, label, raw_url = match.group(1), match.group(2), match.group(3)
        url = html.unescape(raw_url.strip("<>"))
        local = assets.resolve(url, missing=True) if assets else None
        if not local and assets and (url.startswith(("sandbox:", "file-service:", "sediment:")) or
                                     assets.is_chatgpt_file_url(url)):
            local = assets.resolve(label, missing=True)
        if local:
            shown.add(local)
            href = assets.local_href(local)
            if is_image or Path(local).suffix.lower() in IMAGE_EXTS:
                return hold('<a href="' + href + '" target="_blank" rel="noopener"><img class="inline-img" loading="lazy" src="' + href + '" alt="' + html.escape(label, quote=True) + '"></a>')
            return hold('<a download href="' + href + '">📎 ' + html.escape(label or local) + '</a>')
        if url.startswith(("sandbox:", "file-service:", "sediment:")) or (assets and assets.is_chatgpt_file_url(url)):
            options = assets.alternative_html(url, label) if assets else ''
            if options:
                return hold(options)
            return hold('<span class="missing-file" title="Локальный файл не найден">⚠ ' + html.escape(label or "Недоступный файл") + ' (локальный файл не найден)</span>')
        scheme = urlsplit(url).scheme.lower()
        if scheme not in {"http", "https", "mailto"}:
            return match.group(0)
        if is_image:
            # Внешний URL может быть недоступен без входа; не подгружаем из сети.
            return hold('<span class="external-image">🖼 ' + html.escape(label or "Внешнее изображение") + ' — <a href="' + html.escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer">оригинальная ссылка</a></span>')
        return hold('<a href="' + html.escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer">' + html.escape(label) + '</a>')

    value = LINK_RE.sub(make_link, value)
    value = html.escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"__(.+?)__", r"<strong>\1</strong>", value)
    value = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", value)
    value = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", value)
    value = re.sub(r"~~(.+?)~~", r"<del>\1</del>", value)
    return PLACEHOLDER_RE.sub(lambda m: placeholders[int(m.group(1))]
                               if int(m.group(1)) < len(placeholders) else "", value)


def markdown_to_html(text, assets=None, shown=None):
    """v7: полноценный локальный Markdown с MathJax-разметкой и ссылками на assets."""
    return render_markdown_v7(text, assets, shown)


def attachment_html(names):
    output = []
    for name in sorted(names, key=str.casefold):
        href = "../assets/" + quoted_url(name)
        display = html.escape(name)
        if Path(name).suffix.lower() in IMAGE_EXTS:
            output.append('<figure class="attachment"><a href="' + href + '" target="_blank">' +
                          '<img loading="lazy" src="' + href + '" alt="' +
                          html.escape(name, quote=True) + '"></a><figcaption>' +
                          display + '</figcaption></figure>')
        else:
            output.append('<div class="download">📎 <a download href="' + href + '">' +
                          'Скачать: ' + display + '</a></div>')
    return "\n".join(output)


class UIStrip(HTMLParser):
    """Безопасное извлечение простого текста из JSX/DIL-компонентов."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style"): self.skip += 1
        if self.skip: return
        attrs = dict(attrs)
        if tag.lower() in {"entity", "badge", "link", "followup", "button"}:
            value = attrs.get("value") or attrs.get("title")
            if value: self.chunks.append(" " + value + " ")
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "tr", "br"}:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style") and self.skip: self.skip -= 1
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "tr"} and not self.skip:
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self.skip: self.chunks.append(data)


def dil_to_markdown(raw):
    """Оставляет Markdown и fenced code, убирает только UI-теги без запуска JS."""
    segments = []
    lines = raw.splitlines(keepends=True)
    block, fence, size = [], None, 0
    text_lines = []
    def flush_text():
        if text_lines:
            parser = UIStrip()
            try:
                parser.feed("".join(text_lines))
                segments.append("".join(parser.chunks))
            except Exception:
                segments.append("".join(text_lines))
            text_lines.clear()
    for line in lines:
        match = FENCE_RE.match(line.rstrip("\r\n"))
        if fence:
            block.append(line)
            if match and match.group(1)[0] == fence and len(match.group(1)) >= size and not match.group(2).strip():
                segments.append("".join(block))
                block, fence = [], None
            continue
        if match:
            flush_text()
            fence, size = match.group(1)[0], len(match.group(1))
            block = [line]
        else:
            text_lines.append(line)
    flush_text()
    if block: segments.append("".join(block))
    return "\n".join(segments).strip()


DIL_TAG_RE = re.compile(
    r"</?(?:box|row|column|columns|divider|icon|grid|stack|title|text|caption|badge|button|"
    r"card|slider|progress|tabs|tab|table|datatable|chart|entity|cite|link|image|"
    r"asyncimage|asyncimagegroup|appblock|writingblock|codeblock|followup|"
    r"form|input|select|checkbox|toggle|spoiler|callout|list|listitem|"
    r"avatar|steps|step|stat|metric|tag|container|svg)\b", re.I)


def is_intelligent_ui(text):
    if not isinstance(text, str): return False
    # Сначала удаляем fenced code: код с JSX/DIL не является UI-ответом.
    without_code = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)
    return bool(DIL_TAG_RE.search(without_code) or re.search(r"\{@body\b|DIL\.useState\b|\{#(?:if|each)\b", without_code))



class DILStaticRenderer(HTMLParser):
    """Безопасный OFFLINE-рендерер часто встречающихся тегов DIL.

    Не выполняет JS, JSX-expressions, скрипты или сетевые запросы.
    Не претендует на воспроизведение интерактивного runtime ChatGPT.
    """
    ICONS = {
        "git-branch": "⑂", "check": "✓", "check-circle": "✓", "alert-triangle": "⚠",
        "info": "ⓘ", "file": "📄", "file-text": "📄", "image": "🖼", "download": "↓",
        "arrow-right": "→", "arrow-left": "←", "star": "★", "clock": "◷",
        "calendar": "▦", "search": "⌕", "folder": "📁", "link": "🔗", "code": "</>",
    }
    WRAPPERS = {
        "row": ('<div class="dil-row">', '</div>'),
        "box": ('<div class="dil-box">', '</div>'),
        "card": ('<div class="dil-box">', '</div>'),
        "column": ('<div class="dil-column">', '</div>'),
        "columns": ('<div class="dil-row">', '</div>'),
        "grid": ('<div class="dil-grid">', '</div>'),
        "stack": ('<div class="dil-stack">', '</div>'),
        "title": ('<h3 class="dil-title">', '</h3>'),
        "caption": ('<div class="dil-caption">', '</div>'),
        "text": ('<div class="dil-text">', '</div>'),
        "badge": ('<span class="dil-badge">', '</span>'),
        "button": ('<span class="dil-button">', '</span>'),
        "tag": ('<span class="dil-badge">', '</span>'),
        "list": ('<ul>', '</ul>'),
        "listitem": ('<li>', '</li>'),
        "bold": ('<strong>', '</strong>'),
        "strong": ('<strong>', '</strong>'),
        "italic": ('<em>', '</em>'),
        "em": ('<em>', '</em>'),
        "table": ('<div class="dil-box">', '</div>'),
        "tab": ('<div class="dil-box">', '</div>'),
        "tabs": ('<div class="dil-stack">', '</div>'),
        "callout": ('<blockquote>', '</blockquote>'),
        "blockquote": ('<blockquote>', '</blockquote>'),
        "writingblock": ('<div class="dil-box">', '</div>'),
        "codeblock": ('<pre class="dil-code">', '</pre>'),
        "appblock": ('<div class="dil-box"><p>Встроенное приложение ChatGPT. ' 
                     'Интерактивный режим офлайн недоступен; исходный код сохранён ниже.</p>', '</div>'),
    }

    def __init__(self, assets, shown):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.stack = []
        self.skip = 0
        self.assets = assets
        self.shown = shown

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip += 1
            return
        if self.skip:
            return
        attrs = dict(attrs)
        if tag in self.WRAPPERS:
            opening, closing = self.WRAPPERS[tag]
            self.output.append(opening)
            self.stack.append((tag, closing))
            return
        if tag == "divider" or tag == "hr":
            self.output.append('<hr class="dil-divider">')
        elif tag == "icon":
            label = attrs.get("name", "")
            self.output.append('<span class="dil-icon" title="' + html.escape(label, quote=True) + '">' +
                               html.escape(self.ICONS.get(label, "◆")) + '</span> ')
        elif tag in {"image", "asyncimage", "asyncimagegroup", "img"}:
            hint = attrs.get("src") or attrs.get("url") or attrs.get("asset_pointer") or ""
            image_name = self.assets.resolve(hint) if self.assets and hint else None
            if image_name and Path(image_name).suffix.lower() in IMAGE_EXTS:
                self.shown.add(image_name)
                url = self.assets.local_href(image_name)
                self.output.append('<figure class="attachment"><a href="' + url +
                                   '" target="_blank"><img loading="lazy" src="' + url +
                                   '" alt="Изображение"></a></figure>')
            else:
                label = attrs.get("query") or attrs.get("alt") or "Изображение в интерфейсе ChatGPT"
                self.output.append('<div class="dil-caption">🖼 ' + html.escape(label[:300]) +
                                   ' (файл изображения может отсутствовать в экспорте)</div>')
        elif tag in {"slider", "progress", "input", "toggle", "checkbox", "select"}:
            value = attrs.get("value") or attrs.get("defaultvalue")
            label = f"{tag}: {value}" if value is not None else f"{tag} (интерактивный элемент)"
            self.output.append('<span class="dil-badge">' + html.escape(label) + '</span>')
        elif tag in {"entity", "cite", "followup"}:
            label = attrs.get("value") or attrs.get("title") or attrs.get("name") or ""
            if label: self.output.append('<span class="dil-badge">' + html.escape(label) + '</span>')
        elif tag == "link":
            label = attrs.get("title") or attrs.get("value") or attrs.get("url") or "ссылка"
            url = attrs.get("url") or ""
            local = self.assets.resolve(url) if self.assets and url else None
            href = self.assets.local_href(local) if local else url
            if local: self.shown.add(local)
            if local or urlsplit(href).scheme in {"https", "http"}:
                self.output.append('<a href="' + html.escape(href, quote=True) +
                                   '" target="_blank" rel="noopener noreferrer">' + html.escape(label) + '</a>')
            else: self.output.append(html.escape(label))
        elif tag in {"br"}:
            self.output.append('<br>')

    def handle_startendtag(self, tag, attrs):
        # UI-компоненты без детей закрываются тут; не оставляем висячих тегов.
        tag = tag.lower()
        if tag in self.WRAPPERS:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            if self.skip: self.skip -= 1
            return
        if self.skip: return
        # Пропускаем осиротевшие закрывающие теги; закрываем корректную вложенность.
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                for _, closing in reversed(self.stack[i:]):
                    self.output.append(closing)
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        if self.skip or not data.strip(): return
        # Убираем исполняемые выражения DIL без выполнения.
        data = re.sub(r"(?m)^\s*\{@body[^\n]*\}\s*$", "", data)
        data = re.sub(r"\{[#/:](?:if|each|else)[^}]*\}", "", data)
        if not data.strip(): return
        if self.stack and self.stack[-1][0] == "codeblock":
            self.output.append(html.escape(data))
        elif self.stack and self.stack[-1][0] in {
                "title", "caption", "badge", "button", "tag", "bold", "strong", "italic", "em"}:
            self.output.append(inline_markdown(data.strip(), self.assets, self.shown))
        else:
            self.output.append(markdown_to_html(data.strip(), self.assets, self.shown))

    def finish(self):
        for _, closing in reversed(self.stack): self.output.append(closing)
        self.stack = []
        return '\n'.join(self.output)


def render_dil_static(raw, assets, shown):
    """v7: из DIL строится дерево, SVG и box/row превращаются в HTML/CSS."""
    return render_dil_v7(raw, assets, shown,
                         getattr(assets, 'current_chat_id', ''),
                         getattr(assets, 'current_message_ids', ()))


def fallback_text(message, content):
    """В некоторых версиях JSON отдельно сохраняется Markdown-fallback."""
    choices = []
    metadata = message.get("metadata") if isinstance(message, dict) else None
    if isinstance(metadata, dict):
        # КЛЮЧЕВОЕ: новый ChatGPT кладёт готовый Markdown именно сюда.
        compiled = metadata.get("model_dil_v2")
        if isinstance(compiled, dict):
            for field in ("fallbackMarkdown", "fallback_markdown", "markdownFallback"):
                val = compiled.get(field)
                if isinstance(val, str) and val.strip():
                    return val
    for source in (content, message, metadata):
        if not isinstance(source, dict): continue
        choices.extend(source.get(k) for k in ("markdown_fallback", "fallback_markdown", "fallback_text", "text_fallback", "plain_text", "rendered_text", "fallbackMarkdown") if k in source)
        for k in ("ui", "intelligent_ui", "dil", "rendered_content", "model_dil_v2"):
            nested = source.get(k)
            if isinstance(nested, dict):
                choices.extend(nested.get(z) for z in ("markdown_fallback", "fallback_markdown", "fallback_text", "fallbackMarkdown") if z in nested)
    for v in choices:
        if isinstance(v, str) and v.strip(): return v
    return None


def ui_source_html(raw, save_dil=None, heading="Исходная разметка Intelligent UI"):
    # Полная исходная разметка сохраняется в TXT, не утяжеляя HTML-диалог.
    source_link = ""
    if save_dil:
        relative = save_dil(raw)
        source_link = ('<p><a download href="' + html.escape(relative, quote=True) +
                       '">📄 Скачать ПОЛНУЮ исходную разметку этого UI-блока</a></p>')
    preview = raw[:3500]
    if len(raw) > 3500:
        preview += "\n… [предпросмотр сокращён, полная версия в TXT]"
    return ('<details class="ui-source"><summary>' + html.escape(heading) + '</summary>' +
            source_link + '<pre><code>' + html.escape(preview) + '</code></pre></details>')


def render_message(message, assets, save_dil=None, message_ids=()):
    content = message.get("content")
    parts = content.get("parts") if isinstance(content, dict) else content
    if not isinstance(parts, list): parts = [content] if content is not None else []
    rendered, shown = [], set()
    names = assets.from_object(content)
    # Library-вложения теперь распределяются по ролям/дереву сообщений
    # отдельно: простой origination_message_id часто указывает на ЗАПРОС
    # пользователя, даже когда изображение создал ассистент.
    metadata = message.get("metadata")
    if isinstance(metadata, dict):
        names.update(assets.from_object(metadata.get("attachments")))
        names.update(assets.from_object(metadata.get("image_gen")))
    preferred = fallback_text(message, content)
    if preferred:
        names.update(assets.from_text(preferred))
    has_compiled = isinstance(metadata, dict) and isinstance(metadata.get("model_dil_v2"), dict)
    # Для Rich DIL (SVG, диаграмм и вложенных layout-блоков) приоритет у графики.
    # FallbackMarkdown сохраняется в <details>, но не заменяет визуальную часть.
    rich_candidates = []
    for part in parts:
        raw = part if isinstance(part, str) else next((part.get(k) for k in ('raw_dil', 'dil', 'text')
                               if isinstance(part, dict) and isinstance(part.get(k), str)
                               and is_intelligent_ui(part[k])), None)
        if isinstance(raw, str) and is_intelligent_ui(raw):
            rich_candidates.append(raw)
    prefer_visual = bool(rich_candidates) and any(
        re.search(r'<svg\b|<row\b|<grid\b|<columns\b|<box\b[^>]*(?:width|height|background|border|flex|radius)', raw, re.I)
        for raw in rich_candidates)
    dynamic_source = bool(rich_candidates) and any(re.search(r'\{\s*(?:#(?:each|if|await)|@body|:else|/each|/if)\b|DIL\.use(?:State|Memo|Effect)\s*\(', raw) for raw in rich_candidates)
    if dynamic_source and preferred:
        rendered.append('<p class="ui-dynamic-note">Интерактивная часть показана в текстовом представлении. Динамические элементы могут отличаться от оригинала.</p>')
        rendered.append(markdown_to_html(preferred, assets, shown))
        for raw in rich_candidates:
            rendered.append(ui_source_html(raw, save_dil, 'Исходный динамический Intelligent UI'))
        parts = [part for part in parts if not ((isinstance(part,str) and is_intelligent_ui(part)) or
                 (isinstance(part,dict) and any(isinstance(part.get(k),str) and is_intelligent_ui(part[k])
                                                    for k in ('raw_dil','dil','text'))))]
    elif rich_candidates and prefer_visual:
        for raw in rich_candidates:
            rendered.append(render_dil_static(raw, assets, shown))
            rendered.append(ui_source_html(raw, save_dil))
        if preferred:
            rendered.append('<details class="ui-source"><summary>Текстовая версия Intelligent UI (fallbackMarkdown)</summary>' +
                            markdown_to_html(preferred, assets, shown) + '</details>')
        parts = [part for part in parts if not ((isinstance(part, str) and is_intelligent_ui(part)) or
                 (isinstance(part, dict) and any(isinstance(part.get(k),str) and is_intelligent_ui(part[k])
                                                    for k in ('raw_dil','dil','text'))))]
    elif preferred and (has_compiled or rich_candidates):
        rendered.append(markdown_to_html(preferred, assets, shown))
        for raw in rich_candidates:
            rendered.append(ui_source_html(raw, save_dil, 'Исходный Intelligent UI · техническая разметка'))
        parts = [part for part in parts if not ((isinstance(part,str) and is_intelligent_ui(part)) or
                 (isinstance(part,dict) and any(isinstance(part.get(k),str) and is_intelligent_ui(part[k])
                                                    for k in ('raw_dil','dil','text'))))]

    for part in parts:
        if isinstance(part, str):
            if not part.strip(): continue
            if is_intelligent_ui(part):
                rendered.append(render_dil_static(part, assets, shown))
                rendered.append(ui_source_html(part, save_dil))
            else:
                rendered.append(markdown_to_html(part, assets, shown))
        elif isinstance(part, dict):
            typ = str(part.get("content_type") or part.get("type") or "")
            pointer = first_nonempty(part, ("asset_pointer", "file_id", "file_url", "download_url", "image_url", "file_path", "asset_id", "id"))
            if isinstance(pointer, dict): pointer = pointer.get("url") or pointer.get("file_id")
            if isinstance(pointer, str):
                src = assets.resolve(pointer, first_nonempty(part, ("filename", "name", "file_name")), missing=True)
                if src:
                    names.add(src)
                    if ("image" in typ or "image" in str(part.get("mime_type", ""))) and Path(src).suffix.lower() in IMAGE_EXTS:
                        rendered.append(attachment_html({src})); shown.add(src)
            txt = []
            for k in ("text", "transcription", "caption", "description", "prompt", "raw_dil", "dil"):
                val = part.get(k)
                if isinstance(val, str) and val.strip() and val not in txt:
                    txt.append(val)
            if isinstance(part.get("code"), str):
                rendered.append('<pre><code>' + html.escape(part["code"]) + '</code></pre>')
            part_fallback = fallback_text(message, part)
            for v in txt:
                if is_intelligent_ui(v):
                    rendered.append(markdown_to_html(part_fallback, assets, shown) if part_fallback
                                    else render_dil_static(v, assets, shown))
                    rendered.append(ui_source_html(v, save_dil))
                else:
                    rendered.append(markdown_to_html(v, assets, shown))
            if not txt and not pointer and not assets.from_object(part):
                if typ not in {"image_asset_pointer", "audio", "video", "audio_uncond", "audio_perception",
                               "input_audio", "real_time_user_audio_video_asset_pointer"}:
                    brief = json.dumps(part, ensure_ascii=False, indent=2, default=str)
                    rendered.append('<details class="ui-source structure"><summary>Структурированная часть сообщения · JSON с переносами</summary>'
                                    '<pre><code>' + html.escape(brief[:50000]) +
                                    ('\n… [сокращено]' if len(brief) > 50000 else '') + '</code></pre></details>')
        elif part is not None:
            rendered.append('<p>' + html.escape(str(part)) + '</p>')
    if not rendered and preferred:
        rendered.append(markdown_to_html(preferred, assets, shown))
    refs = names | shown
    names.difference_update(shown)
    if names: rendered.append(attachment_html(names))
    return '\n'.join(rendered), refs



# Файлы, сформированные ассистентом, часто присутствуют только как sandbox-ссылки.
# Перечисляем ссылки отдельно, чтобы ни одна пропажа не маскировалась пользователем.
OUTPUT_LINK_RE = re.compile(
    r'(?:sandbox:/+|file-service://|sediment://|https?://(?:chatgpt\.com|chat\.openai\.com|files\.oaiusercontent\.com)/)'
    r'[^\s\"\'<>\[\]{}]+', re.I)


def output_references(message):
    """Находит ожидаемые созданные файлы в сообщении ассистента (не в цитатах кода)."""
    content = message.get('content') if isinstance(message, dict) else None
    metadata = message.get('metadata') if isinstance(message, dict) else None
    selections = [content]
    if isinstance(metadata, dict):
        selections += [metadata.get('attachments'), metadata.get('model_dil_v2'), metadata.get('files')]
    refs = {}
    stack = selections[:]
    visits = 0
    while stack and visits < 40000:
        value = stack.pop(); visits += 1
        if isinstance(value, str) and len(value) < 600000:
            # Не считаем примеры путей внутри fenced-code выданными файлами.
            outside_code = re.sub(r'(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1\s*$', '', value)
            for m in OUTPUT_LINK_RE.finditer(outside_code):
                url = normalize_output_url(m.group(0))
                # HTTP-ссылки на страницу чата и произвольные служебные API — не вложения.
                if urlsplit(url).scheme in ('http', 'https') and not AssetStore.is_chatgpt_file_url(url):
                    continue
                refs[url] = None
        elif isinstance(value, dict):
            direct = first_nonempty(value, ('download_url','file_url','asset_pointer','file_path','file_id'))
            if isinstance(direct, str) and (direct.startswith(('sandbox:', 'file-service:', 'sediment:'))
                                           or TOKEN_RE.fullmatch(direct)):
                refs[direct] = str(first_nonempty(value, ('name','filename','file_name','original_file_name')) or '')
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return refs


def record_output_files(message, assets, chat_title, chat_href, message_time):
    """Возвращает дополнительный HTML и накапливает проверяемые записи о выданных файлах."""
    refs = output_references(message)
    if not refs: return '', set(), []
    good, missing, ambiguous = set(), [], []
    for url, proposed_name in refs.items():
        local = assets.resolve(url, desired=proposed_name or None, missing=True)
        if local:
            good.add(local)
            status = 'найден'
            assets.observe((local,), message_time, chat_title, chat_href)
        else:
            choices = assets.alternatives(url, proposed_name)
            if choices:
                status = 'ЕСТЬ ЛОКАЛЬНЫЕ ВАРИАНТЫ — НЕ УСТАНОВЛЕНО СООТВЕТСТВИЕ'
                ambiguous.append((url, proposed_name))
            else:
                status = 'НЕТ В ЭКСПОРТЕ / ДОПОЛНИТЕЛЬНОЙ ПАПКЕ'
                missing.append((url, proposed_name))
        key = (chat_href, url)
        assets.generated_references[key] = {
            'chat': chat_title, 'href': chat_href, 'time': message_time,
            'reference': url, 'filename': proposed_name or (candidate_keys(url)[0] if candidate_keys(url) else ''),
            'status': status, 'local': local or '',
            'evidence': assets.reference_evidence(url, local) if local else '',
            'source_evidence': assets.source_evidence.get(local,'') if local else ''}
    elements = []
    # Если ссылка была текстом, а не Markdown-ссылкой, всё равно показываем скачивание.
    if good:
        elements.append('<details class="generated-output"><summary>📦 Файлы, созданные ChatGPT: ' +
                        str(len(good)) + ' (локальные копии)</summary>' + attachment_html(good) + '</details>')
    if ambiguous:
        elements.append('<details class="generated-output missing-output" open><summary>⚠ Найдены варианты файлов, нужна проверка: '+
                        str(len(ambiguous))+'</summary>' +
                        ''.join('<p>'+assets.alternative_html(u, label)+'</p>' for u,label in ambiguous[:100])+
                        '</details>')
    if missing:
        elements.append('<details class="generated-output missing-output"><summary>⚠ Не найдены файлы, созданные ChatGPT: ' +
                        str(len(missing)) + '</summary><p>Ссылка есть в истории, но физический файл не найден. '
                        'Если файл сохранился в Library, скачайте его в папку ChatGPT_Generated_Files и запустите конвертер повторно.</p><ul>' +
                        ''.join('<li><code>' + html.escape(label or ref[:220]) + '</code></li>'
                                for ref, label in missing[:100]) + '</ul></details>')
    return '\n'.join(elements), good, missing


def write_generated_report(assets):
    """CSV + читабельная HTML-страница для контроля выходных файлов."""
    entries = sorted(assets.generated_references.values(), key=lambda v: -(float(v['time'] or 0)))
    with (DEST / 'generated_files_report.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(('Статус', 'Чат', 'Дата сообщения (timestamp)', 'Имя файла', 'Ссылка в JSON', 'Локальный файл', 'HTML чата', 'Соответствие ссылки', 'Основание физического файла'))
        for item in entries:
            writer.writerow((item['status'], item['chat'], item['time'], item['filename'],
                             item['reference'], item['local'], item['href'],
                             item.get('evidence',''), item.get('source_evidence','')))
    found = sum(1 for x in entries if x['local'])
    missing = len(entries)-found
    page = DEST / 'generated_files.html'
    with page.open('w', encoding='utf-8') as f:
        f.write('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Файлы ChatGPT</title><style>body{font:14px system-ui,Arial,sans-serif;max-width:1000px;margin:28px auto;padding:0 16px;color:#202124}'
                'h1{font-size:25px}input{width:100%;padding:12px;border:1px solid #ccc;border-radius:9px;margin:10px 0}'
                'section{border:1px solid #ddd;padding:12px 15px;border-radius:8px;margin:10px 0;overflow-wrap:anywhere}'
                '.bad{border-left:5px solid #dc9445}.good{border-left:5px solid #10a37f}'
                'small{color:#666}code{font-size:12px;overflow-wrap:anywhere}a{color:#147a65}</style>'
                '<h1>📦 Выходные файлы ChatGPT</h1><p>Найдено: '+str(found)+' · Отсутствуют: '+str(missing)+'. '
                'Если файл отсутствует, попробуйте скачать его из ChatGPT Library в папку '
                '<code>ChatGPT_Generated_Files</code> рядом со скриптом, затем повторите запуск.</p>'
                '<p><a href="generated_files_report.csv" download>Скачать подробный отчёт CSV</a></p>'
                '<div id="items">')
        for item in entries:
            f.write('<section class="'+('good' if item['local'] else 'bad')+'"><b>'+('✓ Найден' if item['local'] else '⚠ Отсутствует')+'</b> · '
                    '<a href="'+html.escape(item['href'],quote=True)+'">'+html.escape(item['chat'])+'</a><div><code>'+
                    html.escape(item['filename'] or item['reference'][:300])+'</code></div>')
            if item['local']:
                f.write('<a download href="assets/'+quoted_url(item['local'])+'">↓ Скачать '+html.escape(item['local'])+'</a>')
            else:
                f.write('<small>'+html.escape(item['reference'][:500])+'</small>')
            f.write('</section>')
        f.write('</div></html>')
    return found, missing

def write_library_integrity_report(assets):
    with (DEST / 'library_integrity_report.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(('ID файла Library','Название','Состояние в Library','Тип Library',
                         'ID генерации изображения','ID чата','ID сообщения',
                         'Локальная копия','Метод идентификации','Размер в Library (байт)',
                         'Проверка размера','Проверка содержимого'))
        for row in assets.library_audit:
            writer.writerow((row['file_id'], row['file_name'], row['state'], row['kind'],
                             row['image_gen_id'], row['chat_id'], row['message_id'],
                             row['local'], row['method'], row['size_expected'], row['size_check'],
                             'НЕТ ФАЙЛА' if not row['local'] else 'Файл есть; содержимое не сверено по SHA-256'))


def ordered_nodes(conversation):
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        return [], []
    main_ids, seen = [], set()
    node_id = conversation.get("current_node")
    while node_id is not None and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        main_ids.append(node_id)
        node = mapping[node_id]
        node_id = node.get("parent") if isinstance(node, dict) else None
    main_ids.reverse()

    def sort_key(pair):
        node = pair[1] if isinstance(pair[1], dict) else {}
        message = node.get("message") or {}
        time = message.get("create_time") or node.get("create_time") or 0
        try:
            time = float(time)
        except (TypeError, ValueError):
            time = 0
        return time

    if main_ids:
        main = [mapping[x] for x in main_ids]
        extras = [v for k, v in sorted(mapping.items(), key=sort_key) if k not in seen]
    else:
        main = [v for _, v in sorted(mapping.items(), key=sort_key)]
        extras = []
    return main, extras



GENERATED_LIBRARY_TYPES = {'image_gen', 'writing_block', 'deep_research_report', 'sheet', 'report'}
GEN_ID_RE = re.compile(r'(?<![\w])s_[A-Za-z0-9]{12,}(?![\w])')


def is_generated_library_entry(entry, message_role=''):
    return bool(entry.get('generation_id') or entry.get('kind') in GENERATED_LIBRARY_TYPES
                or entry.get('actor') == 'agent' or message_role == 'assistant')


def readable_iso_timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0.0


def extract_message_refs(message):
    """Только ID из реального текста/метаданных; не угадываем по названию чата."""
    blobs, stack, visited = [], [message.get('content'), message.get('metadata')], 0
    while stack and visited < 35000:
        v = stack.pop(); visited += 1
        if isinstance(v, str):
            if v and len(v) < 400000: blobs.append(v)
        elif isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
    ids, gen_ids, names = set(), set(), set()
    for blob in blobs:
        ids.update(asset_key(m.group(0)) for m in TOKEN_RE.finditer(blob))
        gen_ids.update(m.group(0) for m in GEN_ID_RE.finditer(blob))
        # Имя из точного URL/ссылки; произвольные совпадения слов не учитываем.
        for m in OUTPUT_LINK_RE.finditer(blob):
            target = normalize_output_url(m.group(0))
            paths = candidate_keys(target)
            if paths:
                names.add(paths[0].casefold())
    return ids, gen_ids, names


def build_chat_attachment_plan(conversation, main, extras, assets):
    """Сопоставляет Library с сообщениями. Не выдает догадку за точную связь.

    exact: file_id / generation_id в сообщении, уникальная ссылка, или ID ответа;
    inferred: единственная/наиболее подходящая реплика в том же ходе диалога;
    unplaced: метаданные есть, но соответствующий ответ не определён.
    """
    chat_id = str(conversation.get('id') or conversation.get('conversation_id') or '')
    mapping = conversation.get('mapping') if isinstance(conversation.get('mapping'), dict) else {}
    key_by_identity = {id(v): str(k) for k, v in mapping.items() if isinstance(v, dict)}
    by_key, id_lookup, metadata_parent_lookup, ordered = {}, defaultdict(list), defaultdict(list), []

    for node in list(main) + list(extras):
        if not isinstance(node, dict) or not isinstance(node.get('message'), dict):
            continue
        msg = node['message']
        key = key_by_identity.get(id(node), str(node.get('id') or msg.get('id') or ''))
        author = msg.get('author') or {}
        role = author.get('role', '') if isinstance(author, dict) else str(author)
        try:
            ts = float(msg.get('create_time') or node.get('create_time') or 0)
        except (TypeError, ValueError):
            ts = 0.0
        md = msg.get('metadata') if isinstance(msg.get('metadata'), dict) else {}
        # Это приоритеты, не заменяющие проверку связи между сообщениями.
        channel = str(md.get('channel') or '')
        if not channel and isinstance(md.get('message_type'), str):
            channel = md['message_type']
        content = msg.get('content') if isinstance(msg.get('content'), dict) else {}
        parts = content.get('parts', [])
        has_body = bool(parts or fallback_text(msg, content))
        info = {'node': node, 'node_key': key, 'role': role, 'time': ts,
                'channel': channel, 'content_type': str(content.get('content_type') or ''),
                'has_body': has_body,
                'ids': set(filter(None, (key, str(msg.get('id') or ''), str(node.get('id') or '')))),
                'refs': extract_message_refs(msg)}
        ordered.append(info)
        by_key[key] = info
        for mid in info['ids']:
            id_lookup[mid].append(info)
        # Library.origination_message_id иногда ссылается не на mapping message.id,
        # а на metadata.parent_id служебного ответа ChatGPT.
        virtual_parent = md.get('parent_id')
        if isinstance(virtual_parent, str) and virtual_parent:
            metadata_parent_lookup[virtual_parent].append(info)

    def uniquely(items):
        return items[0] if len(items) == 1 else None

    def ancestor_path(child_key, origin_key):
        """Возвращает путь от origin до child только в подтверждённой ветке."""
        current, seen, path = child_key, set(), []
        for _ in range(20000):
            if not current or current in seen:
                return None
            if current == origin_key:
                return list(reversed(path))
            seen.add(current)
            node = mapping.get(current)
            if not isinstance(node, dict):
                return None
            path.append(current)
            current = str(node.get('parent') or '')
        return None

    def same_user_turn(candidate, origin):
        path = ancestor_path(candidate['node_key'], origin['node_key'])
        if path is None:
            return False
        # Не перепрыгиваем через следующий запрос пользователя.
        for step in path[:-1]:
            if by_key.get(step, {}).get('role') == 'user':
                return False
        return True

    def direct_visible_descendant(service):
        """Возвращает уникальный ближайший assistant/text — потомок служебного узла.

        Если веток несколько и они равнозначны, не выбираем ответ произвольно.
        """
        candidates = []
        for item in ordered:
            if item['role'] != 'assistant' or item['node_key'] == service['node_key']:
                continue
            if item['content_type'] not in ('text', 'multimodal_text'):
                continue
            path = ancestor_path(item['node_key'], service['node_key'])
            if path is None or any(by_key.get(step, {}).get('role') == 'user' for step in path[:-1]):
                continue
            candidates.append((len(path), item['time'], item))
        if not candidates:
            return None
        candidates.sort(key=lambda p: (p[0], p[1], p[2]['node_key']))
        nearest = [row for row in candidates if row[0] == candidates[0][0]]
        return nearest[0][2] if len(nearest) == 1 else None

    # Не полагаемся только на номер mapping: ID сообщения в Library нередко
    # отличается от ключа узла, поэтому оба индекса проверяются независимо.
    entries = list(assets.library_by_chat.get(chat_id, ()))
    seen = {e['file_id'] for e in entries}
    for info in ordered:
        for mid in info['ids']:
            for e in assets.library_by_message.get(mid, ()):
                if e['file_id'] not in seen and (not e['chat_id'] or e['chat_id'] == chat_id):
                    entries.append(e)
                    seen.add(e['file_id'])
    name_count = defaultdict(int)
    for e in entries:
        name_count[str(e.get('file_name') or '').casefold()] += 1

    plan, bindings, generated_only = defaultdict(list), [], defaultdict(list)
    users_in_time = sorted(
        (i for i in ordered if i['role'] == 'user' and i['time'] > 0),
        key=lambda i: (i['time'], i['node_key']))

    def image_generation_request(timestamp):
        """Select a request only when a service assistant node proves its ancestry.

        The generated picture may have no visible assistant/text response at all.
        Never attach it to the next textual answer, or simply to the closest user.
        """
        if not timestamp or not users_in_time:
            return None
        prior = [u for u in users_in_time if 0 <= timestamp - u['time'] <= 10 * 60]
        if not prior:
            return None
        req = prior[-1]
        # A real assistant service record immediately preceding the image is
        # required; otherwise chronological proximity alone is NOT evidence.
        service_nodes = []
        for item in ordered:
            if item['role'] != 'assistant' or not item['time']:
                continue
            delay = timestamp - item['time']
            if delay < 0 or delay > 90:
                continue
            path = ancestor_path(item['node_key'], req['node_key'])
            if path is None:
                continue
            if any(by_key.get(step, {}).get('role') == 'user' for step in path[:-1]):
                continue
            service_nodes.append((delay, item))
        if not service_nodes:
            return None
        service_nodes.sort(key=lambda v: (v[0], v[1]['node_key']))
        if service_nodes[0][0] > 40:
            return None
        return req

    for entry in entries:
        origin_id = entry.get('message_id') or ''
        origin = uniquely(id_lookup.get(origin_id, ()))
        virtual = None if origin else uniquely(metadata_parent_lookup.get(origin_id, ()))
        # Навигационный якорь: если связь с финальным ответом не удаётся
        # установить, укажем хотя бы на реальный пользовательский запрос,
        # которому предшествовал найденный служебный шаг.
        if virtual:
            cursor, visited = virtual['node_key'], set()
            while cursor and cursor not in visited:
                visited.add(cursor)
                inf = by_key.get(cursor)
                if inf and inf['role'] == 'user':
                    entry['origin_hint_message_id'] = str(inf['node'].get('message', {}).get('id') or cursor)
                    break
                parent_node = mapping.get(cursor)
                cursor = str(parent_node.get('parent') or '') if isinstance(parent_node, dict) else ''
        fid = asset_key(entry.get('file_id') or '')
        gen = entry.get('generation_id') or ''
        created = readable_iso_timestamp(entry.get('created'))
        generated = is_generated_library_entry(entry)
        best, mode, explanation = None, 'unplaced', 'В истории не установлен конкретный ответ'
        # Необязательная ручная корректировка, привязанная к ТОЧНОМУ file_id.
        # Никакого сопоставления по имени без проверки конкретного диалога.
        override = assets.binding_overrides.get(entry['file_id'])
        if isinstance(override, str):
            override = {'message_id': override}
        if isinstance(override, dict):
            manual_chat = str(override.get('conversation_id') or override.get('chat_id') or chat_id)
            target = str(override.get('message_id') or '')
            if manual_chat == chat_id and target:
                manual = uniquely(id_lookup.get(target, ()))
                if manual:
                    best, mode, explanation = manual, 'manual', 'Указано пользователем в ChatGPT_Binding_Overrides.json'

        # 1. Явная ссылка на ID файла или generation_id в содержимом сообщения.
        direct = [i for i in ordered if fid and (fid in i['refs'][0] or (gen and gen in i['refs'][1]))]
        direct_assistants = [i for i in direct if i['role'] == 'assistant']
        # Для пользовательских вложений приоритет у исходного сообщения,
        # а не у ответа, который только процитировал тот же file_id.
        direct_best = (origin if (origin and not generated and origin in direct) else
                       uniquely(direct_assistants) or uniquely(direct))
        if direct_best and not best:
            best, mode, explanation = direct_best, 'exact', 'ID файла/генерации явно указан в сообщении'

        # 2. Уникальное имя присутствует в явной ссылке и не повторяется среди
        # Library записей этого чата; простое слово в тексте не считается ссылкой.
        fname = str(entry.get('file_name') or '')
        if not best and fname and name_count[fname.casefold()] == 1:
            aliases = {a.casefold() for a in filename_aliases(fname)}
            links = [i for i in ordered if i['refs'][2].intersection(aliases)]
            assistants = [i for i in links if i['role'] == 'assistant']
            direct_name = uniquely(assistants) or uniquely(links)
            if direct_name:
                best, mode, explanation = direct_name, 'exact', 'Однозначная ссылка с названием файла в сообщении'

        # 3. Прямой мост от библиотечного origination_message_id к скрытому
        # parent_id промежуточного сообщения, затем к видимому ответу.
        # Это воспроизводимый случай на пользовательских экспортах 2026 года.
        if not best and virtual and generated:
            descendant = direct_visible_descendant(virtual)
            if descendant:
                best, mode = descendant, 'inferred'
                explanation = ('ID Library совпал с metadata.parent_id служебного шага; '
                               'целевой assistant/text найден по пути parent в mapping')

        # 4. Library часто указывает на user-запрос, когда картинку СГЕНЕРИРОВАЛ
        # assistant. Ищем ответ строго до следующего user-запроса в той же ветке.
        if not best and origin:
            if generated and origin['role'] == 'user':
                candidates = [i for i in ordered if i['role'] == 'assistant'
                              and same_user_turn(i, origin)]
                # Исключаем промежуточные tool-calls, analysis, скрытые служебные шаги.
                finals = [i for i in candidates if i['channel'] == 'final']
                if finals:
                    candidates = finals
                visible = [i for i in candidates if i['has_body']]
                if visible:
                    candidates = visible
                if candidates:
                    if created:
                        # Предпочитаем ответ, временная метка которого ближе всего
                        # к созданию результата, даже если задержка больше 6 часов.
                        ranked = sorted(candidates, key=lambda i: (abs((i['time'] or created) - created),
                                                                   i['time'], i['node_key']))
                    else:
                        ranked = sorted(candidates, key=lambda i: (i['time'] or 0, i['node_key']))
                    if len(ranked) == 1 or (created and len(ranked) > 1 and ranked[0]['time'] != ranked[1]['time']):
                        best, mode = ranked[0], 'inferred'
                        explanation = 'Ответ в ветке исходного запроса до следующего сообщения пользователя; выбор по времени'
                    elif not created and len(ranked) == 1:
                        best, mode = ranked[0], 'inferred'
                        explanation = 'Единственный ответ в ветке запроса'
            elif generated and origin['role'] in ('tool', 'assistant') and (
                    origin['role'] == 'tool' or origin['channel'] in ('analysis', 'commentary')):
                # Создающие изображение tool/analysis-сообщения могут не иметь
                # пригодного для просмотра тела. Переносим карточку под
                # видимый финальный ответ в той же ветке, если он определяется.
                next_replies = [i for i in ordered if i['role'] == 'assistant'
                                and i['node_key'] != origin['node_key']
                                and same_user_turn(i, origin) and i['has_body']]
                finals = [i for i in next_replies if i['channel'] == 'final']
                if finals:
                    next_replies = finals
                if next_replies:
                    next_replies.sort(key=lambda i: (i['time'] or 0, i['node_key']))
                    best, mode = next_replies[0], 'inferred'
                    explanation = 'Результат tool/analysis перенесён под последующий видимый ответ той же ветки'
                else:
                    best, mode, explanation = origin, 'exact', 'ID технического сообщения совпадает с Library'
            elif origin['role'] == 'assistant':
                best, mode, explanation = origin, 'exact', 'Library указывает непосредственно на ответ ChatGPT'
            else:
                # Нельзя подменять настоящий пользовательский upload ответом.
                best, mode, explanation = origin, 'exact', 'ID исходного сообщения совпадает с Library'

        # 4. Иногда Library записала ID сообщения, которого нет в экспортированном
        # mapping (другая ветка, сервисное сообщение). При отсутствии прямой связи
        # выбираем только уникальный, близкий по времени ответ в ЭТОМ чате.
        if not best and generated and not origin and created:
            nearby = [i for i in ordered if i['role'] == 'assistant' and i['time']
                      and abs(i['time'] - created) <= 15 * 60]
            if len(nearby) == 1:
                best, mode, explanation = nearby[0], 'inferred', 'Единственный ответ в пределах ±15 минут от создания файла'
            elif len(nearby) > 1:
                near = sorted(nearby, key=lambda i: abs(i['time'] - created))
                if abs(near[0]['time'] - created) + 90 < abs(near[1]['time'] - created):
                    best, mode, explanation = near[0], 'inferred', 'Ближайший ответ существенно ближе остальных по времени'

        # 4b. Когда ID оригинального tool-event отсутствует, но изображение
        # создано почти одновременно с ОДНИМ текстовым ответом ассистента,
        # допускаем временную привязку. Не называем её exact и не выбираем
        # между конкурирующими ответами с близкими временами.
        if not best and generated and not origin and created:
            final_texts = [i for i in ordered if i['role'] == 'assistant'
                           and i['content_type'] in ('text', 'multimodal_text') and i['time']]
            final_texts.sort(key=lambda i: (abs(i['time'] - created), i['node_key']))
            if final_texts:
                dist = abs(final_texts[0]['time'] - created)
                runner_up = (abs(final_texts[1]['time'] - created)
                             if len(final_texts) > 1 else float('inf'))
                if dist <= 20 and runner_up >= max(25, 2.5 * dist):
                    best, mode, explanation = (final_texts[0], 'inferred',
                        'Один ответ assistant/text в пределах 20 секунд создания файла; '
                        'следующий кандидат существенно дальше по времени')

        # 5. Если ID origination_message отсутствует в этом экспорте, можно
        # определить ХОД ДИАЛОГА по времени Library: от user-запроса до
        # следующего user-запроса. Это особенно полезно при пакетной генерации
        # нескольких изображений (один запрос, несколько файлов, много tool-steps).
        # Это остаётся предположением; никогда не называем привязку exact.
        if not best and generated and not origin and created:
            chronological = sorted((i for i in ordered if i['time'] > 0),
                                   key=lambda i: (i['time'], i['node_key']))
            users = [i for i in chronological if i['role'] == 'user']
            possible_turns = []
            for idx, req in enumerate(users):
                next_t = users[idx + 1]['time'] if idx + 1 < len(users) else float('inf')
                # Не выбираем другую беседу, если запись о файле появилась намного
                # позже последнего ответа. Допуск 20 минут на генерацию.
                if req['time'] - 120 <= created < next_t:
                    candidates = [i for i in chronological if i['role'] == 'assistant'
                                  and i['time'] >= req['time'] and i['time'] < next_t]
                    if candidates:
                        finals = [i for i in candidates if i['channel'] == 'final']
                        if finals:
                            candidates = finals
                        visible = [i for i in candidates if i['has_body']]
                        if visible:
                            candidates = visible
                        best_candidate = min(candidates, key=lambda i: (abs(i['time'] - created), i['time']))
                        distance = abs(best_candidate['time'] - created)
                        if distance <= 20 * 60:
                            possible_turns.append((best_candidate, distance))
            if len(possible_turns) == 1:
                best, mode = possible_turns[0][0], 'inferred'
                explanation = 'Связь по времени создания файла с ходом диалога от запроса до следующего запроса (ID сообщения отсутствует)'

        # Last resort for image_gen pictures: a valid *generated-only* turn
        # may contain reasoning/tool nodes but no visible final assistant text.
        # Create a separate visible assistant card IMMEDIATELY AFTER the user
        # request, preserving chronology. Do not confuse the request with the
        # actual generated reply, and never place by time alone.
        if (best is None and generated and entry.get('local')
                and str(entry.get('file_name') or '').lower().endswith(tuple(IMAGE_EXTS))
                and gen and created):
            request = image_generation_request(created)
            if request is not None:
                best, mode = request, 'synthesized'
                explanation = ('Служебный ответ в той же ветке создан незадолго до изображения; '
                               'видимого assistant/text в ходе диалога нет. '
                               'Добавлена отдельная карточка результата, а не подмена ответа.')
                generated_only[id(request['node'])].append((entry, mode, explanation))

        if best and mode != 'synthesized':
            plan[id(best['node'])].append((entry, mode, explanation))
        bindings.append((entry, best, mode, explanation))
    return plan, bindings, generated_only


def library_attachment_html(items, assets, already_linked):
    """Карточки добавляем ПОД ответом, с локальным превью при наличии файла."""
    chunks, inserted, missing = [], set(), []
    for entry, mode, explanation in items:
        local = entry.get('local') or ''
        if local and local in already_linked: continue
        if local and local in inserted: continue
        safe_title = html.escape(entry.get('file_name') or entry['file_id'])
        suffix = (('<span class="link-confidence">вероятная привязка: ' + html.escape(explanation) + '</span>')
                  if mode == 'inferred' else '')
        if local and asset_key(entry.get('file_id', '')) in assets.weak_ids:
            suffix += '<span class="link-confidence">доступная копия найдена по имени и размеру; ID оригинала не подтверждён</span>'
        if local:
            href = assets.local_href(local)
            if Path(local).suffix.lower() in IMAGE_EXTS:
                chunks.append('<div class="library-media"><a href="'+href+'" target="_blank" rel="noopener">'
                              '<img loading="lazy" decoding="async" src="'+href+'" alt="'+safe_title+'"></a>'
                              '<div>🖼 '+safe_title+' '+suffix+'</div></div>')
            else:
                chunks.append('<div class="library-file">📦 <a href="'+href+'" target="_blank" '
                              'download="'+html.escape(local,quote=True)+'">'+safe_title+'</a> '+suffix+'</div>')
            inserted.add(local)
        else:
            options = assets.alternative_html(entry.get('file_name') or '')
            if options:
                missing.append('<li>'+safe_title+' — '+options+' '+suffix+'</li>')
            else:
                missing.append('<li>'+safe_title+' — локальный файл не найден. '
                               +html.escape(entry.get('file_id') or '')+' '+suffix+'</li>')
    if missing:
        chunks.append('<details class="generated-output missing-output"><summary>⚠ Файлы Library без локальной копии: '
                      +str(len(missing))+'</summary><ul>'+''.join(missing)+'</ul></details>')
    return '\n'.join(chunks), inserted


def human_date(value):
    try:
        if value is None:
            return ""
        return datetime.fromtimestamp(float(value)).strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError, OSError, OverflowError):
        return ""


CHAT_CSS = r"""
:root{color-scheme:light;font-family:system-ui,-apple-system,'Segoe UI',Arial,sans-serif}
*{box-sizing:border-box}body{max-width:980px;margin:0 auto;background:#fff;color:#202123;padding:28px 28px 70px;font-size:15px;line-height:1.65}
header{border-bottom:1px solid #e5e7eb;padding-bottom:18px;margin-bottom:26px}h1{font-size:26px;line-height:1.25;overflow-wrap:anywhere;margin:0 0 8px}
.date{font-size:12px;color:#737a86}article{display:grid;grid-template-columns:115px minmax(0,1fr);gap:14px;margin:0 0 22px;padding-bottom:20px;border-bottom:1px solid #edf0f2}
.role{font-weight:650;font-size:13px;color:#55616b;padding-top:8px}.role.user{color:#087557}.role.assistant{color:#6543a5}
.body{overflow-wrap:anywhere;min-width:0}.body>*:first-child{margin-top:0}.body>*:last-child{margin-bottom:0}p{margin:0 0 12px}ul,ol{padding-left:24px;margin:6px 0 14px}
pre{background:#f5f6f8;border:1px solid #e8e9ec;border-radius:9px;padding:14px 16px;overflow:auto;max-width:100%;line-height:1.48;font-size:13px;white-space:pre}
code{font-family:Consolas,'Courier New',monospace;font-size:.91em}p code,li code{background:#f1f1f1;border-radius:4px;padding:2px 5px}pre code{font-size:inherit}
a{color:#137f6c}a:hover{text-decoration:underline}h2,h3,h4,h5,h6{line-height:1.3;margin:20px 0 9px}blockquote{border-left:3px solid #becbc8;padding:5px 14px;margin:12px 0;background:#fafafa}
figure.attachment{margin:13px 0;max-width:680px}figure img{display:block;max-width:100%;max-height:520px;object-fit:contain;border-radius:9px;border:1px solid #e7e7e7}figcaption{font-size:12px;color:#596471;margin-top:4px}
.download{margin:10px 0;background:#f7f8f9;padding:11px;border-radius:8px}.branch{font-size:17px;border-bottom:1px solid #ddd;margin:36px 0 22px;padding-bottom:8px;color:#67717c}.empty{color:#64748b}
.table-wrap{overflow-x:auto;margin:12px 0 18px}table{border-collapse:collapse;width:max-content;min-width:100%;table-layout:auto}th,td{border:1px solid #e3e5e7;padding:9px 12px;text-align:left;vertical-align:top;overflow-wrap:normal;word-break:normal;hyphens:none}th{background:#f6f7f8;font-weight:650}tr:nth-child(even) td{background:#fcfcfd} td:nth-child(2){white-space:nowrap}
.inline-img{display:block;max-width:100%;max-height:600px;object-fit:contain;border-radius:10px;margin:8px 0}.candidate-files{display:inline-block;background:#fff1d6;border:1px solid #ead3a3;border-radius:7px;padding:6px 9px;overflow-wrap:anywhere}.candidate-files a{margin:0 3px}.missing-file{color:#9b5a08;background:#fff7e7;padding:2px 7px;border-radius:5px}.external-image{background:#f3f4f6;padding:2px 7px}.ui-source{font-size:12px;color:#596471;border:1px solid #e5e7eb;border-radius:8px;padding:8px 12px;margin:10px 0}.ui-source summary{cursor:pointer}.ui-source pre{max-height:400px}a[download]{font-weight:600}
.structure pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:700px}.ui-dynamic-note{font-size:12px;color:#765b1a;background:#fffaf0;padding:6px 9px;border-radius:7px}
.dil-row{display:flex;flex-wrap:wrap;gap:14px;margin:12px 0;align-items:flex-start}
.dil-row>.dil-box,.dil-row>.dil-column{flex:1 1 210px;min-width:0}
.dil-box{background:#f8f9fa;border:1px solid #e3e6e8;border-radius:12px;padding:14px;margin:8px 0;min-width:0}
.dil-box>*:last-child,.dil-text>*:last-child{margin-bottom:0}
.dil-column,.dil-stack{min-width:0;display:flex;flex-direction:column;gap:8px}
.dil-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:12px 0}
.dil-divider{border:0;border-top:1px solid #e2e5e7;margin:12px 0}
.dil-title{font-size:18px;margin:6px 0 8px;line-height:1.35}.dil-title>*{margin:0}
.dil-caption{font-size:12px;color:#67717e;margin:8px 0}
.dil-badge,.dil-button{display:inline-block;padding:4px 9px;border-radius:7px;background:#ecf1f0;font-size:12px;margin:3px}
.dil-button{background:#daeae5;color:#07664b}.dil-icon{font-size:18px;color:#167b63}
.generated-output{background:#f7faf9;border:1px solid #d8e8df;border-radius:9px;padding:10px 14px;margin:10px 0}.generated-output summary{cursor:pointer;font-weight:600}.missing-output{background:#fff9ee;border-color:#f0dfb9}.generated-output code{overflow-wrap:anywhere}.dil-code{white-space:pre-wrap}.dil-text{min-width:0}

.files-overview{border-top:2px solid #dfe5e3;margin-top:38px;padding-top:15px}.files-overview h2{font-size:21px;margin:8px 0}.files-overview-hint{color:#697581;font-size:13px}
.files-overview-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:10px;margin:18px 0}
.file-entry{display:flex;align-items:center;min-width:0;gap:12px;border:1px solid #e4e9e6;border-radius:9px;padding:10px;background:#fafcfb}
.file-entry-text{flex:1;min-width:0;overflow-wrap:anywhere;font-size:13px}.file-entry-text>a{font-weight:600}
.file-preview{width:66px;height:66px;object-fit:cover;border-radius:6px;border:1px solid #e0e3e2;flex-shrink:0}.file-type{font-size:29px;width:66px;text-align:center;flex-shrink:0}
.file-occurrences{margin-top:5px;color:#71807b;font-size:12px}.file-occurrences a{white-space:normal}.file-unsited{color:#8a6b41}
article:target{outline:2px solid #12a37f;outline-offset:3px;border-radius:4px}
.library-media{margin:15px 0;padding:10px;border:1px solid #dfebea;border-radius:12px;background:#fbfdfc}
.library-media img{display:block;width:auto;max-width:100%;max-height:850px;object-fit:contain;border-radius:8px}
.library-media>div{font-size:12px;color:#555;padding-top:9px;overflow-wrap:anywhere}
.synthetic-result{background:#f7fcfa;padding:12px;border:1px solid #d8ede5;border-radius:12px}
.synthetic-note{font-size:12px;color:#526b63;margin-bottom:12px}
.library-file{border:1px solid #e4e9e7;border-radius:9px;padding:10px;margin:7px 0;overflow-wrap:anywhere}
.link-confidence{display:inline-block;font-size:11px;color:#966300;white-space:normal;background:#fff7e7;border-radius:5px;padding:2px 6px}

@media(max-width:640px){body{padding:14px}article{grid-template-columns:1fr;gap:2px}.role{padding-top:0}}
"""


def attachment_summary_html(file_locations, unplaced_files, missing_locations, assets):
    """Компактный список всех вложений чата, в том числе из тела ответов.

    file_locations: {локальное имя: [(id HTML-сообщения, роль, дата), ...]}.
    unplaced_files: только файлы со связью на чат, но без надёжного ID сообщения.
    """
    all_files = set(file_locations) | set(unplaced_files)
    if not all_files and not missing_locations:
        return ''
    out = ['<section class="files-overview" id="all-attachments">',
           '<h2>📎 Все файлы диалога</h2>',
           '<p class="files-overview-hint">Документы и картинки также находятся рядом с соответствующими сообщениями. '
           'Здесь собраны все найденные вложения без повторов, от новых к старым.</p>']
    if all_files:
        out.append('<div class="files-overview-list">')
        def summary_order(filename):
            # Последнее сообщение первым. Если точной привязки нет — ниже.
            positions = file_locations.get(filename, ())
            last = max((int(anchor.rsplit('-', 1)[-1]) for anchor, _, _ in positions), default=0)
            return (-last, filename.casefold())
        for name in sorted(all_files, key=summary_order):
            href = assets.local_href(name)
            shown_name = html.escape(name)
            is_img = Path(name).suffix.lower() in IMAGE_EXTS
            lead = (('<img class="file-preview" loading="lazy" decoding="async" src="' + href +
                     '" alt="">') if is_img else '<span class="file-type">📄</span>')
            occurrences = []
            recorded = set()
            for anchor, role, when in file_locations.get(name, []):
                if anchor in recorded:
                    continue
                recorded.add(anchor)
                occurrences.append('<a href="#' + html.escape(anchor, quote=True) + '">↗ ' +
                                   html.escape(role + (' · ' + when if when else '')) + '</a>')
            if not occurrences:
                occurrences.append('<span class="file-unsited">Связан с чатом; сообщение не установлено</span>')
            out.append('<div class="file-entry">' + lead + '<div class="file-entry-text">' +
                       '<a href="' + href + '" target="_blank" rel="noopener">' + shown_name + '</a>' +
                       '<div class="file-occurrences">' + ' · '.join(occurrences) + '</div>' +
                       '</div></div>')
        out.append('</div>')
    if missing_locations:
        out.append('<details class="generated-output missing-output"><summary>⚠ Упомянутые, но не найденные файлы: ' +
                   str(len(missing_locations)) + '</summary><ul>')
        for (ref, label), anchors in sorted(missing_locations.items(), key=lambda x: str(x[0][1] or x[0][0] or '').casefold()):
            links = ' · '.join('<a href="#' + html.escape(a, quote=True) + '">↗ сообщение</a>'
                               for a in dict.fromkeys(anchors) if a)
            out.append('<li>' + html.escape(label or ref[:220]) + ((' — ' + links) if links else '') + '</li>')
        out.append('</ul></details>')
    out.append('</section>')
    return '\n'.join(out)


def write_chat(conversation, number, assets):
    title = str(conversation.get("title") or "Без названия")
    chat_id = str(conversation.get("id") or conversation.get("conversation_id") or number)
    digest = hashlib.sha1(f"{chat_id}:{number}".encode("utf-8", "replace")).hexdigest()[:8]
    filename = f"chat_{number:07d}_{digest}.html"
    path = CHATS_DIR / filename
    main, extras = ordered_nodes(conversation)
    assets.current_chat_id = chat_id
    assets.current_message_ids = ()
    attachment_plan, attachment_bindings, generated_only = build_chat_attachment_plan(conversation, main, extras, assets)
    written = 0
    # Файл появляется непосредственно у сообщения, а также один раз в общем списке.
    file_locations = defaultdict(list)
    missing_locations = defaultdict(list)
    ui_counter = 0
    anchor_by_node = {}
    anchor_by_synthetic = {}
    anchor_by_message_id = {}
    text_mentions = defaultdict(set)  # название файла или ID из прямых ссылок → якоря
    def save_dil(raw):
        nonlocal ui_counter
        ui_counter += 1
        fname = Path(filename).stem + f"_ui_{ui_counter:04d}.txt"
        (DIL_DIR / fname).write_text(raw, encoding="utf-8")
        return "../dil_sources/" + quoted_url(fname)
    chat_time = conversation.get("update_time") or conversation.get("create_time") or 0
    chat_href = "chats/" + filename
    with path.open("w", encoding="utf-8", newline="\n") as out:
        out.write('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                  '<meta name="viewport" content="width=device-width,initial-scale=1">'
                  '<title>' + html.escape(title) + '</title><style>' + CHAT_CSS + DIL_V7_CSS +
                  '</style><script>window.MathJax={tex:{inlineMath:[[\"\\\\(\",\"\\\\)\"],[\"$\",\"$\"]],displayMath:[[\"\\\\[\",\"\\\\]\"],[\"$$\",\"$$\"]],processEscapes:true},svg:{fontCache:\"global\"},options:{skipHtmlTags:[\"script\",\"noscript\",\"style\",\"textarea\",\"pre\",\"code\"]}};</script>' +
                  '<script defer src=\"../viewer/mathjax-tex-svg.js\"></script></head><body><header><h1>' + html.escape(title) + '</h1>' +
                  '<div class="date">' + html.escape(human_date(conversation.get("create_time"))) +
                  '</div></header>')
        for section, nodes in enumerate((main, extras)):
            heading_written = False
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                message = node.get("message")
                if not isinstance(message, dict):
                    continue
                ids = [str(x) for x in (message.get('id'), node.get('id')) if x]
                assets.current_message_ids = tuple(ids)
                body, linked = render_message(message, assets, save_dil, ids)
                author = message.get("author")
                role = author.get("role", "") if isinstance(author, dict) else str(author or "")
                message_time = message.get('create_time') or chat_time
                if role == 'assistant':
                    extra_html, created_files, missing_refs = record_output_files(
                        message, assets, title, chat_href, message_time)
                    if extra_html:
                        body += '\n' + extra_html
                    linked.update(created_files)
                else:
                    missing_refs = []
                planned = attachment_plan.get(id(node), [])
                extra_cards, planned_added = library_attachment_html(planned, assets, linked)
                if extra_cards:
                    body += '\n' + extra_cards
                linked.update(planned_added)
                for mid in ids:
                    # Показываем отсутствующие записи Library прямо у связанного ответа.
                    for file_id, fname in assets.missing_library_by_message.get(mid, ()):
                        if any(e['file_id'] == file_id for e,_,_ in planned):
                            continue
                        ref = 'library:' + file_id
                        missing_refs.append((ref, fname))
                # Дубли Library/sandbox не плодят одинаковые предупреждения.
                if missing_refs:
                    unique_missing = {(r, l) for r, l in missing_refs}
                    if role != 'assistant' or not extra_html:
                        body += '<details class="generated-output missing-output"><summary>⚠ Файлы без локальной копии: ' + str(len(unique_missing)) + '</summary><ul>' + ''.join(
                            '<li>' + html.escape(label or ref) + '</li>' for ref, label in sorted(unique_missing)
                        ) + '</ul></details>'
                    elif any(r.startswith('library:') for r, _ in unique_missing):
                        library_only = sorted((r, l) for r, l in unique_missing if r.startswith('library:'))
                        if library_only:
                            body += '<details class="generated-output missing-output"><summary>⚠ Файлы из Library без локальной копии: ' + str(len(library_only)) + '</summary><ul>' + ''.join(
                                '<li>' + html.escape(label or ref) + '</li>' for ref, label in library_only
                            ) + '</ul></details>'
                assets.observe(linked, message_time, title, chat_href)
                if not body.strip() and not linked:
                    continue
                if section and not heading_written:
                    out.write('<h2 class="branch">Другие ветки и альтернативные ответы</h2>')
                    heading_written = True
                written += 1
                anchor = 'message-' + str(written)
                anchor_by_node[id(node)] = anchor
                # Соответствие как по key mapping, так и по message.id.
                for key in (*ids, str(node.get('id') or '')):
                    if key:
                        anchor_by_message_id[key] = anchor
                # Индекс прямых упоминаний (включая sandbox-ссылки и metadata).
                for ref in output_references(message):
                    for alias in candidate_keys(ref):
                        for name_alias in filename_aliases(alias):
                            text_mentions[name_alias.casefold()].add(anchor)
                for token in extract_message_refs(message)[0]:
                    text_mentions[token].add(anchor)
                name = {"assistant": "ChatGPT", "user": "Вы", "system": "Система", "tool": "Инструмент"}.get(role, role or "Сообщение")
                cls = role if role in {"assistant", "user", "system", "tool"} else "other"
                out.write('<article id="' + anchor + '"><div class="role ' + cls + '">' + html.escape(name) +
                          '</div><div class="body">' + body + '</div></article>\n')
                date = human_date(message_time)
                for item in linked:
                    file_locations[item].append((anchor, name, date))
                    assets.chat_locations[item] = (title, chat_href, anchor)
                for entry, mode, explanation in planned:
                    if not entry.get('local'):
                        missing_locations[('library:'+entry['file_id'], entry['file_name'])].append(anchor)
                for ref, label in missing_refs:
                    missing_locations[(ref, label)].append(anchor)
                # Some image-gen turns do not have a visible final/text node.
                # This synthetic assistant card follows the actual user request
                # but leaves the original messages untouched and the summary intact.
                if role == 'user' and id(node) in generated_only:
                    synthetic_anchor = 'generated-' + str(written)
                    pending = generated_only[id(node)]
                    synthetic_html, synthetic_files = library_attachment_html(pending, assets, linked)
                    if synthetic_html:
                        out.write('<article id="' + synthetic_anchor + '" class="synthetic-result">'
                                  '<div class="role assistant">ChatGPT</div><div class="body">'
                                  '<p class="synthetic-note">Результат генерации изображения · '
                                  'восстановлено по служебной цепочке экспорта; '
                                  'исходный текст ответа отсутствует</p>' + synthetic_html +
                                  '</div></article>\n')
                        for name in synthetic_files:
                            file_locations[name].append((synthetic_anchor, 'ChatGPT · изображение', human_date(message_time)))
                            assets.chat_locations[name] = (title, chat_href, synthetic_anchor)
                        assets.observe(synthetic_files, message_time, title, chat_href)
                        for entry, _, _ in pending:
                            if entry.get('local') in synthetic_files:
                                anchor_by_synthetic[entry['file_id']] = synthetic_anchor
        # Сохраняем доказательства КАЖДОГО решения о привязке.
        # Названия одинаковых файлов не подменяют ID, отсутствие контента = missing.
        for entry, chosen, mode, explanation in attachment_bindings:
            local = entry.get('local') or ''
            anchor = (anchor_by_synthetic.get(entry['file_id'], '') if mode == 'synthesized'
                      else anchor_by_node.get(id(chosen['node']), '') if chosen else '')
            info = {
                'chat_id':chat_id,'chat':title,'file_id':entry['file_id'],
                'filename':entry['file_name'],'local':local,'origin_message_id':entry.get('message_id') or '',
                # Synthetic assistant blocks did not exist as message IDs in
                # ChatGPT; do not falsely claim that the user is the assistant.
                'target_message_id':('' if mode == 'synthesized' else
                    str(chosen['node'].get('message',{}).get('id') or chosen['node_key']) if chosen else ''),
                'anchor':anchor,
                'origin_anchor':(anchor_by_node.get(id(chosen['node']), '') if mode == 'synthesized'
                    else anchor_by_message_id.get(entry.get('message_id') or '', '')
                    or anchor_by_message_id.get(entry.get('origin_hint_message_id') or '', '')),
                'binding':mode,'evidence':explanation,
                'generated':is_generated_library_entry(entry, chosen['role'] if chosen else ''),
                'file_status':entry.get('state') or '', 'kind':entry.get('kind') or '',
                'url':(chat_href+'#'+anchor) if anchor else chat_href,
            }
            if not anchor and info['origin_anchor']:
                # Навигация до исходного сообщения при unplaced. Не выдаём
                # этот якорь за целевой ответ ChatGPT.
                info['url'] = chat_href + '#' + info['origin_anchor']
            assets.bindings.append(info)
            assets.summary_bindings[mode] += 1
            if not local: assets.summary_bindings['missing'] += 1
            if info['generated']:
                ref = 'library:' + entry['file_id']
                assets.generated_references[(chat_href,ref)] = {
                    'chat':title, 'href':chat_href, 'time':chat_time,
                    'reference':ref, 'filename':entry['file_name'],
                    'status':'найден' if local else 'ОТСУТСТВУЕТ ФИЗИЧЕСКИЙ ФАЙЛ',
                    'local':local, 'evidence':explanation,
                    'source_evidence':assets.source_evidence.get(local,'') if local else ''}
        # Сначала привязанные к конкретным сообщениям файлы, затем оставшиеся
        # записи Library с известным ID чата (не приписываем их случайному ответу).
        unplaced = set(assets.by_chat_id.get(chat_id, ())) - set(file_locations)
        if not file_locations and not unplaced:
            # В старых манифестах может быть только название чата.
            # Эта привязка неточная, поэтому показываем только в общем разделе.
            unplaced.update(assets.by_title.get(title, ()))
        if unplaced:
            assets.observe(unplaced, chat_time, title, chat_href)
        missing_lib = list(assets.missing_library_by_chat.get(chat_id, ()))
        if not missing_lib:
            missing_lib = list(assets.missing_library_by_title.get(title, ()))
        planned_ids = {e['file_id'] for e, chosen, mode, note in attachment_bindings if chosen is not None}
        for absent_id, absent_name in missing_lib:
            if absent_id in planned_ids:
                continue
            ref = 'library:' + absent_id
            # Существующая запись в конце списка не создаёт новый элемент.
            anchors = missing_locations.setdefault((ref, absent_name), [])
            # Если в Library известен origination_message_id, переход хотя бы
            # к исходному сообщению должен присутствовать даже без привязки
            # к ответу ассистента. Если есть явная ссылка — приоритет у неё.
            for candidate in assets.library_by_chat.get(chat_id, ()):
                if candidate['file_id'] == absent_id:
                    origin_anchor = (anchor_by_message_id.get(candidate.get('message_id') or '')
                                     or anchor_by_message_id.get(candidate.get('origin_hint_message_id') or ''))
                    if origin_anchor and origin_anchor not in anchors:
                        anchors.append(origin_anchor)
                    break
            assets.generated_references.setdefault((chat_href, ref), {
                'chat': title, 'href': chat_href, 'time': chat_time, 'reference': ref,
                'filename': absent_name, 'status': 'НЕТ ФАЙЛА В LIBRARY ЭКСПОРТА', 'local': '',
                'evidence':'', 'source_evidence':''})
        # Для каждого локального файла, оставшегося в сводке, сохраняем якорь
        # исходного сообщения Library как подсказку (не утверждаем, что это ответ).
        for entry, chosen, mode, explanation in attachment_bindings:
            if chosen is None and entry.get('local'):
                origin_anchor = (anchor_by_message_id.get(entry.get('message_id') or '')
                                 or anchor_by_message_id.get(entry.get('origin_hint_message_id') or ''))
                if origin_anchor:
                    file_locations[entry['local']].append((origin_anchor, 'Исходное сообщение Library', ''))
        # У отсутствующего файла могут быть прямые упоминания в нескольких ответах.
        # Показываем ВСЕ эти позиции, а не первый/последний текстовый матч.
        for (ref, label), anchors in missing_locations.items():
            tokens = [asset_key(ref)] if ref.startswith('library:') else []
            keys = set(tokens)
            for candidate in filename_aliases(label or ''):
                keys.add(candidate.casefold())
            for candidate in candidate_keys(ref):
                keys.add(candidate.casefold())
            for key in keys:
                for anchor in text_mentions.get(key, ()):
                    if anchor not in anchors:
                        anchors.append(anchor)
        out.write(attachment_summary_html(file_locations, unplaced, missing_locations, assets))
        if not written and not file_locations and not unplaced:
            out.write('<p class="empty">В этом диалоге нет экспортированных текстовых сообщений.</p>')
        out.write('</body></html>')
    try:
        sorted_timestamp = float(chat_time)
    except (ValueError, TypeError):
        sorted_timestamp = 0.0
    return [title, chat_href, human_date(chat_time), sorted_timestamp]


INDEX_HTML_START = r'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Мой архив ChatGPT</title>
<style>
*{box-sizing:border-box}html,body{margin:0;height:100%;font:14px system-ui,-apple-system,'Segoe UI',Arial,sans-serif;color:#212121}
.app{display:flex;width:100%;height:100vh;height:100dvh;overflow:hidden}.sidebar{flex:none;width:330px;background:#f5f5f4;display:flex;flex-direction:column;border-right:1px solid #dededb;min-width:0}
.brand{padding:22px 18px 12px;font-size:19px;font-weight:700}.sub{font-size:12px;font-weight:400;color:#6b7280;margin-top:6px}.search-wrap{padding:0 12px 12px}
#search{width:100%;font:inherit;background:white;border:1px solid #d6d6d6;border-radius:9px;padding:11px;outline:none}#search:focus{border-color:#10a37f}
#count{padding:0 18px 8px;color:#777;font-size:12px}.list{position:relative;flex:1;overflow:auto;overscroll-behavior:contain}
.spacer{position:relative;min-height:2px}.rows{position:absolute;left:0;right:0}.row{width:100%;display:flex;align-items:flex-start;justify-content:center;flex-direction:column;padding:0 17px;height:46px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-decoration:none;color:#333;border-radius:0;outline-offset:-2px}
.row:hover{background:#e6e8e5}.row.active{background:#dcefe9;color:#075e4c;font-weight:600}.row span{overflow:hidden;text-overflow:ellipsis;display:block;width:100%}.row small{font-size:10px;color:#777;white-space:nowrap}
.main{flex:1;min-width:0;height:100%;position:relative;background:#fff}iframe{width:100%;height:100%;border:0;background:#fff}
.welcome{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;padding:30px;pointer-events:none;color:#6b7280;font-size:17px}.welcome.hidden{display:none}
.empty-list{padding:15px 18px;color:#888}.gallery-nav{border-top:1px solid #e4e4e2;padding:12px 18px}.gallery-nav a{color:#076c56;text-decoration:none;font-weight:600}.gallery-nav a:hover{text-decoration:underline}.footer{font-size:11px;color:#777;border-top:1px solid #e4e4e2;padding:10px 18px}
@media(max-width:720px){.sidebar{width:41%;min-width:160px}.brand{font-size:16px;padding:14px 10px}.search-wrap{padding:0 7px 9px}.row{padding-left:9px;font-size:12px}}
</style></head><body><div class="app"><aside class="sidebar"><div class="brand">◉ Архив ChatGPT<div class="sub">Последние диалоги — вверху · работает офлайн</div></div>
<div class="search-wrap"><input id="search" type="search" placeholder="Поиск по названиям..." aria-label="Поиск по названиям чатов" autocomplete="off"></div>
<div id="count"></div><nav id="list" class="list" aria-label="Чаты"><div id="spacer" class="spacer"><div id="rows" class="rows"></div></div></nav>
<div class="gallery-nav"><a id="gallery-link" href="gallery/0001.html" target="chat_view">🖼 Галерея изображений</a> · <a id="outputs-link" href="generated_files.html" target="chat_view">📦 Файлы ChatGPT</a></div><div class="footer">Локальный архив · работает без интернета</div></aside>
<main class="main"><div id="welcome" class="welcome">Выберите диалог слева, чтобы прочитать его</div><iframe id="viewer" name="chat_view" title="Просмотр диалога" sandbox="allow-scripts allow-downloads allow-popups"></iframe></main></div>
<script>
'use strict';
const CHATS = '''

INDEX_HTML_END = r''';
// В памяти находится только компактный список названий, не содержимое всех чатов.
const input = document.getElementById('search');
const list = document.getElementById('list');
const spacer = document.getElementById('spacer');
const rows = document.getElementById('rows');
const count = document.getElementById('count');
const viewer = document.getElementById('viewer');
let filtered = CHATS.map((_, index) => index);
let selected = -1;
const ROW_HEIGHT = 46;
const BUFFER = 8;
function renderRows(){
  const top = list.scrollTop;
  const start = Math.max(0, Math.floor(top / ROW_HEIGHT) - BUFFER);
  const visible = Math.ceil(list.clientHeight / ROW_HEIGHT) + BUFFER * 2;
  const end = Math.min(filtered.length, start + visible);
  spacer.style.height = (filtered.length * ROW_HEIGHT) + 'px';
  rows.style.top = (start * ROW_HEIGHT) + 'px';
  const fragment = document.createDocumentFragment();
  for(let i=start; i<end; i++){
    const index = filtered[i];
    const chat = CHATS[index];
    const a = document.createElement('a');
    a.className = 'row' + (selected===index ? ' active' : '');
    a.href = chat[1];
    a.target = 'chat_view';
    a.title = chat[0] + (chat[2] ? '\n' + chat[2] : '');
    const span = document.createElement('span');
    span.textContent = chat[0];
    a.appendChild(span);
    if(chat[2]){
      const date = document.createElement('small');
      date.textContent = chat[2];
      a.appendChild(date);
    }
    a.addEventListener('click', event => {
      if(event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      openChat(index);
    });
    fragment.appendChild(a);
  }
  rows.replaceChildren(fragment);
}
function openChat(index){
  if(index < 0 || index >= CHATS.length) return;
  selected = index;
  viewer.src = CHATS[index][1];
  document.getElementById('welcome').classList.add('hidden');
  history.replaceState(null, '', '#chat=' + index);
  renderRows();
}
function doSearch(){
  const q = input.value.trim().toLocaleLowerCase();
  filtered = [];
  for(let i=0; i<CHATS.length; i++) if(CHATS[i][0].toLocaleLowerCase().includes(q)) filtered.push(i);
  count.textContent = 'Найдено: ' + filtered.length.toLocaleString('ru-RU') + ' / ' + CHATS.length.toLocaleString('ru-RU');
  list.scrollTop = 0;
  renderRows();
  if(filtered.length === 0){
    rows.innerHTML = '<div class="empty-list">Ничего не найдено</div>';
    spacer.style.height = '50px';
  }
}
document.getElementById('gallery-link').addEventListener('click', () => document.getElementById('welcome').classList.add('hidden'));
input.addEventListener('input', doSearch);
list.addEventListener('scroll', renderRows, {passive:true});
window.addEventListener('resize', renderRows);
doSearch();
const match = location.hash.match(/^#chat=(\d+)$/);
if(match) openChat(Number(match[1]));
else if(CHATS.length) openChat(0); // Сразу показать самый новый диалог.
</script></body></html>
'''


def write_index(chat_records):
    # Порядок как в ChatGPT: первый — наиболее недавно изменённый чат.
    chat_records.sort(key=lambda r: (-r[3], r[0].casefold(), r[1]))
    public_records = [r[:3] for r in chat_records]
    # Escape '<' защищает от </script> в названиях, даже если файл не доверенный.
    data = json.dumps(public_records, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e")
    data = data.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    with (DEST / "index.html").open("w", encoding="utf-8", newline="\n") as file:
        file.write(INDEX_HTML_START)
        file.write(data)
        file.write(INDEX_HTML_END)


def write_gallery(assets):
    names = assets.image_names()
    gallery = DEST / "gallery"
    gallery.mkdir(exist_ok=True)
    per_page = 120
    pages = (len(names) + per_page - 1) // per_page
    style = '''
*{box-sizing:border-box}body{font:14px system-ui,'Segoe UI',Arial,sans-serif;margin:0 auto;max-width:1160px;padding:24px;color:#222}h1{font-size:26px}p{color:#666}nav{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}nav a{padding:7px 12px;border-radius:8px;background:#e8f5ef;color:#075a48;text-decoration:none}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:16px}figure{margin:0;border:1px solid #e4e7e9;border-radius:10px;overflow:hidden}figure>a{display:block;height:186px;background:#f5f6f7}figure img{width:100%;height:100%;object-fit:contain}figcaption{overflow-wrap:anywhere;padding:8px;font-size:12px;color:#555}.chat-ref{display:block;padding:0 8px 8px;font-size:12px;color:#0a8065;text-decoration:none}.chat-ref:hover{text-decoration:underline}.hint{font-size:12px;color:#777}
'''
    with (DEST / "gallery.html").open("w", encoding="utf-8") as f:
        f.write('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Галерея изображений</title><style>' +
                style + '</style><h1>Изображения из экспорта · сначала новые</h1>' +
                '<p>Найдено: ' + str(len(names)) +
                '. Дата берётся из связанных сообщений, а если связи нет — из даты файла.</p>')
        if not pages:
            f.write('<p>Изображения не обнаружены. Проверьте наличие самих файлов в экспорте.</p>')
        else:
            f.write('<nav>' + ''.join(f'<a href="gallery/{i:04d}.html">Страница {i}</a>'
                                     for i in range(1, pages+1)) + '</nav>')
        f.write('</html>')
    if not pages:
        (gallery / "0001.html").write_text(
            '<!doctype html><html lang="ru"><meta charset="utf-8"><style>' + style +
            '</style><h1>Изображений в экспорте не найдено</h1><p>Проверьте исходные файлы и build_log.txt.</p></html>',
            encoding="utf-8")
    for page in range(1, pages+1):
        part = names[(page-1)*per_page:page*per_page]
        with (gallery / f"{page:04d}.html").open("w", encoding="utf-8") as f:
            f.write('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Изображения</title><style>' + style + '</style><h1>Изображения · ' + str(page) +
                    '/' + str(pages) + ' · сначала новые</h1><nav><a href="../gallery.html">Все страницы</a>')
            if page > 1: f.write(f'<a href="{page-1:04d}.html">← Назад</a>')
            if page < pages: f.write(f'<a href="{page+1:04d}.html">Вперёд →</a>')
            f.write('</nav><div class="grid">')
            for name in part:
                url = '../assets/' + quoted_url(name)
                t = assets.asset_times.get(name) or assets.asset_sources.get(name)
                date = human_date(t)
                f.write('<figure><a href="' + url + '" target="_blank"><img loading="lazy" src="' +
                        url + '" alt="' + html.escape(name,quote=True) + '"></a><figcaption>' +
                        html.escape(name) + '<div class="hint">' + html.escape(date) + '</div></figcaption>')
                if name in assets.asset_chats:
                    chat_title, chat_href = assets.asset_chats[name]
                    detail = assets.chat_locations.get(name)
                    if detail:
                        chat_title, chat_href, message_anchor = detail
                        chat_href += '#'+message_anchor
                    f.write('<a class="chat-ref" href="../' + quoted_url(chat_href).replace('%2F','/').replace('%23','#') +
                            '">↗ ' + html.escape(chat_title) + '</a>')
                f.write('</figure>')
            f.write('</div></html>')
    return len(names)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    DIL_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    viewer = DEST / "viewer"
    viewer.mkdir(parents=True, exist_ok=True)
    src_mathjax = ROOT / "viewer" / "mathjax-tex-svg.js"
    if src_mathjax.exists() and (not (viewer / src_mathjax.name).exists() or
        src_mathjax.stat().st_size != (viewer / src_mathjax.name).stat().st_size):
        shutil.copy2(src_mathjax, viewer / src_mathjax.name)
    mathjax_license = ROOT / "third_party_licenses" / "MathJax_APACHE-2.0.txt"
    if mathjax_license.exists():
        shutil.copy2(mathjax_license, DEST / "LICENSE_MathJax.txt")
    say("=== ChatGPT Local Archive STABLE v7.3.16.1 -> локальный HTML-архив ===")
    say(f"Источник: {ROOT}")
    say(f"Результат: {DEST}")
    say("Для больших экспортов диалоги извлекаются по одному — без загрузки всех JSON в RAM.")
    assets = AssetStore()
    assets.load_and_copy()
    records = []
    failures = []
    total = 0
    present = 0
    shards = find_shards()
    chat_audit = []
    seen_ids = set()
    if not shards: say('[!] В папке нет conversations-*.json или conversations.json')
    for shard in shards:
        if not shard.is_file():
            failures.append(f"Отсутствует шард: {shard.name}")
            say(f"[!] Нет файла: {shard.name}")
            continue
        present += 1
        shard_total = 0
        say(f"Читаем {shard.name} ({shard.stat().st_size / (1024 * 1024):.1f} МиБ)...")
        try:
            with shard.open("r", encoding="utf-8-sig") as file:
                for conversation in StreamJSON(file).conversations():
                    if not isinstance(conversation, dict):
                        continue
                    try:
                        record = write_chat(conversation, total + 1, assets)
                        records.append(record)
                        title = str(conversation.get('title') or 'Без названия')
                        cid = str(conversation.get('id') or conversation.get('conversation_id') or '')
                        duplicate = cid in seen_ids if cid else False
                        if cid: seen_ids.add(cid)
                        chat_audit.append({'shard':shard.name,'conversation_id':cid,'title':title,
                                           'status':'OK','html':record[1],
                                           'mapping_messages':len(conversation.get('mapping') or {}) if isinstance(conversation.get('mapping'),dict) else 0,
                                           'duplicate_id':'ДА' if duplicate else ''})
                        total += 1
                        shard_total += 1
                        if total % 100 == 0:
                            say(f"  Создано HTML-чатов: {total}")
                    except Exception as exc:
                        # Диалог остаётся в списке, а не исчезает без уведомления.
                        title = str(conversation.get('title') or 'Без названия')
                        cid = str(conversation.get('id') or conversation.get('conversation_id') or '')
                        digest = hashlib.sha1(f'{cid}:{total+1}'.encode('utf-8','replace')).hexdigest()[:8]
                        fname = f'chat_{total+1:07d}_{digest}_error.html'
                        (CHATS_DIR / fname).write_text('<!doctype html><html lang="ru"><meta charset="utf-8">'
                            '<h1>'+html.escape(title)+'</h1><p>Ошибка при подготовке страницы. '
                            'Этот диалог сохранён в списке, но не сконвертирован.</p><pre>'
                            +html.escape(str(exc))+'</pre></html>', encoding='utf-8')
                        href='chats/'+fname
                        when=conversation.get('update_time') or conversation.get('create_time') or 0
                        try: stamp=float(when)
                        except (TypeError,ValueError): stamp=0.0
                        records.append([title,href,human_date(when),stamp])
                        chat_audit.append({'shard':shard.name,'conversation_id':cid,
                                          'title':title,'status':'ERROR','html':href,
                                          'mapping_messages':len(conversation.get('mapping') or {}) if isinstance(conversation.get('mapping'),dict) else 0,
                                          'duplicate_id':''})
                        total+=1
                        shard_total+=1
                        message = f"Ошибка диалога {title!r} в {shard.name}: {exc}"
                        failures.append(message)
                        say("[!] " + message)
        except (OSError, UnicodeError, ValueError) as exc:
            message = f"Ошибка JSON-файла {shard.name}: {exc}"
            failures.append(message)
            say("[!] " + message)
        say(f"  Из {shard.name}: {shard_total} диалогов")
    # Полные индексы позволяют проверить отсутствие КОНКРЕТНОГО названия чата.
    def write_csv(name, rows, fields):
        with (DEST / name).open('w',encoding='utf-8-sig',newline='') as fh:
            writer=csv.DictWriter(fh,fieldnames=fields,extrasaction='ignore',delimiter=';')
            writer.writeheader();writer.writerows(rows)
    write_csv('dil_render_report.csv', DIL_RENDER_EVENTS,
              ['chat_id','message_id','source_sha256','render_mode','svg_count','layout_nodes',
               'unknown_nodes','blocked_nodes','bad_nesting','error'])
    write_csv('conversations_index.csv',chat_audit,
              ['shard','conversation_id','title','status','html','mapping_messages','duplicate_id'])
    write_csv('message_file_bindings.csv',assets.bindings,
              ['chat_id','chat','file_id','filename','local','origin_message_id',
               'target_message_id','anchor','origin_anchor','binding','evidence','generated','file_status','kind','url'])
    write_csv('unplaced_library_files.csv',
              [v for v in assets.bindings if v['binding'] == 'unplaced'],
              ['chat_id','chat','file_id','filename','local','origin_message_id',
               'origin_anchor','target_message_id','binding','evidence','file_status','url'])
    write_csv('missing_generated_files.csv',
              [v for v in assets.bindings if v['generated'] and not v['local']],
              ['chat_id','chat','file_id','filename','origin_message_id',
               'target_message_id','binding','evidence','file_status','kind','url'])
    assets.import_loose_images()
    images = write_gallery(assets)
    generated_found, generated_missing = write_generated_report(assets)
    write_library_integrity_report(assets)
    write_index(records)
    log_path = DEST / "build_log.txt"
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"Папка: {ROOT}\nОбработано шардов: {present}/{len(shards)}\n")
        log.write('Индекс ВСЕХ найденных чатов: conversations_index.csv\n')
        log.write('Распределение Library по сообщениям: message_file_bindings.csv\n')
        log.write('Недостающие созданные файлы: missing_generated_files.csv\n')
        log.write('Library без уверенной привязки: unplaced_library_files.csv\n')
        log.write('Расстановка Library: '+repr(dict(assets.summary_bindings))+'\n')
        log.write(f"Создано HTML-диалогов: {total}\nКопировано медиа: {assets.copied}\n")
        log.write(f"Отсутствует исходных файлов: {assets.missing}\n")
        log.write(f"Ошибок копирования: {assets.failed}\nПовторы файлов: {assets.reused}\n")
        log.write(f"Дополнительно найдено файлов без манифеста: {assets.found_without_manifest}\n")
        log.write(f"Изображений в галерее: {images}\n")
        log.write(f"Выданных файлов ChatGPT найдено (ссылок): {generated_found}\n")
        log.write(f"Выданных файлов ChatGPT НЕ НАЙДЕНО (ссылок): {generated_missing}\n")
        log.write("Список: generated_files_report.csv и generated_files.html\n")
        log.write('Подробная сверка Library: library_integrity_report.csv\n')
        log.write(f'Неоднозначных имён вложений: {len(assets.ambiguous_names)}\n')
        log.write(f'Повторов имён в ручной папке: {len(assets.manual_ambiguous)}\n')
        log.write(f"Сохранено исходников Intelligent UI: {len(list(DIL_DIR.glob('*.txt')))}\n")
        log.write(f"Изображений со связью с диалогом: {sum(1 for n in assets.image_names() if n in assets.asset_chats)}\n")
        log.write("Порядок галереи: дата сообщения/чата; если неизвестна — mtime файла.\n")
        log.write(f"Неразрешенных ссылок на файлы: {len(assets.unresolved)}\n\n")
        for ref in sorted(assets.unresolved):
            log.write("- Неразрешённая ссылка: " + ref + "\n")
        for problem in failures + assets.problems:
            log.write("- " + problem + "\n")
        if len(assets.problems) >= 150:
            log.write("(Список проблем с медиа сокращён до 150 записей.)\n")
    say("\nГОТОВО")
    say(f"Шарды: {present}/{len(shards)} | Чаты: {total} | Медиа: {assets.copied} | Изображений: {images}")
    say(f"Выходные файлы ChatGPT: ссылок найдено {generated_found}, отсутствует {generated_missing}")
    say(f"Откройте браузером: {DEST / 'index.html'}")
    if failures or assets.failed or assets.missing or assets.unresolved:
        say(f"Часть данных не обработана; подробности: {log_path}")
    return total


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        say(f"КРИТИЧЕСКАЯ ОШИБКА: {err}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    # При двойном щелчке Windows может закрыть окно до прочтения итогов.
    if os.name == "nt" and not os.environ.get("CHATGPT_ARCHIVE_BATCH") and sys.stdin and sys.stdin.isatty():
        try:
            input("\nНажмите Enter, чтобы закрыть окно...")
        except (EOFError, OSError):
            pass
