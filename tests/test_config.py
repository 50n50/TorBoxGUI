"""Unit tests for configuration manager."""

import json
from pathlib import Path
import tempfile
import unittest

from torbox.config import Config, load_config, save_config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_config(self):
        cfg = Config()
        self.assertFalse(cfg.is_valid())
        self.assertEqual(cfg.api_key, "")
        self.assertTrue(cfg.auto_copy_link)
        self.assertFalse(cfg.auto_start_browser)
        self.assertEqual(cfg.theme, "Dark")

    def test_save_and_load_config(self):
        cfg = Config(
            api_key="test_token_abc_123",
            download_dir=str(Path(self.temp_dir.name) / "downloads"),
            auto_copy_link=False,
            auto_start_browser=True,
            poll_interval=5,
            theme="Light",
        )
        save_config(cfg, custom_path=self.config_path)

        self.assertTrue(self.config_path.exists())

        loaded = load_config(custom_path=self.config_path)
        self.assertTrue(loaded.is_valid())
        self.assertEqual(loaded.api_key, "test_token_abc_123")
        self.assertEqual(loaded.download_dir, str(Path(self.temp_dir.name) / "downloads"))
        self.assertFalse(loaded.auto_copy_link)
        self.assertTrue(loaded.auto_start_browser)
        self.assertEqual(loaded.poll_interval, 5)
        self.assertEqual(loaded.theme, "Light")

    def test_load_nonexistent_returns_defaults(self):
        non_existent = Path(self.temp_dir.name) / "does_not_exist.json"
        loaded = load_config(custom_path=non_existent)
        self.assertFalse(loaded.is_valid())
        self.assertEqual(loaded.api_key, "")


if __name__ == "__main__":
    unittest.main()
