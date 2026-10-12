#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enable chat actions and metadata on an already built archive.

Final unified v7.3.16.1: application modules are included directly in the
root directory; unlike the historical add-on, no stale modules are copied.
No source export or chat HTML is modified.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
MARK='data-archive-extra-actions="7.3.16"'
SCRIPT='\n<script defer src="archive_chat_list_meta.js" '+MARK+'></script>\n'
REQUIRED=('serve_archive.py','archive_chat_exports.py','archive_chat_actions.js','archive_chat_list_meta.js')


def main(argv=None):
    parser=argparse.ArgumentParser(description='Включить копирование, Markdown и метаданные v7.3.16.1')
    parser.add_argument('--skip-index',action='store_true',help='Не обновлять подготовленные Markdown и метаданные')
    args=parser.parse_args(argv)
    archive=ROOT/'ChatGPT_Local_Archive'
    page=archive/'index.html'
    if not page.is_file():raise SystemExit('Ошибка: сначала нужно создать ChatGPT_Local_Archive/index.html')
    for name in REQUIRED:
        if not (ROOT/name).is_file():raise SystemExit('Ошибка: нет модуля '+name)
    html=page.read_text(encoding='utf-8-sig')
    if 'const CHATS = ' not in html or 'id="list"' not in html:
        raise SystemExit('Ошибка: неизвестный HTML-индекс — изменения не внесены')
    changed=False
    if MARK not in html:
        p=html.lower().rfind('</body>')
        if p<0:raise SystemExit('Ошибка: в индексе нет </body>')
        html=html[:p]+SCRIPT+html[p:]
        changed=True
    old='sandbox="allow-scripts allow-downloads allow-popups"'
    new='sandbox="allow-scripts allow-downloads allow-popups allow-popups-to-escape-sandbox"'
    if old in html:
        html=html.replace(old,new,1)
        changed=True
    if changed:
        backup=archive/'index.before_v7316.html'
        if not backup.exists():shutil.copy2(page,backup)
        temp=archive/'index.chat_actions.tmp'
        temp.write_text(html,encoding='utf-8')
        temp.replace(page)
        print('Действия чатов подключены к главной странице.',flush=True)
    else:
        print('Действия чатов уже подключены.',flush=True)
    if args.skip_index:
        if not (archive/'chat_metadata_index.json').is_file():
            print('ВНИМАНИЕ: индекс метаданных отсутствует.',flush=True)
    else:
        from archive_chat_exports import make_index
        print('Создаём индекс чатов и Markdown из исходного экспорта. Это может занять время…',flush=True)
        make_index(root=ROOT,archive=archive)
    print('Готово: метаданные и Markdown v7.3.16.1.',flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)
    except Exception as exc:
        import traceback;traceback.print_exc()
        raise SystemExit('Ошибка: '+str(exc))
