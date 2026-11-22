import unittest
from types import SimpleNamespace
from unittest import mock

import guiHC09


class RuntimeSelectionTests(unittest.TestCase):
    def make_app(self, runtime="xenia"):
        app = guiHC09.App.__new__(guiHC09.App)
        app.ui_prefs = {
            "runtime": runtime,
            "boot_ast_path": "old-boot.ast",
            "game_ast_path": "old-game.ast",
        }
        app._recomp_images_memo = ["stale.iso"]
        app._clear_game_data_caches = mock.Mock()
        app._runtime_btn = SimpleNamespace(configure=mock.Mock())
        app._recomp_build_btn = SimpleNamespace(configure=mock.Mock())
        app.lbl_status = SimpleNamespace(configure=mock.Mock())
        return app

    def test_switching_to_recomp_clears_runtime_specific_paths_and_enables_iso_build(self):
        app = self.make_app("rpcs3")
        with mock.patch.object(guiHC09, "save_ui_prefs") as save:
            app._set_runtime("recomp")

        self.assertEqual(app.ui_prefs["runtime"], "recomp")
        self.assertEqual(app.ui_prefs["boot_ast_path"], "")
        self.assertEqual(app.ui_prefs["game_ast_path"], "")
        self.assertIsNone(app._recomp_images_memo)
        app._clear_game_data_caches.assert_called_once_with()
        save.assert_called_once_with(app.ui_prefs)
        app._runtime_btn.configure.assert_called_once_with(text="Runtime: RECOMP")
        app._recomp_build_btn.configure.assert_called_once_with(state="normal")
        app.lbl_status.configure.assert_called_once()

    def test_switching_to_xenia_disables_recomp_iso_build(self):
        app = self.make_app("recomp")
        with mock.patch.object(guiHC09, "save_ui_prefs"):
            app._set_runtime("xenia")
        self.assertEqual(app.ui_prefs["runtime"], "xenia")
        app._recomp_build_btn.configure.assert_called_once_with(state="disabled")

    def test_switching_between_all_supported_runtime_values(self):
        app = self.make_app("xenia")
        with mock.patch.object(guiHC09, "save_ui_prefs"):
            app._set_runtime("rpcs3")
            self.assertEqual(app.ui_prefs["runtime"], "rpcs3")
            app._set_runtime("recomp")
            self.assertEqual(app.ui_prefs["runtime"], "recomp")
            app._set_runtime("xenia")
            self.assertEqual(app.ui_prefs["runtime"], "xenia")
        self.assertEqual(app._clear_game_data_caches.call_count, 3)

    def test_selecting_current_runtime_is_a_no_op(self):
        app = self.make_app("rpcs3")
        with mock.patch.object(guiHC09, "save_ui_prefs") as save:
            app._set_runtime("rpcs3")
        save.assert_not_called()
        app._clear_game_data_caches.assert_not_called()
        app._runtime_btn.configure.assert_not_called()

    def test_unknown_runtime_is_rejected_without_changing_preferences(self):
        app = self.make_app("xenia")
        with self.assertRaisesRegex(ValueError, "Unknown runtime"):
            app._set_runtime("unknown")
        self.assertEqual(app.ui_prefs["runtime"], "xenia")
        app._clear_game_data_caches.assert_not_called()


if __name__ == "__main__":
    unittest.main()
