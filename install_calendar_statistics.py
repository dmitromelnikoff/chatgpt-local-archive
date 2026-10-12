#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install optional calendar/statistics navigation on an existing archive.

Modifies only index.html and writes two new static assets inside archive root.
Leaves all export JSON, chats, media, recovery files, server, and converter intact.
"""
import argparse
import shutil
from pathlib import Path

MARKER = 'data-archive-calendar-stats="1"'
STYLES = '<link rel="stylesheet" href="archive_calendar_stats.css" ' + MARKER + '>'
SCRIPT = '<script defer src="archive_calendar_stats.js" ' + MARKER + '></script>'

def main():
    ap=argparse.ArgumentParser(description='Install calendar/months and archive statistics')
    ap.add_argument('archive',nargs='?', help='Path to ChatGPT_Local_Archive')
    arg=ap.parse_args()
    root=Path(__file__).resolve().parent
    archive=(Path(arg.archive) if arg.archive else root / 'ChatGPT_Local_Archive').resolve()
    index=archive/'index.html'
    if not index.is_file():
        raise SystemExit('ОШИБКА: не найден index.html в '+str(archive))
    originals={n:root/n for n in ('archive_calendar_stats.js','archive_calendar_stats.css')}
    for n,src in originals.items():
        if not src.is_file(): raise SystemExit('ОШИБКА: отсутствует '+n+' рядом с установщиком')
    data=index.read_text(encoding='utf-8-sig')
    if 'const CHATS = ' not in data or 'id="list"' not in data:
        raise SystemExit('ОШИБКА: не узнаю структуру index.html. Никаких файлов не изменено.')
    if MARKER in data:
        print('Календарь и статистика уже подключены: index.html не изменяется.')
    else:
        i=data.lower().rfind('</body>')
        if i < 0: raise SystemExit('ОШИБКА: отсутствует </body> в index.html')
        backup=archive/'index.before_calendar_stats.html'
        if not backup.exists():
            shutil.copy2(index,backup)
        data=data[:i]+'\n'+STYLES+'\n'+SCRIPT+'\n'+data[i:]
        tmp=archive/'index.calendar_stats.tmp'
        tmp.write_text(data,encoding='utf-8')
        tmp.replace(index)
        print('Обновлён index.html. Резервная копия:',backup.name)
    for n,src in originals.items():
        dest=archive/n
        shutil.copy2(src,dest)
        print('Установлен:',dest.name)
    print('ГОТОВО. Перезапустите локальный сервер, откройте архив через 02_OPEN_ARCHIVE.bat')
    print('Если сервер уже работает, достаточно обновить index.html (Ctrl+F5).')
    return 0

if __name__=='__main__': raise SystemExit(main())
