#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enable the recovery tab on an EXISTING archive; no chat conversion."""
import argparse
import os
from pathlib import Path
import re
import shutil
import sys


def enable(archive):
    archive=Path(archive).resolve()
    target=archive/'index.html'
    if not target.is_file():raise FileNotFoundError('No index.html in '+str(archive))
    before=target.read_text('utf-8')
    # Only the FILES tab needs an unsandboxed browser tab. Preserve the iframe
    # sandboxing used to render potentially untrusted chat content.
    after = re.sub(r'(<a\s+id="outputs-link"\s+href="generated_files\.html"\s+)target="chat_view"',
                   r'\1target="_blank" rel="noopener"', before, count=1)
    if after==before and 'id="outputs-link"' not in before:
        raise RuntimeError('Could not find Files ChatGPT tab in existing index.html')
    if after!=before:
        backup=archive/'index.before_recovery_upload.html'
        if not backup.exists():shutil.copy2(target,backup)
        temp=archive/'index.recovery.tmp'
        temp.write_text(after,encoding='utf-8')
        os.replace(temp,target)
    if not (archive/'generated_files_report.csv').is_file():
        raise RuntimeError('No generated_files_report.csv: build the archive first')
    print('RECOVERY TAB ENABLED: '+str(archive),flush=True)
    print('Open via run_open_archive.bat (http://127.0.0.1).',flush=True)
    print('The Files ChatGPT tab opens in a separate browser tab.',flush=True)


def main():
    p=argparse.ArgumentParser(description='Enable uploads for existing ChatGPT archive')
    p.add_argument('archive',nargs='?')
    args=p.parse_args()
    base=Path(__file__).resolve().parent
    archive=Path(args.archive) if args.archive else (base/'ChatGPT_Local_Archive' if (base/'ChatGPT_Local_Archive').exists() else base.parent/'ChatGPT_Local_Archive')
    try:enable(archive)
    except Exception as exc:
        print('ERROR:',exc,flush=True)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
