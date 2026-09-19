"""TorBox API Client implementation for API v1."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests


class TorBoxError(Exception):
    """Base exception for TorBox API errors."""
    def __init__(self, message: str, detail: Optional[str] = None, error_code: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or message
        self.error_code = error_code
        self.status_code = status_code


class AuthenticationError(TorBoxError):
    """Raised when API token is missing, invalid or expired."""
    pass


class RateLimitError(TorBoxError):
    """Raised when TorBox API rate limits are hit."""
    pass


class NotCachedError(TorBoxError):
    """Raised when an item is required to be cached but is not."""
    pass


class ItemNotFoundError(TorBoxError):
    """Raised when a requested torrent or download is not found."""
    pass


class TorBoxClient:
    """Client for interacting with the TorBox API (https://api.torbox.app)."""

    BASE_URL = "https://api.torbox.app"

    def __init__(self, api_key: str, timeout: int = 25):
        self.api_key = api_key.strip() if api_key else ""
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "TorBoxGUI/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _handle_response(self, resp: requests.Response) -> Dict[str, Any]:
        """Parse response JSON and handle API-level and HTTP-level errors."""
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            return {"success": True, "data": resp.text}

        if resp.status_code == 401 or resp.status_code == 403 or data.get("error") == "BAD_TOKEN":
            detail = data.get("detail", "Your TorBox API key is invalid or expired.")
            raise AuthenticationError(detail, detail=detail, error_code=data.get("error"), status_code=resp.status_code)

        if resp.status_code == 429:
            detail = data.get("detail", "Rate limit exceeded. Please wait a moment.")
            raise RateLimitError(detail, detail=detail, error_code="RATE_LIMIT", status_code=429)

        if resp.status_code == 404:
            detail = data.get("detail", "Resource not found.")
            raise ItemNotFoundError(detail, detail=detail, error_code="NOT_FOUND", status_code=404)

        if not data.get("success", False) and resp.status_code >= 400:
            err_code = data.get("error", "API_ERROR")
            detail = data.get("detail", f"TorBox API error: {err_code}")
            raise TorBoxError(detail, detail=detail, error_code=err_code, status_code=resp.status_code)

        return data

    # ---------------- User & Authentication ----------------

    def verify_token(self) -> Dict[str, Any]:
        """
        Verify API key validity against /v1/api/user/me.
        Returns user info dictionary on success.
        """
        if not self.api_key:
            raise AuthenticationError("API key is not configured.")

        url = f"{self.BASE_URL}/v1/api/user/me"
        resp = self.session.get(url, headers=self._headers(), params={"settings": "true"}, timeout=self.timeout)
        return self._handle_response(resp)

    # ---------------- Cache Checking ----------------

    def check_cached_torrent(self, hashes: Union[str, List[str]], list_files: bool = True) -> Dict[str, Any]:
        """
        Check if torrent hash(es) are cached in TorBox servers.
        Returns mapping: {hash: {'cached': bool, 'name': str, 'size': int, 'files': [...]}}
        """
        url = f"{self.BASE_URL}/v1/api/torrents/checkcached"
        if isinstance(hashes, str):
            hashes = [hashes]

        params = {
            "hash": ",".join(hashes),
            "format": "object",
            "list_files": "true" if list_files else "false",
        }
        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        res_json = self._handle_response(resp)
        return res_json.get("data") or {}

    def is_hash_cached(self, info_hash: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Convenience helper: returns (is_cached: bool, details_dict).
        """
        clean_hash = info_hash.strip().lower()
        cached_dict = self.check_cached_torrent([clean_hash])

        # Check exact key or case-insensitive match
        item = cached_dict.get(clean_hash)
        if not item:
            for k, v in cached_dict.items():
                if k.lower() == clean_hash:
                    item = v
                    break

        if isinstance(item, dict):
            # TorBox typically returns {"name": ..., "size": ..., "files": ...} or {"cached": true/false}
            # If files or size or cached is present and true:
            is_cached = item.get("cached", True) if "cached" in item else bool(item.get("size", 0) > 0 or item.get("files"))
            return bool(is_cached), item

        return False, None

    # ---------------- Torrent Management ----------------

    def create_torrent(
        self,
        magnet: Optional[str] = None,
        file_path: Optional[Union[str, Path]] = None,
        name: Optional[str] = None,
        seed: int = 1,
        allow_zip: bool = True,
        as_queued: bool = False,
        add_only_if_cached: bool = False,
    ) -> Dict[str, Any]:
        """
        Create / add a torrent using magnet URI or .torrent file.
        """
        url = f"{self.BASE_URL}/v1/api/torrents/createtorrent"
        form_data: Dict[str, Any] = {
            "seed": seed,
            "allow_zip": "true" if allow_zip else "false",
            "as_queued": "true" if as_queued else "false",
            "add_only_if_cached": "true" if add_only_if_cached else "false",
        }
        if name:
            form_data["name"] = name

        files = None
        opened_file = None
        try:
            if file_path:
                p = Path(file_path)
                opened_file = open(p, "rb")
                files = {"file": (p.name, opened_file, "application/x-bittorrent")}
            elif magnet:
                form_data["magnet"] = magnet
            else:
                raise ValueError("Either magnet or file_path must be provided.")

            resp = self.session.post(url, headers=self._headers(), data=form_data, files=files, timeout=self.timeout)
            return self._handle_response(resp)
        finally:
            if opened_file:
                opened_file.close()

    def get_torrent_list(self, torrent_id: Optional[int] = None, bypass_cache: bool = True) -> List[Dict[str, Any]]:
        """Retrieve list of user torrents."""
        url = f"{self.BASE_URL}/v1/api/torrents/mylist"
        params = {"bypass_cache": "true" if bypass_cache else "false"}
        if torrent_id is not None:
            params["id"] = torrent_id

        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        data = self._handle_response(resp).get("data", [])
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []

    def request_torrent_dl(
        self,
        torrent_id: int,
        file_id: Optional[int] = 0,
        zip_link: bool = False,
        redirect: bool = False,
    ) -> str:
        """
        Request a download link for a torrent.
        Returns the direct CDN URL or permalink redirect URL.
        """
        if redirect:
            # Permanent redirect URL
            return (
                f"{self.BASE_URL}/v1/api/torrents/requestdl?"
                f"token={self.api_key}&torrent_id={torrent_id}&file_id={file_id or 0}&"
                f"zip_link={'true' if zip_link else 'false'}&redirect=true"
            )

        url = f"{self.BASE_URL}/v1/api/torrents/requestdl"
        params = {
            "token": self.api_key,
            "torrent_id": torrent_id,
            "file_id": file_id or 0,
            "zip_link": "true" if zip_link else "false",
            "redirect": "false",
        }
        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        res_data = self._handle_response(resp).get("data")

        if isinstance(res_data, str):
            return res_data
        if isinstance(res_data, dict):
            return res_data.get("link") or res_data.get("url") or ""
        return ""

    def control_torrent(self, torrent_id: int, operation: str = "delete") -> Dict[str, Any]:
        """Control torrent (e.g. 'delete', 'resume', 'pause', 'reannounce')."""
        url = f"{self.BASE_URL}/v1/api/torrents/controltorrent"
        payload = {"operation": operation, "torrent_id": torrent_id}
        resp = self.session.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        return self._handle_response(resp)

    # ---------------- Web Debrid Downloads ----------------

    def create_web_download(
        self,
        link: str,
        password: Optional[str] = None,
        name: Optional[str] = None,
        as_queued: bool = False,
        add_only_if_cached: bool = False,
    ) -> Dict[str, Any]:
        """Create a debrid web download from a supported link."""
        url = f"{self.BASE_URL}/v1/api/webdl/createwebdownload"
        data = {
            "link": link,
            "as_queued": "true" if as_queued else "false",
            "add_only_if_cached": "true" if add_only_if_cached else "false",
        }
        if password:
            data["password"] = password
        if name:
            data["name"] = name

        resp = self.session.post(url, headers=self._headers(), data=data, timeout=self.timeout)
        return self._handle_response(resp)

    def get_web_list(self, web_id: Optional[int] = None, bypass_cache: bool = True) -> List[Dict[str, Any]]:
        """Retrieve web downloads list."""
        url = f"{self.BASE_URL}/v1/api/webdl/mylist"
        params = {"bypass_cache": "true" if bypass_cache else "false"}
        if web_id is not None:
            params["id"] = web_id

        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        data = self._handle_response(resp).get("data", [])
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []

    def request_web_dl(
        self,
        web_id: int,
        file_id: Optional[int] = 0,
        zip_link: bool = False,
        redirect: bool = False,
    ) -> str:
        """Request download link for a web download item."""
        if redirect:
            return (
                f"{self.BASE_URL}/v1/api/webdl/requestdl?"
                f"token={self.api_key}&web_id={web_id}&file_id={file_id or 0}&"
                f"zip_link={'true' if zip_link else 'false'}&redirect=true"
            )

        url = f"{self.BASE_URL}/v1/api/webdl/requestdl"
        params = {
            "token": self.api_key,
            "web_id": web_id,
            "file_id": file_id or 0,
            "zip_link": "true" if zip_link else "false",
            "redirect": "false",
        }
        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        res_data = self._handle_response(resp).get("data")
        if isinstance(res_data, str):
            return res_data
        if isinstance(res_data, dict):
            return res_data.get("link") or res_data.get("url") or ""
        return ""

    def control_web(self, web_id: int, operation: str = "delete") -> Dict[str, Any]:
        """Control web download (e.g. 'delete')."""
        url = f"{self.BASE_URL}/v1/api/webdl/controlwebdownload"
        payload = {"operation": operation, "web_id": web_id}
        resp = self.session.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        return self._handle_response(resp)

    # ---------------- Usenet Downloads ----------------

    def create_usenet_download(
        self,
        link: Optional[str] = None,
        file_path: Optional[Union[str, Path]] = None,
        name: Optional[str] = None,
        password: Optional[str] = None,
        as_queued: bool = False,
        add_only_if_cached: bool = False,
    ) -> Dict[str, Any]:
        """Create a usenet download from NZB link or file."""
        url = f"{self.BASE_URL}/v1/api/usenet/createusenetdownload"
        form_data: Dict[str, Any] = {
            "as_queued": "true" if as_queued else "false",
            "add_only_if_cached": "true" if add_only_if_cached else "false",
        }
        if name:
            form_data["name"] = name
        if password:
            form_data["password"] = password

        files = None
        opened_file = None
        try:
            if file_path:
                p = Path(file_path)
                opened_file = open(p, "rb")
                files = {"file": (p.name, opened_file, "application/x-nzb")}
            elif link:
                form_data["link"] = link
            else:
                raise ValueError("Either link or file_path must be provided.")

            resp = self.session.post(url, headers=self._headers(), data=form_data, files=files, timeout=self.timeout)
            return self._handle_response(resp)
        finally:
            if opened_file:
                opened_file.close()

    def get_usenet_list(self, usenet_id: Optional[int] = None, bypass_cache: bool = True) -> List[Dict[str, Any]]:
        """Retrieve usenet downloads list."""
        url = f"{self.BASE_URL}/v1/api/usenet/mylist"
        params = {"bypass_cache": "true" if bypass_cache else "false"}
        if usenet_id is not None:
            params["id"] = usenet_id

        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        data = self._handle_response(resp).get("data", [])
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []

    def request_usenet_dl(
        self,
        usenet_id: int,
        file_id: Optional[int] = 0,
        zip_link: bool = False,
        redirect: bool = False,
    ) -> str:
        """Request download link for a usenet download item."""
        if redirect:
            return (
                f"{self.BASE_URL}/v1/api/usenet/requestdl?"
                f"token={self.api_key}&usenet_id={usenet_id}&file_id={file_id or 0}&"
                f"zip_link={'true' if zip_link else 'false'}&redirect=true"
            )

        url = f"{self.BASE_URL}/v1/api/usenet/requestdl"
        params = {
            "token": self.api_key,
            "usenet_id": usenet_id,
            "file_id": file_id or 0,
            "zip_link": "true" if zip_link else "false",
            "redirect": "false",
        }
        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        res_data = self._handle_response(resp).get("data")
        if isinstance(res_data, str):
            return res_data
        if isinstance(res_data, dict):
            return res_data.get("link") or res_data.get("url") or ""
        return ""

    def control_usenet(self, usenet_id: int, operation: str = "delete") -> Dict[str, Any]:
        """Control usenet download (e.g. 'delete')."""
        url = f"{self.BASE_URL}/v1/api/usenet/controlusenetdownload"
        payload = {"operation": operation, "usenet_id": usenet_id}
        resp = self.session.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        return self._handle_response(resp)
