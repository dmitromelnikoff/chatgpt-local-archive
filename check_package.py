#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Basic offline checks for the standalone frozen release; no source modification."""
from pathlib import Path
import importlib
import sys

ROOT=Path(__file__).resolve().parent
MODULES=('chatgpt_local_archive','archive_render_v7','archive_recovery','serve_archive',
         'recovery_source_links','intelligent_ui_markdown','dil_template_safe',
         'verify_archive_images','install_recovery','archive_chat_exports',
         'install_calendar_statistics','install_chat_actions','refresh_ui_only')
FILES=('build_from_export.py','01_BUILD_ARCHIVE.bat','02_OPEN_ARCHIVE.bat',
       'viewer/mathjax-tex-svg.js','intelligent_ui_toggle.js','copy_answers.js',
       'question_navigation.js','structured_blocks_toggle.js',
       'archive_calendar_stats.js','archive_calendar_stats.css',
       'archive_chat_actions.js','archive_chat_list_meta.js',
       '10_REFRESH_INTERFACE.bat',
       'full_files_recovery.js','full_files_recovery.css',
       'vendor/mistune/__init__.py','third_party_licenses/Mistune_BSD-3-Clause.txt','third_party_licenses/MathJax_APACHE-2.0.txt')

def main():
    bad=[]
    if sys.version_info < (3,9):bad.append('Требуется Python 3.9+')
    for name in FILES:
        if not (ROOT/name).is_file():bad.append('Отсутствует: '+name)
    sys.path.insert(0,str(ROOT))
    for name in MODULES:
        try:importlib.import_module(name)
        except Exception as exc:bad.append('Ошибка импорта '+name+': '+str(exc))
    if (ROOT/'ChatGPT_Local_Archive'/'index.html').is_file():
        print('Готовый архив обнаружен.')
    else:
        print('Готовый архив ещё не создан (это нормально при первой установке).')
    if not list(ROOT.glob('conversations-*.json')) and not (ROOT/'conversations.json').is_file():
        print('Исходные conversations-*.json не найдены — для конвертации положите их рядом с программой.')
    print('Проверено модулей:',len(MODULES),'проверено файлов:',len(FILES))
    for error in bad:print('ОШИБКА:',error)
    if not bad:print('КОМПЛЕКТ ПРОГРАММЫ ПОЛОН И ИМПОРТИРУЕТСЯ. Это не проверка полного архива.')
    return bool(bad)

if __name__=='__main__':raise SystemExit(main())
