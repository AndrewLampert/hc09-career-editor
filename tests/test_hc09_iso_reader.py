import os
import struct
import tempfile
import unittest

import hc09_iso


def directory_entry(name, sector, size, directory=False, left=0xFFFF, right=0xFFFF):
    raw_name = name.encode("latin-1")
    raw = struct.pack(
        "<HHIIBB", left, right, sector, size,
        hc09_iso.DIRECTORY if directory else 0, len(raw_name),
    ) + raw_name
    return raw + b"\xFF" * ((-len(raw)) % 4)


class XdvdfsReaderTests(unittest.TestCase):
    def make_image(self, path):
        nested = directory_entry("inside.dat", 36, 5)\n        root = directory_entry("folder", 34, len(nested), directory=True, right=5)
        root += directory_entry("root.bin", 35, 4)
        nested = directory_entry("inside.dat", 36, 5)
        image = bytearray(37 * hc09_iso.SECTOR)
        descriptor = 32 * hc09_iso.SECTOR
        image[descriptor:descriptor + len(hc09_iso.MAGIC)] = hc09_iso.MAGIC
        struct.pack_into("<II", image, descriptor + len(hc09_iso.MAGIC), 33, len(root))
        image[33 * hc09_iso.SECTOR:33 * hc09_iso.SECTOR + len(root)] = root
        image[34 * hc09_iso.SECTOR:34 * hc09_iso.SECTOR + len(nested)] = nested
        image[35 * hc09_iso.SECTOR:35 * hc09_iso.SECTOR + 4] = b"root"
        image[36 * hc09_iso.SECTOR:36 * hc09_iso.SECTOR + 5] = b"inner"
        with open(path, "wb") as f:
            f.write(image)

    def test_list_root_returns_sorted_names_and_folder_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "game.iso")
            self.make_image(path)
            self.assertEqual(
                hc09_iso.list_root(path),
                [("folder", 24, True), ("root.bin", 4, False)],
            )

    def test_find_walks_nested_paths_case_insensitively(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "game.iso")
            self.make_image(path)
            self.assertEqual(hc09_iso.find(path, "FOLDER/INSIDE.DAT"), (0, 36, 5))
            self.assertEqual(hc09_iso.find(path, r"folder\inside.dat"), (0, 36, 5))

    def test_find_rejects_file_used_as_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "game.iso")
            self.make_image(path)
            with self.assertRaisesRegex(ValueError, "root.bin is a file"):
                hc09_iso.find(path, "root.bin/child.dat")

    def test_find_rejects_folder_requested_as_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "game.iso")
            self.make_image(path)
            with self.assertRaisesRegex(ValueError, "folder, not a file"):
                hc09_iso.find(path, "folder")

    def test_find_reports_missing_nested_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "game.iso")
            self.make_image(path)
            with self.assertRaisesRegex(ValueError, "folder/missing.dat is not in the disc image"):
                hc09_iso.find(path, "folder/missing.dat")

    def test_root_descriptor_rejects_short_descriptor(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "short.iso")
            with open(path, "wb") as f:
                f.write(b"\0" * (32 * hc09_iso.SECTOR) + hc09_iso.MAGIC)
            with self.assertRaisesRegex(ValueError, "cut short"):
                hc09_iso.list_root(path)

    def test_directory_reader_rejects_unreasonable_table_size(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "oversized.iso")
            image = bytearray(33 * hc09_iso.SECTOR)
            descriptor = 32 * hc09_iso.SECTOR
            image[descriptor:descriptor + len(hc09_iso.MAGIC)] = hc09_iso.MAGIC
            struct.pack_into("<II", image, descriptor + len(hc09_iso.MAGIC),
                             33, hc09_iso.MAX_TABLE + 1)
            with open(path, "wb") as f:
                f.write(image)
            with self.assertRaisesRegex(ValueError, "looks damaged"):
                hc09_iso.list_root(path)

    def test_entry_tree_visits_left_and_right_siblings(self):
        entries = (
            directory_entry("b", 10, 1, left=4, right=8)
            + directory_entry("a", 11, 1)
            + directory_entry("c", 12, 1)
        )
        self.assertEqual(
            {item["name"] for item in hc09_iso._entries(entries)},
            {"a", "b", "c"},
        )

    def test_entry_tree_stops_on_cycles_and_ignores_out_of_range_links(self):
        entries = directory_entry("first", 10, 1, left=4, right=0x1234)
        entries += directory_entry("second", 11, 1, left=0)
        found = hc09_iso._entries(entries)
        self.assertEqual({item["name"] for item in found}, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
