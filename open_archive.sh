#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python3 serve_archive.py ChatGPT_Local_Archive "$@"
