import os
import struct
import tempfile
import unittest

import hc09_iso


class RecompIsoWriteTests(unittest.TestCase):
    def make_image(self, path):
        sector = hc09_iso.SECTOR
        name = b"qkl_boot.ast"
        entry = struct.pack("<HHIIBB", 0xFFFF, 0xFFFF, 34, 3, 0, len(name)) + name
        entry += b"\xFF" * ((-len(entry)) % 4)
        image = bytearray(35 * sector)
        descriptor = 32 * sector
        image[descriptor:descriptor + len(hc09_iso.MAGIC)] = hc09_iso.MAGIC
        struct.pack_into("<II", image, descriptor + len(hc09_iso.MAGIC), 33, len(entry))
        image[33 * sector:33 * sector + len(entry)] = entry
        image[34 * sector:34 * sector + 3] = b"old"
        with open(path, "wb") as f:
            f.write(image)

    def test_replace_appends_archive_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            replacement = os.path.join(folder, "qkl_boot.ast")
            output = os.path.join(folder, "modified.iso")
            self.make_image(source)
            with open(replacement, "wb") as f:
                f.write(b"new archive bytes")
            with open(source, "rb") as f:
                original = f.read()

            hc09_iso.replace_file(source, "qkl_boot.ast", replacement, output)

            self.assertEqual(hc09_iso.find(output, "qkl_boot.ast")[2], len(b"new archive bytes"))
            off, sector, size = hc09_iso.find(output, "qkl_boot.ast")
            with open(output, "rb") as f:
                f.seek(off + sector * hc09_iso.SECTOR)
                self.assertEqual(f.read(size), b"new archive bytes")
            with open(source, "rb") as f:
                self.assertEqual(f.read(), original)

    def test_refuses_to_overwrite_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            replacement = os.path.join(folder, "qkl_boot.ast")
            self.make_image(source)
            with open(replacement, "wb") as f:
                f.write(b"new")
            with self.assertRaises(ValueError):
                hc09_iso.replace_file(source, "qkl_boot.ast", replacement, source)


if __name__ == "__main__":
    unittest.main()
