import os
import struct
import tempfile
import unittest

import hc09_iso


class RecompIsoSafetyTests(unittest.TestCase):
    def make_image(self, path, size=3):
        name = b"qkl_boot.ast"
        entry = struct.pack("<HHIIBB", 0xFFFF, 0xFFFF, 34, size, 0, len(name)) + name
        entry += b"\xFF" * ((-len(entry)) % 4)
        image = bytearray(35 * hc09_iso.SECTOR)
        descriptor = 32 * hc09_iso.SECTOR
        image[descriptor:descriptor + len(hc09_iso.MAGIC)] = hc09_iso.MAGIC
        struct.pack_into("<II", image, descriptor + len(hc09_iso.MAGIC), 33, len(entry))
        image[33 * hc09_iso.SECTOR:33 * hc09_iso.SECTOR + len(entry)] = entry
        image[34 * hc09_iso.SECTOR:34 * hc09_iso.SECTOR + 3] = b"old"
        with open(path, "wb") as f:
            f.write(image)

    def test_find_rejects_non_xbox_image(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "not-an-iso.bin")
            with open(path, "wb") as f:
                f.write(b"not an xbox image")
            with self.assertRaisesRegex(ValueError, "not an Xbox 360 disc image"):
                hc09_iso.find(path, "qkl_boot.ast")

    def test_extract_rejects_truncated_file_without_leaving_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            output = os.path.join(folder, "nested", "qkl_boot.ast")
            self.make_image(source, size=5000)
            with self.assertRaisesRegex(ValueError, "ends before qkl_boot.ast"):
                hc09_iso.extract(source, "qkl_boot.ast", output)
            self.assertFalse(os.path.exists(output))
            self.assertFalse(os.path.exists(os.path.dirname(output)))

    def test_extract_creates_parent_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            output = os.path.join(folder, "new", "folder", "qkl_boot.ast")
            self.make_image(source)
            progress = []
            self.assertEqual(
                hc09_iso.extract(source, "QKL_BOOT.AST", output,
                                 lambda done, total: progress.append((done, total))),
                3,
            )
            with open(output, "rb") as f:
                self.assertEqual(f.read(), b"old")
            self.assertEqual(progress[-1], (3, 3))
            self.assertEqual(os.listdir(os.path.dirname(output)), ["qkl_boot.ast"])

    def test_replace_rejects_empty_archive_without_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            replacement = os.path.join(folder, "empty.ast")
            output = os.path.join(folder, "modified.iso")
            self.make_image(source)
            with open(replacement, "wb"):
                pass
            with self.assertRaisesRegex(ValueError, "unsupported size"):
                hc09_iso.replace_file(source, "qkl_boot.ast", replacement, output)
            self.assertFalse(os.path.exists(output))


if __name__ == "__main__":
    unittest.main()
