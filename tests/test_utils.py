"""Unit tests for utility helpers."""

from pathlib import Path
import tempfile
import unittest

from torbox.utils import (
    _bdecode_value,
    _bencode,
    detect_input_type,
    format_bytes,
    format_eta,
    format_speed,
    get_torrent_file_info,
    parse_magnet_info,
)


class TestUtils(unittest.TestCase):
    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")
        self.assertEqual(format_bytes(None), "Unknown size")

    def test_format_speed(self):
        self.assertEqual(format_speed(0), "0 B/s")
        self.assertEqual(format_speed(1048576), "1.00 MB/s")

    def test_format_eta(self):
        self.assertEqual(format_eta(45), "45s")
        self.assertEqual(format_eta(75), "1m 15s")
        self.assertEqual(format_eta(3665), "1h 01m 05s")
        self.assertEqual(format_eta(None), "Unknown")

    def test_parse_magnet_info_hex(self):
        magnet = "magnet:?xt=urn:btih:08a800874e0d49cd9783f9fe5ec25d30922851cf&dn=Ubuntu+ISO&tr=http%3A%2F%2Ftracker.example.com%2Fannounce"
        info = parse_magnet_info(magnet)
        self.assertEqual(info["hash"], "08a800874e0d49cd9783f9fe5ec25d30922851cf")
        self.assertEqual(info["name"], "Ubuntu ISO")
        self.assertIn("http://tracker.example.com/announce", info["trackers"])

    def test_parse_magnet_info_base32(self):
        # Base32 32-char representation
        magnet = "magnet:?xt=urn:btih:BBC4BB2OJVU43F4D7H7F4JJ5GCJCRUOP&dn=Test"
        info = parse_magnet_info(magnet)
        self.assertEqual(info["hash"], "0845c0874e4d69cd9783f9fe5e253d309228d1cf")
        self.assertEqual(info["name"], "Test")

    def test_detect_input_type(self):
        self.assertEqual(
            detect_input_type("magnet:?xt=urn:btih:08a800874e0d49cd9783f9fe5ec25d30922851cf"),
            "magnet",
        )
        self.assertEqual(
            detect_input_type("08a800874e0d49cd9783f9fe5ec25d30922851cf"),
            "magnet",
        )
        self.assertEqual(
            detect_input_type("https://1fichier.com/?abcdef12345"),
            "web_link",
        )
        self.assertEqual(
            detect_input_type("https://example.com/file.nzb"),
            "usenet_link",
        )
        self.assertEqual(
            detect_input_type("random_string_not_valid"),
            "unknown",
        )

    def test_bencode_and_torrent_file(self):
        # Test bencode encoding and decoding
        data = {b"announce": b"http://tracker.org", b"info": {b"length": 12345, b"name": b"test_file.txt"}}
        encoded = _bencode(data)
        decoded, _ = _bdecode_value(encoded, 0)
        self.assertEqual(decoded[b"announce"], b"http://tracker.org")
        self.assertEqual(decoded[b"info"][b"name"], b"test_file.txt")

        # Create temporary .torrent file and verify get_torrent_file_info
        with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as f:
            f.write(encoded)
            temp_path = Path(f.name)

        try:
            info = get_torrent_file_info(temp_path)
            self.assertIsNotNone(info["hash"])
            self.assertEqual(info["name"], "test_file.txt")
            self.assertEqual(info["size"], 12345)
            self.assertEqual(detect_input_type(str(temp_path)), "torrent_file")
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
