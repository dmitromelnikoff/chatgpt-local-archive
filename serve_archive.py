#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Private local ChatGPT archive viewer with optional user-file recovery.

Python standard library only. HTTP binds to 127.0.0.1 with a random per-run
capability token. Uploaded files never leave the local computer.
"""
import argparse
import http.server
import json
import os
from pathlib import Path
import secrets
import threading
import urllib.parse
import webbrowser
from functools import partial
from archive_recovery import RecoveryManager, DANGEROUS_BROWSER
import re
import unicodedata


def chat_download_filename(markdown, fallback_stem):
    """Return a Windows-safe title.md, without changing archive or MD data."""
    first = markdown.lstrip('\ufeff').split('\n', 1)[0].rstrip('\r')
    title = first[2:] if first.startswith('# ') else fallback_stem
    title = unicodedata.normalize('NFC', title.strip())
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', title)
    title = re.sub(r'\s+', ' ', title).rstrip(' .')[:120].rstrip(' .')
    if not title:
        title = fallback_stem
    if re.match(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', title, re.I):
        title = '_' + title
    return title + '.md'



class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, token=None, recovery=None, chat_meta=None, **kwargs):
        self.token = token
        self.recovery = recovery
        self.chat_meta = chat_meta or {}
        self.original_unprefixed_path = ''
        super().__init__(*args, directory=directory, **kwargs)

    def _with_prefix(self):
        path = urllib.parse.urlsplit(self.path).path
        prefix = '/' + self.token
        if path == prefix:
            path = prefix + '/index.html'
        if not path.startswith(prefix + '/'):
            self.send_error(404, 'Not found')
            return False
        self.path = path[len(prefix):] or '/index.html'
        self.original_unprefixed_path = self.path
        return True

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._with_prefix():return
        if self.path == '/__recovery/api/list':
            self._json(200, self.recovery.list())
            return
        if self.path == '/__recovery/api/full-list':
            self._json(200, self.recovery.full_list())
            return
        if self.path in ('/__recovery/full_files_recovery.js', '/__recovery/full_files_recovery.css'):
            name = self.path.rsplit('/', 1)[-1]
            source = Path(__file__).resolve().parent / name
            if not source.is_file():
                self.send_error(404, 'Recovery UI asset missing')
                return
            data = source.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == '/__intelligent_ui_toggle.js':
            source = Path(__file__).resolve().parent / 'intelligent_ui_toggle.js'
            if not source.is_file():
                self.send_error(404, 'Intelligent UI toggle missing')
                return
            data = source.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type','text/javascript; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith('/__intelligent_ui_markdown/'):
            # Markdown mode in a sandboxed iframe cannot use fetch(). Return
            # inert, pre-sanitized HTML as a JS callback through the token URL.
            # The original MathJax scripts/settings and all chat HTML are intact.
            import re
            name = self.path.rsplit('/', 1)[-1]
            if not re.fullmatch(r'chat_\d{7}_[0-9a-f]{8}_ui_\d{4}\.txt', name):
                self.send_error(404, 'Markdown source not found')
                return
            path = (self.recovery.archive / 'dil_sources' / name).resolve()
            try:
                path.relative_to(self.recovery.archive.resolve())
            except ValueError:
                self.send_error(404, 'Markdown source not found')
                return
            if not path.is_file():
                self.send_error(404, 'Markdown source not found')
                return
            if path.stat().st_size > 2_000_000:
                arguments = (json.dumps(name), 'null', 'null', json.dumps('Source larger than 2 MB'), 'null')
            else:
                try:
                    from intelligent_ui_markdown import render_ui_variants
                    html_output, markdown_output, enhanced = render_ui_variants(
                        path.read_text(encoding='utf-8', errors='replace'),self.recovery.archive,name)
                    arguments = (json.dumps(name), json.dumps(html_output, ensure_ascii=True),
                                 json.dumps(markdown_output, ensure_ascii=True), 'null',
                                 json.dumps(enhanced, ensure_ascii=True))
                except Exception:
                    import traceback
                    traceback.print_exc()
                    arguments = (json.dumps(name), 'null', 'null', json.dumps('Markdown rendering failed'), 'null')
            code = 'window.__archiveIntelligentUiMarkdownLoaded(' + ','.join(arguments) + ');'
            data = code.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','text/javascript; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith('/__intelligent_ui_source/'):
            # The sandboxed viewer has an opaque origin: fetch() fails under CORS.
            # Send an inert JSON-string value as executable JS from this private,
            # token-scoped route. The client inserts it only as textContent.
            import re
            name = self.path.rsplit('/', 1)[-1]
            if not re.fullmatch(r'chat_\d{7}_[0-9a-f]{8}_ui_\d{4}\.txt', name):
                self.send_error(404, 'Source not found')
                return
            path = (self.recovery.archive / 'dil_sources' / name).resolve()
            try:
                path.relative_to(self.recovery.archive.resolve())
            except ValueError:
                self.send_error(404, 'Source not found')
                return
            if not path.is_file():
                self.send_error(404, 'Source not found')
                return
            if path.stat().st_size > 2_000_000:
                code = ('window.__archiveIntelligentUiSourceLoaded(' + json.dumps(name) +
                        ',null,"Source larger than 2 MB: use the original TXT link");')
            else:
                raw = path.read_text(encoding='utf-8', errors='replace')
                code = ('window.__archiveIntelligentUiSourceLoaded(' + json.dumps(name) +
                        ',' + json.dumps(raw, ensure_ascii=True) + ',null);')
            data = code.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','text/javascript; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == '/__structured_blocks_toggle.js':
            # Per-chat switch; hides only existing service JSON blocks.
            # No disk HTML changes, and it does not affect uploads or copy UI.
            source = Path(__file__).resolve().parent / 'structured_blocks_toggle.js'
            if not source.is_file():
                self.send_error(404, 'Structured toggle asset missing')
                return
            data = source.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == '/__question_navigation.js':
            # Read-only prompt navigation inside the sandboxed chat iframe.
            source = Path(__file__).resolve().parent / 'question_navigation.js'
            if not source.is_file():
                self.send_error(404, 'Question navigation asset missing')
                return
            data = source.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == '/archive_chat_list_meta.js':
            # v7.3.16 index.html loads this URL relative to the generated
            # archive, but the installed JS lives beside serve_archive.py.
            # Serve it explicitly rather than duplicating it into the archive.
            script = Path(__file__).resolve().parent / 'archive_chat_list_meta.js'
            if not script.is_file():
                self.send_error(404, 'Chat list metadata script not installed')
                return
            data = script.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == '/__chat_actions.js':
            source = Path(__file__).resolve().parent / 'archive_chat_actions.js'
            if not source.is_file():
                self.send_error(404, 'Chat actions missing');return
            data=source.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type','text/javascript; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data);return
        if self.path.startswith('/__chat_md_data/') or self.path.startswith('/__chat_md_download/'):
            import re
            is_script=self.path.startswith('/__chat_md_data/')
            name=self.path.rsplit('/',1)[-1]
            if is_script:
                if not re.fullmatch(r'chat_\d{7}_[a-f0-9]{8}\.js',name):
                    self.send_error(404,'Unknown chat');return
                stem=name[:-3]
            else:
                if not re.fullmatch(r'chat_\d{7}_[a-f0-9]{8}\.md',name):
                    self.send_error(404,'Unknown chat');return
                stem=name[:-3]
            path=self.recovery.archive/'chat_exports'/(stem+'.md')
            if not path.is_file():
                if is_script:
                    code='window.__archiveChatMarkdown=null;'
                    data=code.encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type','text/javascript; charset=utf-8')
                    self.send_header('Content-Length',str(len(data)))
                    self.end_headers();self.wfile.write(data);return
                self.send_error(404,'Original conversation Markdown unavailable');return
            try:
                from archive_chat_exports import resolved_markdown
                source_md=path.read_text(encoding='utf-8')
                source_md=resolved_markdown(self.recovery.archive,'chats/'+stem+'.html',
                                            source_md,self.recovery.registry())
            except (OSError,ValueError):
                self.send_error(500,'Markdown data unreadable');return
            if is_script:
                code='window.__archiveChatMarkdown='+json.dumps(source_md,ensure_ascii=True).replace('<','\\u003c')+';'
                data=code.encode('utf-8')
                mimetype='text/javascript; charset=utf-8'
            else:
                data=source_md.encode('utf-8')
                mimetype='text/markdown; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type',mimetype)
            if not is_script:
                # Preserve the REAL conversation title (including Cyrillic)
                # using RFC 5987; don't expose the technical chat_... filename.
                friendly_name=chat_download_filename(source_md, stem)
                self.send_header('Content-Disposition',
                                 'attachment; filename="chat.md"; filename*=UTF-8\'\''
                                 + urllib.parse.quote(friendly_name, safe=''))
            self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data);return
        if self.path == '/__copy_answers.js':
            # Attach one copy action to each assistant reply at display time.
            # Leave the multi-gigabyte source export and every chat HTML untouched.
            source = Path(__file__).resolve().parent / 'copy_answers.js'
            if not source.is_file():
                self.send_error(404, 'Copy UI asset missing')
                return
            data = source.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith('/chats/chat_') and self.path.endswith('.html'):
            # Runtime injection avoids rewriting already repaired/recovered chats.
            # Only the strict generated chat filename pattern is accepted.
            import re
            if re.fullmatch(r'/chats/chat_\d{7}_[0-9a-f]{8}\.html', self.path):
                page_path = (self.recovery.archive / self.path.lstrip('/')).resolve()
                try:
                    page_path.relative_to(self.recovery.archive)
                except ValueError:
                    self.send_error(404, 'Chat not found')
                    return
                if not page_path.is_file():
                    self.send_error(404, 'Chat not found')
                    return
                source_html = page_path.read_text(encoding='utf-8-sig')
                tag = ('<script defer src="../__copy_answers.js"></script>'
                       '<script defer src="../__question_navigation.js"></script>'
                       '<script defer src="../__structured_blocks_toggle.js"></script>'
                       '<script defer src="../__intelligent_ui_toggle.js"></script>'
                       '<script defer src="../__chat_actions.js"></script>')
                low = source_html.lower()
                position = low.rfind('</body>')
                # Add the REAL original ID, never an inferred ID from filename.
                original_id=(self.chat_meta.get('chats/'+self.path.rsplit('/',1)[-1]) or {}).get('conversation_id','')
                if not (isinstance(original_id,str) and __import__('re').fullmatch(r'[A-Za-z0-9_-]{8,128}',original_id)):
                    original_id=''
                safe_id=json.dumps(original_id,ensure_ascii=True).replace('<','\\u003c')
                tag += ('<script>window.__archiveOriginalConversationId='+safe_id+';</script>'
                        '<script defer src="../__chat_md_data/'+self.path.rsplit('/',1)[-1][:-5]+'.js"></script>')
                if position >= 0:
                    source_html = source_html[:position] + tag + source_html[position:]
                else:
                    source_html += tag
                data = source_html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        if self.path == '/generated_files.html':
            # IMPORTANT: preserve the original full generated_files.html list.
            # v7.3 mistakenly substituted a totally different list (first 200).
            # Add buttons only via a separate JS asset: the disk HTML is unchanged.
            full_page = self.recovery.archive / 'generated_files.html'
            if not full_page.is_file():
                self.send_error(404, 'Original generated_files.html missing')
                return
            original = full_page.read_text(encoding='utf-8-sig')
            inject = ('<link rel="stylesheet" href="__recovery/full_files_recovery.css">'
                      '<script defer src="__recovery/full_files_recovery.js"></script>')
            if '</html>' in original.lower():
                pos = original.lower().rfind('</html>')
                page = original[:pos] + inject + original[pos:]
            else:
                page = original + inject
            data = page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_HEAD(self):
        if not self._with_prefix():return
        if self.path.startswith('/__recovery/'):
            self.send_error(405, 'Not available via HEAD')
            return
        super().do_HEAD()

    def do_POST(self):
        if not self._with_prefix():return
        if not self.path.startswith('/__recovery/api/upload/'):
            self._json(404, {'error':'Unknown upload destination'});return
        origin = self.headers.get('Origin')
        # Browser in the main archive page has a proper same-origin Origin;
        # open the recovery screen in its own tab, NOT opaque sandboxed iframe.
        local_origin='http://127.0.0.1:'+str(self.server.server_port)
        if origin and origin != local_origin:
            self._json(403, {'error':'Only this local archive can upload files'});return
        if self.headers.get('Content-Type','').split(';')[0].lower() != 'application/octet-stream':
            self._json(415, {'error':'Expected raw file upload'});return
        try:
            length=int(self.headers.get('Content-Length',''))
            key=self.path.rsplit('/',1)[-1]
            if not (key.startswith('id_') or key.startswith('ref_')) or len(key)>80:
                raise ValueError('Invalid recovery ID')
            name=urllib.parse.unquote(self.headers.get('X-Original-Filename',''))
            result=self.recovery.recover(key, name, length, self.rfile)
            self._json(200,result)
        except (ValueError, FileNotFoundError, OSError) as e:
            self._json(400, {'error':str(e)})
        except Exception:
            self._json(500, {'error':'Unexpected error during recovery; see server console'})
            import traceback
            traceback.print_exc()

    def list_directory(self,path):
        self.send_error(403, 'Directory listings disabled')
        return None

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        # User HTML/JS/SVG from archive assets is never served as active content.
        if self.original_unprefixed_path.startswith('/assets/') and Path(self.original_unprefixed_path).suffix.lower() in DANGEROUS_BROWSER:
            self.send_header('Content-Disposition','attachment')
            self.send_header('Content-Security-Policy',"sandbox; default-src 'none'; script-src 'none'")
        super().end_headers()

    def log_message(self, format, *args):
        # Avoid echoing private chat names or paths in console.
        pass


def make_server(archive, port=0):
    archive = Path(archive).resolve()
    if not (archive / 'index.html').is_file():
        raise FileNotFoundError('index.html not found in '+str(archive))
    recovery = RecoveryManager(archive)
    # v7.3/v7.3.1 placed uploaded cards as a third CSS-grid child. Repair
    # EXISTING uploads once on startup, including original image/download
    # placeholders. No re-upload or full JSON conversion is necessary.
    registry = recovery.registry()
    if registry:
        try:
            with recovery.lock:
                recovery._patch_chats(registry)
        except (OSError, ValueError) as exc:
            # Don't lock the user out of the archive if one HTML was damaged.
            print('WARNING: automatic recovery repair:', exc, flush=True)
    metadata_path=archive/'chat_metadata_index.json'
    try:
        metadata=json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.is_file() else {}
        chat_meta={v['href']:v for v in metadata.get('chats',[]) if isinstance(v,dict) and 'href' in v}
    except (OSError,ValueError):chat_meta={}
    token=secrets.token_urlsafe(24)
    handler=partial(ViewerHandler,directory=str(archive),token=token,
                    recovery=recovery,chat_meta=chat_meta)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',port),handler)
    url='http://127.0.0.1:%d/%s/index.html' % (server.server_port,token)
    return server,url


def main():
    parser=argparse.ArgumentParser(description='Open a private ChatGPT archive in browser')
    parser.add_argument('archive', nargs='?', help='Archive directory')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    base=Path(__file__).resolve().parent
    archive=Path(args.archive) if args.archive else (base if (base/'index.html').exists() else base/'ChatGPT_Local_Archive')
    try:server,url=make_server(archive,args.port)
    except (OSError,ValueError) as exc:
        print('ERROR:',exc,flush=True);return 1
    print('Private ChatGPT archive — local-only server',flush=True)
    print('Folder:',Path(archive).resolve(),flush=True)
    print('Open:',url,flush=True)
    print('Original full Files ChatGPT list preserved; missing rows have Restore buttons.',flush=True)
    print('Keep this window open. Ctrl+C to stop.',flush=True)
    if not args.no_browser:
        threading.Timer(0.5,webbrowser.open,args=(url,)).start()
    try:server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
