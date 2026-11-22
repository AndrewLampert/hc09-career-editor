import os
import struct
import tempfile
import unittest

import hc09_iso


class RecompIsoIntegrityTests(unittest.TestCase):
    def make_nested_image(self, path, trailing=b""):
        sector = hc09_iso.SECTOR
        name = b"inside.dat"
        child = struct.pack("<HHIIBB", 0xFFFF, 0xFFFF, 35, 3, 0, len(name)) + name
        child += b"\xFF" * ((-len(child)) % 4)
        folder_name = b"folder"
        root = struct.pack(
            "<HHIIBB", 0xFFFF, 0xFFFF, 34, len(child),
            hc09_iso.DIRECTORY, len(folder_name),
        ) + folder_name
        root += b"\xFF" * ((-len(root)) % 4)
        image = bytearray(36 * sector)
        descriptor = 32 * sector
        image[descriptor:descriptor + len(hc09_iso.MAGIC)] = hc09_iso.MAGIC
        struct.pack_into("<II", image, descriptor + len(hc09_iso.MAGIC), 33, len(root))
        image[33 * sector:33 * sector + len(root)] = root
        image[34 * sector:34 * sector + len(child)] = child
        image[35 * sector:35 * sector + 3] = b"old"
        with open(path, "wb") as f:
            f.write(image)
            f.write(trailing)

    def test_nested_replacement_preserves_other_source_bytes_and_aligns_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            replacement = os.path.join(folder, "replacement.ast")
            output = os.path.join(folder, "output.iso")
            self.make_nested_image(source, trailing=b"TAIL")
            payload = b"new archive contents, not sector-sized"
            with open(replacement, "wb") as f:
                f.write(payload)
            with open(source, "rb") as f:
                original = f.read()

            hc09_iso.replace_file(source, "FOLDER/INSIDE.DAT", replacement, output)

            off, new_sector, new_size = hc09_iso.find(output, "folder/inside.dat")
            self.assertEqual((off, new_size), (0, len(payload)))
            self.assertEqual((new_sector * hc09_iso.SECTOR) % hc09_iso.SECTOR, 0)
            with open(output, "rb") as f:
                result = f.read()
            patch_start = 34 * hc09_iso.SECTOR + 4
            expected_prefix = bytearray(original)
            struct.pack_into("<II", expected_prefix, patch_start, new_sector, len(payload))
            self.assertEqual(result[:len(original)], expected_prefix)
            appended_at = new_sector * hc09_iso.SECTOR
            self.assertEqual(result[appended_at:appended_at + len(payload)], payload)
            self.assertEqual(result[appended_at - 1], 0)
            self.assertEqual(os.path.getsize(source), len(original))

    def test_truncated_original_file_is_rejected_before_output_is_created(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            replacement = os.path.join(folder, "replacement.ast")
            output = os.path.join(folder, "output.iso")
            self.make_nested_image(source)
            with open(source, "r+b") as f:
                f.truncate(35 * hc09_iso.SECTOR + 1)
            with open(replacement, "wb") as f:
                f.write(b"replacement")
            with self.assertRaisesRegex(ValueError, "extends beyond the end"):
                hc09_iso.replace_file(source, "folder/inside.dat", replacement, output)
            self.assertFalse(os.path.exists(output))
            self.assertFalse(any(name.endswith(".part") for name in os.listdir(folder)))

    def test_interrupted_replacement_leaves_no_destination_or_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "source.iso")
            replacement = os.path.join(folder, "replacement.ast")
            output = os.path.join(folder, "output.iso")
            self.make_nested_image(source)
            with open(replacement, "wb") as f:
                f.write(b"replacement payload")

            def stop_copy(done, total):
                raise RuntimeError("simulated interruption")

            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                hc09_iso.replace_file(
                    source, "folder/inside.dat", replacement, output,
                    progress=stop_copy,
                )
            self.assertFalse(os.path.exists(output))
            self.assertEqual(
                sorted(os.listdir(folder)),
                ["replacement.ast", "source.iso"],
            )


if __name__ == "__main__":
    unittest.main()
