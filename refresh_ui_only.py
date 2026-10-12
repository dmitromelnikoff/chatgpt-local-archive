#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply the stable viewer controls to a previously converted archive.
Does not rebuild conversations, touch source JSON or re-upload files.
The derived Markdown/metadata index is refreshed from the original export.
"""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    output=ROOT/'ChatGPT_Local_Archive'
    if not (output/'index.html').is_file():
        print('Ошибка: готовый архив отсутствует. Для новой установки выполните 01_BUILD_ARCHIVE.bat',flush=True)
        return 2
    jobs=('install_recovery.py','install_calendar_statistics.py','install_chat_actions.py')
    for job in jobs:
        print('\n== Включаем',job,'==',flush=True)
        subprocess.run([sys.executable,str(ROOT/job)],cwd=str(ROOT),check=True)
    print('\nГОТОВО. HTML чатов и восстановленные файлы не менялись.',flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)
    except Exception as exc:
        import traceback;traceback.print_exc()
        raise SystemExit(1)
