"""Unit tests for TorBox API client."""

import unittest
from unittest.mock import MagicMock, patch
import requests

from torbox.client import (
    AuthenticationError,
    RateLimitError,
    TorBoxClient,
    TorBoxError,
)


class TestTorBoxClient(unittest.TestCase):
    def setUp(self):
        self.client = TorBoxClient("my_test_api_key")

    def test_headers_include_bearer_token(self):
        headers = self.client._headers()
        self.assertEqual(headers["Authorization"], "Bearer my_test_api_key")
        self.assertIn("TorBoxGUI", headers["User-Agent"])

    def test_verify_token_empty_raises_error(self):
        empty_client = TorBoxClient("")
        with self.assertRaises(AuthenticationError):
            empty_client.verify_token()

    @patch.object(requests.Session, "get")
    def test_verify_token_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "error": None,
            "detail": "Retrieved user.",
            "data": {
                "id": 1,
                "email": "user@example.com",
                "plan": "pro",
                "total_downloaded": 50000000,
            },
        }
        mock_get.return_value = mock_resp

        res = self.client.verify_token()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["email"], "user@example.com")
        mock_get.assert_called_once()

    @patch.object(requests.Session, "get")
    def test_verify_token_bad_token(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {
            "success": False,
            "error": "BAD_TOKEN",
            "detail": "Your token is invalid or has expired.",
            "data": None,
        }
        mock_get.return_value = mock_resp

        with self.assertRaises(AuthenticationError):
            self.client.verify_token()

    @patch.object(requests.Session, "get")
    def test_rate_limit_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {
            "success": False,
            "error": "RATE_LIMIT",
            "detail": "Too many requests.",
            "data": None,
        }
        mock_get.return_value = mock_resp

        with self.assertRaises(RateLimitError):
            self.client.verify_token()

    @patch.object(requests.Session, "get")
    def test_check_cached_torrent(self, mock_get):
        test_hash = "08a800874e0d49cd9783f9fe5ec25d30922851cf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "data": {
                test_hash: {
                    "name": "Debian Linux",
                    "size": 1234567,
                    "cached": True,
                    "files": [{"id": 0, "name": "debian.iso", "size": 1234567}],
                }
            },
        }
        mock_get.return_value = mock_resp

        is_cached, info = self.client.is_hash_cached(test_hash)
        self.assertTrue(is_cached)
        self.assertEqual(info["name"], "Debian Linux")

    @patch.object(requests.Session, "post")
    def test_create_torrent_magnet(self, mock_post):
        magnet = "magnet:?xt=urn:btih:08a800874e0d49cd9783f9fe5ec25d30922851cf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "detail": "Torrent created successfully.",
            "data": {"torrent_id": 9999, "hash": "08a800874e0d49cd9783f9fe5ec25d30922851cf"},
        }
        mock_post.return_value = mock_resp

        res = self.client.create_torrent(magnet=magnet, allow_zip=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["torrent_id"], 9999)

    @patch.object(requests.Session, "get")
    def test_request_torrent_dl_cdn(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "data": "https://cdn.torbox.app/download/example_file.zip",
        }
        mock_get.return_value = mock_resp

        url = self.client.request_torrent_dl(torrent_id=123, zip_link=True, redirect=False)
        self.assertEqual(url, "https://cdn.torbox.app/download/example_file.zip")

    def test_request_torrent_dl_permalink(self):
        url = self.client.request_torrent_dl(torrent_id=123, file_id=5, zip_link=False, redirect=True)
        self.assertIn("token=my_test_api_key", url)
        self.assertIn("torrent_id=123", url)
        self.assertIn("file_id=5", url)
        self.assertIn("redirect=true", url)


if __name__ == "__main__":
    unittest.main()
