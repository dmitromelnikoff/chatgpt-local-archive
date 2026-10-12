"""Dependency-free smoke checks using a fabricated conversation, never user data.

The legacy source layout uses module-relative paths; we therefore run the real
build pipeline in a disposable copy of the release instead of monkey-patching
production constants or modifying a user's archive.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[1]


def synthetic_export():
    def message(msg_id, role, ts, text, *, content_type="text", channel="final"):
        return {
            "id": msg_id,
            "author": {"role": role, "name": None, "metadata": {}},
            "content": {"content_type": content_type, "parts": [text]},
            "create_time": ts,
            "metadata": {"channel": channel},
            "status": "finished_successfully",
        }

    user = message("user-fixture", "user", 1740000001, "Synthetic question: explain x^2")
    service = message(
        "recap-fixture", "assistant", 1740000002,
        "PRIVATE_SERVICE_TEXT_MUST_NOT_EXPORT", content_type="reasoning_recap", channel="summary",
    )
    assistant = message(
        "assistant-fixture", "assistant", 1740000003,
        "The answer is 42.\n\n$$E=mc^2$$\n\n```python\nprint(42)\n```",
    )
    return [
        {
            "id": "synthetic-demo-chat-001",
            "title": "Тестовый чат — Synthetic",
            "create_time": 1740000000,
            "update_time": 1740000004,
            "is_archived": True,
            "current_node": "answer",
            "mapping": {
                "root": {"id": "root", "message": None, "parent": None, "children": ["question"]},
                "question": {"id": "question", "message": user, "parent": "root", "children": ["recap"]},
                "recap": {"id": "recap", "message": service, "parent": "question", "children": ["answer"]},
                "answer": {"id": "answer", "message": assistant, "parent": "recap", "children": []},
            },
        }
    ]


class TestReleaseSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="chatgpt-archive-public-test-")
        cls.root = Path(cls.tmp.name)
        for source in REPO.iterdir():
            if source.is_file() and source.suffix in {".py", ".js", ".css", ".bat", ".sh", ".txt", ".json"}:
                shutil.copy2(source, cls.root / source.name)
            elif source.is_dir() and source.name in {"vendor", "viewer"}:
                shutil.copytree(source, cls.root / source.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (cls.root / "conversations-000.json").write_text(
            json.dumps(synthetic_export(), ensure_ascii=False), encoding="utf-8"
        )
        completed = subprocess.run(
            [sys.executable, "build_from_export.py"], cwd=cls.root,
            capture_output=True, text=True, timeout=90, encoding="utf-8", errors="replace",
        )
        if completed.returncode != 0:
            cls.tmp.cleanup()
            raise AssertionError(
                "Synthetic build failed (exit %s):\n%s\n%s" % (
                    completed.returncode, completed.stdout[-6000:], completed.stderr[-6000:]
                )
            )
        cls.archive = cls.root / "ChatGPT_Local_Archive"
        cls.server = None
        cls.thread = None

    @classmethod
    def tearDownClass(cls):
        if cls.server is not None:
            cls.server.shutdown()
            cls.thread.join(timeout=5)
            cls.server.server_close()
        cls.tmp.cleanup()

    def test_build_and_derived_metadata(self):
        self.assertTrue((self.archive / "index.html").is_file())
        self.assertTrue((self.archive / "generated_files.html").is_file())
        self.assertTrue((self.archive / "archive_calendar_stats.js").is_file())
        self.assertEqual((self.archive / "index.html").read_text(encoding="utf-8").count('data-archive-extra-actions="7.3.16"'), 1)
        data = json.loads((self.archive / "chat_metadata_index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["chats"]), 1)
        meta = data["chats"][0]
        self.assertEqual(meta["questions"], 1)
        self.assertEqual(meta["images"], 0)
        self.assertIs(meta["is_archived"], True)
        self.assertTrue(meta["source_ready"])
        md = (self.archive / "chat_exports" / (Path(meta["href"]).stem + ".md")).read_text(encoding="utf-8")
        self.assertIn("# Тестовый чат — Synthetic", md)
        self.assertIn("Synthetic question", md)
        self.assertIn("$$E=mc^2$$", md)
        self.assertIn("print(42)", md)
        self.assertNotIn("PRIVATE_SERVICE_TEXT_MUST_NOT_EXPORT", md)

    def test_build_refuses_existing_archive(self):
        result = subprocess.run(
            [sys.executable, "build_from_export.py"], cwd=self.root,
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 3, result.stdout[-2000:] + result.stderr[-2000:])

    def test_http_routes_and_markdown_download(self):
        # Import the server module from the disposable copy so it can resolve
        # all vendored/root-relative dependencies without any network access.
        sys.path.insert(0, str(self.root))
        try:
            from serve_archive import make_server
            if self.server is None:
                self.server, self.url = make_server(self.archive)
                self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self.thread.start()
            with urlopen(self.url, timeout=8) as res:
                page = res.read().decode("utf-8")
            self.assertIn("archive_calendar_stats.js", page)
            with urlopen(self.url.replace("index.html", "archive_chat_list_meta.js"), timeout=8) as res:
                self.assertIn("javascript", res.headers.get("Content-Type", "").lower())
                self.assertIn("chat_metadata_index.json", res.read().decode("utf-8"))
            metadata = json.loads((self.archive / "chat_metadata_index.json").read_text(encoding="utf-8"))
            stem = Path(metadata["chats"][0]["href"]).stem
            with urlopen(self.url.replace("index.html", "__chat_md_download/" + stem + ".md"), timeout=8) as res:
                downloaded = res.read().decode("utf-8")
                disposition = res.headers.get("Content-Disposition", "")
            self.assertIn("Synthetic question", downloaded)
            self.assertIn("filename*=UTF-8''", disposition)
            self.assertIn("%D0%A2", disposition)
            bad_url = self.url.replace(self.url.split("/")[3], "wrong-token", 1)
            with self.assertRaises(HTTPError) as e:
                urlopen(bad_url, timeout=8)
            self.assertEqual(e.exception.code, 404)
        finally:
            sys.path.remove(str(self.root))


if __name__ == "__main__":
    unittest.main()
