"""Focused, private-data-free regression checks for public utility functions."""
import re
import unittest

from archive_chat_exports import archive_state, is_service
from chatgpt_local_archive import asset_key, safe_name
from serve_archive import chat_download_filename


class TestArchiveHelpers(unittest.TestCase):
    def test_file_id_normalization(self):
        expected = "file_abcdef012345"
        for raw in ("file-service://file-ABCDEF012345", "file-ABCDEF012345.dat", "file_ABCDEF012345"):
            self.assertEqual(asset_key(raw), expected)

    def test_windows_safe_titles(self):
        filename = chat_download_filename("# Пример: диалог?*\n\nТекст", "technical")
        self.assertTrue(filename.startswith("Пример_ диалог"))
        self.assertTrue(filename.endswith(".md"))
        self.assertIsNone(re.search(r'[<>:"/\\|?*]', filename))
        self.assertEqual(chat_download_filename("# CON\n", "technical"), "_CON.md")
        self.assertEqual(chat_download_filename("not a heading", "technical"), "technical.md")

    def test_archive_flag_requires_source_boolean(self):
        self.assertIs(archive_state({"is_archived": True}), True)
        self.assertIs(archive_state({"is_archived": False}), False)
        self.assertIs(archive_state({"is_archived": "false"}), None)
        self.assertIs(archive_state({"metadata": {"is_archived": True}}), True)
        self.assertIs(archive_state({}), None)

    def test_service_messages_excluded(self):
        normal = {"author": {"role": "assistant"}, "content": {"content_type": "text", "parts": ["Hello"]}}
        self.assertFalse(is_service(normal))
        self.assertTrue(is_service({**normal, "metadata": {"channel": "analysis"}}))
        self.assertTrue(is_service({**normal, "content": {"content_type": "reasoning_recap"}}))
        self.assertTrue(is_service({**normal, "author": {"role": "tool"}}))

    def test_filename_helpers_preserve_safe_names(self):
        self.assertEqual(safe_name("image.png"), "image.png")
        self.assertEqual(safe_name("CON.txt"), "_CON.txt")
        self.assertNotIn("/", safe_name("test/name?.txt"))


if __name__ == "__main__":
    unittest.main()
