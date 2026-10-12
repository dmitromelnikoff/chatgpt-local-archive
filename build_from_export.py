#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a fresh ChatGPT export into a local archive and enable recovery.

The source JSON and media are never edited. Refuses accidental rebuild of an
existing archive unless the operator passes --rebuild-after-backup.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import subprocess

BASE = Path(__file__).resolve().parent


def run(argv=None):
    p=argparse.ArgumentParser(description='Сборка зафиксированного локального архива ChatGPT')
    p.add_argument('--rebuild-after-backup',action='store_true',
                   help='Я вручную сохранил копию существующего архива и понимаю последствия пересборки')
    args=p.parse_args(argv)
    sys.path.insert(0,str(BASE))
    import chatgpt_local_archive as exporter
    import install_recovery
    import verify_archive_images

    shards=exporter.find_shards()
    if not shards:
        print('ОШИБКА: Не обнаружены conversations.json или conversations-000.json (и другие части).',flush=True)
        print('Распакуйте программу в папку ОРИГИНАЛЬНОГО экспорта OpenAI.',flush=True)
        return 2
    output=BASE/'ChatGPT_Local_Archive'
    if (output/'index.html').is_file() and not args.rebuild_after_backup:
        print('ОСТАНОВЛЕНО: архив уже существует:',output,flush=True)
        print('Повторная конвертация может переписать HTML и отчёты о восстановлении.',flush=True)
        print('Используйте 02_OPEN_ARCHIVE.bat, если нужно просто читать.',flush=True)
        print('Если действительно требуется полная пересборка: сохраните всю папку',flush=True)
        print('ChatGPT_Local_Archive и ChatGPT_Generated_Files, затем запустите',flush=True)
        print('python build_from_export.py --rebuild-after-backup',flush=True)
        return 3
    print('=== ChatGPT Local Archive STABLE v7.3.16.1 ===',flush=True)
    print('Источники:',len(shards),'файлов JSON',flush=True)
    if not (BASE/'library_files.json').is_file() and not (BASE/'library-files.json').is_file():
        print('ПРЕДУПРЕЖДЕНИЕ: library_files.json не найден — часть привязок и статусов недоступна.',flush=True)
    chats=exporter.main()
    if not isinstance(chats,int) or chats < 1 or not (output/'index.html').is_file():
        print('ОШИБКА: конвертация не создала пригодный архив.',flush=True)
        return 4
    print('Устанавливаем восстановление файлов в полный список…',flush=True)
    install_recovery.enable(output)
    print('Проверяем локальные пути изображений…',flush=True)
    counts,_=verify_archive_images.scan(output)
    print('Подключаем календарь и статистику…',flush=True)
    subprocess.run([sys.executable,str(BASE/'install_calendar_statistics.py')], cwd=str(BASE),check=True)
    print('Подключаем копирование, Markdown и метаданные чатов…',flush=True)
    subprocess.run([sys.executable,str(BASE/'install_chat_actions.py')], cwd=str(BASE),check=True)
    print('==================================================',flush=True)
    print('ГОТОВО. Чатов:',chats,flush=True)
    print('Изображений в чатах:',counts['img_tags_in_chats'],flush=True)
    print('Функции v7.3.16.1: календарь, статистика, копирование, Markdown, метаданные — подключены.',flush=True)
    print('Некорректных src (включая вложенные HTML в assets):',counts['missing'],flush=True)
    print('Для просмотра запустите 02_OPEN_ARCHIVE.bat.',flush=True)
    print('Полные отчёты — в ChatGPT_Local_Archive.',flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(run())
    except KeyboardInterrupt:
        print('\nПрервано пользователем. Возможно, архив создан частично.',flush=True)
        raise SystemExit(130)
    except Exception as exc:
        import traceback
        print('ОШИБКА:',exc,flush=True)
        traceback.print_exc()
        raise SystemExit(1)
