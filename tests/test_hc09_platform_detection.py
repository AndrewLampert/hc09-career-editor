import os
import tempfile
import unittest
from unittest import mock

import hc09_detect as detect


def mc02_save(table_count, padding=detect.MIN_SAVE_SIZE):
    database = b"DB" + (b"\x00" * 14) + int(table_count).to_bytes(4, "big")
    metadata = b"meta"
    header = bytearray(detect.MC02_HEADER_SIZE)
    header[:4] = detect.MC02_MAGIC
    header[8:12] = len(metadata).to_bytes(4, "big")
    body = bytes(header) + metadata + database
    return body + (b"\x00" * max(0, padding - len(body)))


class PlatformDetectionTests(unittest.TestCase):
    def test_xenia_save_is_found_only_under_the_hc09_title_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            xenia = os.path.join(folder, "Xenia")
            title = os.path.join(
                xenia, "content", "profile-1", detect.XENIA_TITLE_ID,
            )
            package = os.path.join(title, "00000001", "CAREER-Test")
            os.makedirs(package)
            save = os.path.join(package, "CAREER-Test")
            with open(save, "wb") as f:
                f.write(mc02_save(208))

            self.assertEqual(detect.xenia_dir_of(save), xenia)
            self.assertEqual(detect.title_folder_of(save), title)
            self.assertEqual(detect.classify_save(save), ("career", 208))
            found = detect.list_xenia_saves([xenia])
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["kind"], "career")
            self.assertEqual(found[0]["name"], "Test")

    def test_non_hc09_content_folder_is_not_mistaken_for_xenia(self):
        with tempfile.TemporaryDirectory() as folder:
            content = os.path.join(folder, "content", "profile-1", "12345678")
            os.makedirs(content)
            path = os.path.join(content, "save")
            with open(path, "wb") as f:
                f.write(mc02_save(208))
            self.assertIsNone(detect.xenia_dir_of(path))
            self.assertIsNone(detect.title_folder_of(path))

    def test_xenia_listing_skips_backup_and_bak_files(self):
        with tempfile.TemporaryDirectory() as folder:
            xenia = os.path.join(folder, "Xenia")
            title = os.path.join(xenia, "content", "profile", detect.XENIA_TITLE_ID)
            package = os.path.join(title, "00000001", "CAREER-Test")
            backup = os.path.join(title, detect.BACKUP_DIR_NAME)
            os.makedirs(package)
            os.makedirs(backup)
            save = os.path.join(package, "CAREER-Test")
            for path in (save, os.path.join(package, "old.bak"),
                         os.path.join(backup, "backup-save")):
                with open(path, "wb") as f:
                    f.write(mc02_save(208))
            found = detect.list_xenia_saves([xenia])
            self.assertEqual([item["path"] for item in found], [save])

    def test_mc02_reader_rejects_bad_magic_and_truncated_header(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = os.path.join(folder, "bad.mc02")
            short = os.path.join(folder, "short.mc02")
            with open(bad, "wb") as f:
                f.write(b"NOPE" + b"\x00" * 40)
            with open(short, "wb") as f:
                f.write(detect.MC02_MAGIC + b"\x00" * 4)
            self.assertIsNone(detect.mc02_db_start(bad))
            self.assertIsNone(detect.mc02_db_start(short))
            self.assertEqual(detect.classify_save(short), ("other", None))

    def test_recomp_install_is_found_from_a_nested_save_path(self):
        with tempfile.TemporaryDirectory() as folder:
            install = os.path.join(folder, "HC09Recomp")
            nested = os.path.join(install, "build", "userdata", "content")
            os.makedirs(nested)
            save = os.path.join(nested, "CAREER-Test")
            os.makedirs(save)
            ini = os.path.join(install, detect.TOOLS81_INI)
            with open(ini, "w", encoding="utf-8") as f:
                f.write("[Game]\nIsoPath=game.iso\n")
            self.assertEqual(detect.recomp_install_of(save), install)

    def test_recomp_iso_resolves_relative_and_quoted_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            install = os.path.join(folder, "install")
            os.makedirs(install)
            iso = os.path.join(install, "game image.iso")
            with open(iso, "wb") as f:
                f.write(b"image")
            with open(os.path.join(install, detect.TOOLS81_INI), "w", encoding="utf-8") as f:
                f.write("[Game]\nIsoPath=\"game image.iso\"\n")
            self.assertEqual(detect.recomp_iso(install), iso)

    def test_recomp_iso_returns_empty_for_missing_image(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, detect.TOOLS81_INI), "w", encoding="utf-8") as f:
                f.write("IsoPath=missing.iso\n")
            self.assertEqual(detect.recomp_iso(folder), "")


if __name__ == "__main__":
    unittest.main()
