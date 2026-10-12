#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check each image src in exported HTML against an actual file, without editing.

Produces image_paths_summary.txt and image_paths_missing.csv. Pure stdlib.
"""
import argparse
import csv
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import html

class ImageScanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'img':
            src = dict(attrs).get('src')
            if src: self.images.append(src)
    handle_startendtag = handle_starttag


def signature_valid(path):
    ext = path.suffix.casefold()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'):
        return True  # unknown/other format: cannot verify with a minimal signature
    try:
        with path.open('rb') as f: head = f.read(20)
    except OSError:
        return False
    return {
      '.png':lambda b:b.startswith(b'\x89PNG\r\n\x1a\n'),
      '.jpg':lambda b:b.startswith(b'\xff\xd8\xff'),
      '.jpeg':lambda b:b.startswith(b'\xff\xd8\xff'),
      '.webp':lambda b:b.startswith(b'RIFF') and b[8:12]==b'WEBP',
      '.gif':lambda b:b.startswith((b'GIF87a', b'GIF89a')),
      '.bmp':lambda b:b.startswith(b'BM'),
    }[ext](head)


def scan(archive):
    archive = Path(archive).resolve()
    counts=Counter()
    assets_dir=archive/'assets'
    if assets_dir.is_dir():
        counts['asset_images_on_disk']=sum(1 for file in assets_dir.iterdir() if file.is_file() and file.suffix.casefold() in ('.png','.jpg','.jpeg','.webp','.gif','.bmp','.svg','.avif'))
    missing=[]
    examples=[]
    for page in archive.rglob('*.html'):
        counts['html_scanned']+=1
        try:
            parser=ImageScanner()
            parser.feed(page.read_text(encoding='utf-8', errors='replace'))
            parser.close()
        except (OSError,ValueError) as exc:
            missing.append([str(page.relative_to(archive)), '', 'HTML_READ_ERROR',str(exc)])
            continue
        for src in parser.images:
            counts['img_tags']+=1
            if 'chats' in page.relative_to(archive).parts:
                counts['img_tags_in_chats']+=1
            elif 'gallery' in page.relative_to(archive).parts:
                counts['img_tags_in_gallery']+=1
            u=urlsplit(html.unescape(src))
            if u.scheme or u.netloc or src.startswith('//'):
                counts['remote_or_absolute']+=1
                continue
            # Check a single decode, as a browser would. Avoid decoding %2520 as space.
            dest=(page.parent / unquote(u.path)).resolve()
            if not dest.is_relative_to(archive):
                counts['outside_archive']+=1
                missing.append([str(page.relative_to(archive)),src,'PATH_ESCAPE','outside output'])
                continue
            if not dest.is_file():
                counts['missing']+=1
                missing.append([str(page.relative_to(archive)),src,'NOT_FOUND',str(dest)])
            elif dest.stat().st_size == 0 or not signature_valid(dest):
                counts['invalid_signature']+=1
                missing.append([str(page.relative_to(archive)),src,'INVALID_CONTENT',str(dest)])
            else:
                counts['existing']+=1
    with (archive/'image_paths_missing.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,delimiter=';')
        writer.writerow(['html_file','src','problem','path'])
        writer.writerows(missing)
    lines=['ChatGPT Local Archive — image path audit',
           'HTML pages scanned: '+str(counts['html_scanned']),
           'Asset images physically on disk: '+str(counts['asset_images_on_disk']),
           'Image tags in chats: '+str(counts['img_tags_in_chats']),
           'Image tags in gallery: '+str(counts['img_tags_in_gallery']),
           'Total image tags: '+str(counts['img_tags']),
           'Images with valid existing local files: '+str(counts['existing']),
           'Broken/missing local paths: '+str(counts['missing']),
           'Invalid image signatures or zero bytes: '+str(counts['invalid_signature']),
           'Paths escaping output directory: '+str(counts['outside_archive']),
           'Remote or absolute sources (not verified): '+str(counts['remote_or_absolute']),
           '',
           'If broken paths = 0 but images are absent in the browser:',
           'do NOT open index.html as file://. Use run_open_archive.bat (http://127.0.0.1).',
           'If chat image tags = 0 but gallery images exist, this is an attachment-binding/rendering problem, not a path problem.',
           'This check cannot detect a picture omitted from HTML altogether.',
           'Details: image_paths_missing.csv']
    (archive/'image_paths_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return counts, lines


def main():
    parser=argparse.ArgumentParser(description='Verify local image URLs in generated ChatGPT HTML')
    parser.add_argument('archive',nargs='?')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    archive=Path(args.archive) if args.archive else (root if (root/'index.html').exists() else root/'ChatGPT_Local_Archive')
    if not (archive/'index.html').is_file():
        print('ERROR: no ChatGPT_Local_Archive/index.html at',archive)
        return 1
    _,lines=scan(archive)
    print('\n'.join(lines),flush=True)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
