#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix chat placement for ALREADY uploaded recovery files (no re-upload)."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
from archive_recovery import RecoveryManager, existing_asset


def main():
    parser=argparse.ArgumentParser(description='Repair existing recovered-file links in local ChatGPT archive')
    parser.add_argument('archive', nargs='?', help='ChatGPT_Local_Archive directory')
    args=parser.parse_args()
    base=Path(__file__).resolve().parent
    dest=Path(args.archive) if args.archive else (
        base/'ChatGPT_Local_Archive' if (base/'ChatGPT_Local_Archive'/'index.html').is_file()
        else base.parent/'ChatGPT_Local_Archive')
    if not (dest/'index.html').is_file():
        print('ОШИБКА: Не найден index.html в', dest, flush=True)
        return 1
    manager=RecoveryManager(dest)
    registry=manager.registry()
    if not registry:
        print('Восстановленных файлов пока нет (recovered_files.json пуст или отсутствует).', flush=True)
        return 0
    paths=set()
    for rec in registry.values():
        for href in rec.get('hrefs') or [rec.get('href')]:
            if href and re.fullmatch(r'chats/[a-zA-Z0-9_.-]+\.html',href):
                paths.add(href)
    before={}
    for href in paths:
        path=manager.archive/href
        if path.is_file():before[href]=path.read_bytes()
    with manager.lock:
        manager._patch_chats(registry)
    changed=[href for href, data in before.items() if (manager.archive/href).read_bytes()!=data]
    missing=[rec.get('asset_name') for rec in registry.values() if
             not existing_asset(manager.assets,rec.get('asset_name'))]
    total=sum(bool(rec.get('asset_name')) for rec in registry.values())
    lines=[
        'ChatGPT Archive — recovery HTML repair',
        'Файлов в реестре: '+str(len(registry)),
        'Записей с локальным asset: '+str(total),
        'Затронутых страниц чатов: '+str(len(paths)),
        'Изменено страниц: '+str(len(changed)),
        'Файлов реестра без asset: '+str(len(missing)),
        'Никакой полной обработки conversations-*.json не выполнялось.',
        'В исходном generated_files.html ничего не изменялось.',
    ]
    if changed:lines.append('Обновлены чаты: '+', '.join(sorted(changed)))
    if missing:lines.append('Отсутствуют на диске: '+', '.join(str(x) for x in missing[:15]))
    report=manager.archive/'recovery_html_repair_report.txt'
    report.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines),flush=True)
    print('Отчёт:',report,flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
