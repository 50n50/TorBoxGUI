"""Utility functions for TorBox GUI & CLI."""

import base64
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse


def format_bytes(size: Optional[int]) -> str:
    """Format bytes into human-readable string (KB, MB, GB, TB)."""
    if size is None or size < 0:
        return "Unknown size"
    if size == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    current = float(size)
    while current >= 1024.0 and idx < len(units) - 1:
        current /= 1024.0
        idx += 1
    return f"{current:.2f} {units[idx]}"


def format_speed(speed_bytes_per_sec: Optional[float]) -> str:
    """Format transfer speed."""
    if speed_bytes_per_sec is None or speed_bytes_per_sec <= 0:
        return "0 B/s"
    return f"{format_bytes(int(speed_bytes_per_sec))}/s"


def format_eta(seconds: Optional[float]) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return "Unknown"
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    mins, sec = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}h {mins:02d}m {sec:02d}s"
    return f"{mins}m {sec:02d}s"


def parse_magnet_info(magnet_url: str) -> Dict[str, Any]:
    """
    Extract info_hash, display name, and trackers from a magnet URI.
    Handles both hex (40 chars) and base32 (32 chars) hashes.
    """
    result = {
        "hash": None,
        "name": None,
        "trackers": [],
    }

    try:
        parsed = urllib.parse.urlparse(magnet_url.strip())
        if parsed.scheme.lower() != "magnet":
            return result

        params = urllib.parse.parse_qs(parsed.query)

        # Extract name
        dn = params.get("dn", [])
        if dn:
            result["name"] = dn[0]

        # Extract trackers
        tr = params.get("tr", [])
        result["trackers"] = tr

        # Extract info hash
        xt_list = params.get("xt", [])
        for xt in xt_list:
            if xt.lower().startswith("urn:btih:"):
                raw_hash = xt[9:].strip()
                if len(raw_hash) == 32:
                    # Base32 encoded hash
                    try:
                        decoded = base64.b32decode(raw_hash.upper())
                        result["hash"] = decoded.hex().lower()
                    except Exception:
                        result["hash"] = raw_hash.lower()
                else:
                    result["hash"] = raw_hash.lower()
                break

    except Exception:
        pass

    return result


def _bdecode_value(data: bytes, idx: int) -> Tuple[Any, int]:
    """Helper to decode a single bencoded value."""
    if idx >= len(data):
        raise ValueError("Unexpected end of data")

    byte = data[idx:idx + 1]

    # Integer
    if byte == b"i":
        end = data.find(b"e", idx + 1)
        if end == -1:
            raise ValueError("Malformed bencoded integer")
        return int(data[idx + 1:end]), end + 1

    # List
    if byte == b"l":
        res_list = []
        cur = idx + 1
        while cur < len(data) and data[cur:cur + 1] != b"e":
            val, cur = _bdecode_value(data, cur)
            res_list.append(val)
        return res_list, cur + 1

    # Dictionary
    if byte == b"d":
        res_dict = {}
        cur = idx + 1
        while cur < len(data) and data[cur:cur + 1] != b"e":
            key, cur = _bdecode_value(data, cur)
            val, cur = _bdecode_value(data, cur)
            res_dict[key] = val
        return res_dict, cur + 1

    # Byte string
    colon = data.find(b":", idx)
    if colon != -1:
        try:
            str_len = int(data[idx:colon])
            start = colon + 1
            end = start + str_len
            if end > len(data):
                raise ValueError("Bencoded string length exceeds data")
            return data[start:end], end
        except ValueError:
            pass

    raise ValueError(f"Invalid bencode prefix at {idx}: {byte}")


def _bencode(data: Any) -> bytes:
    """Helper to re-encode python structure back to bencoded bytes."""
    if isinstance(data, int):
        return b"i" + str(data).encode("ascii") + b"e"
    if isinstance(data, (bytes, bytearray)):
        return str(len(data)).encode("ascii") + b":" + bytes(data)
    if isinstance(data, str):
        encoded = data.encode("utf-8")
        return str(len(encoded)).encode("ascii") + b":" + encoded
    if isinstance(data, list):
        return b"l" + b"".join(_bencode(x) for x in data) + b"e"
    if isinstance(data, dict):
        items = []
        for k in sorted(data.keys()):
            key_bytes = k if isinstance(k, bytes) else str(k).encode("utf-8")
            items.append(_bencode(key_bytes) + _bencode(data[k]))
        return b"d" + b"".join(items) + b"e"
    raise TypeError(f"Cannot bencode type: {type(data)}")


def get_torrent_file_info(filepath: Path) -> Dict[str, Any]:
    """
    Parse a local .torrent file and extract info_hash, name, and total size.
    """
    result = {
        "hash": None,
        "name": None,
        "size": 0,
        "files": [],
    }

    try:
        data = Path(filepath).read_bytes()
        decoded, _ = _bdecode_value(data, 0)
        if isinstance(decoded, dict) and b"info" in decoded:
            info_dict = decoded[b"info"]
            raw_info = _bencode(info_dict)
            result["hash"] = hashlib.sha1(raw_info).hexdigest().lower()

            # Name
            if b"name" in info_dict:
                name_bytes = info_dict[b"name"]
                result["name"] = name_bytes.decode("utf-8", errors="replace")

            # Files and size
            if b"files" in info_dict:
                total_size = 0
                for f in info_dict[b"files"]:
                    f_size = f.get(b"length", 0)
                    total_size += f_size
                    path_parts = [p.decode("utf-8", errors="replace") for p in f.get(b"path", [])]
                    result["files"].append({
                        "name": "/".join(path_parts),
                        "size": f_size,
                    })
                result["size"] = total_size
            elif b"length" in info_dict:
                result["size"] = info_dict[b"length"]
                if result["name"]:
                    result["files"].append({
                        "name": result["name"],
                        "size": result["size"],
                    })
    except Exception:
        pass

    return result


def detect_input_type(input_str: str) -> str:
    """
    Detects whether the input string is a magnet, torrent file, web link, or usenet.
    Returns: 'magnet', 'torrent_file', 'usenet_file', 'usenet_link', 'web_link', or 'unknown'.
    """
    cleaned = input_str.strip().strip("'\"")

    if cleaned.lower().startswith("magnet:?"):
        return "magnet"

    # Check if local file exists
    try:
        p = Path(cleaned)
        if p.is_file():
            suffix = p.suffix.lower()
            if suffix == ".torrent":
                return "torrent_file"
            if suffix == ".nzb":
                return "usenet_file"
    except Exception:
        pass

    # Check URL
    if cleaned.lower().startswith(("http://", "https://")):
        if cleaned.lower().endswith(".torrent"):
            return "web_link"  # or torrent url
        if cleaned.lower().endswith(".nzb"):
            return "usenet_link"
        return "web_link"

    # If it is a 40-char hex string, it could be a bare hash
    if re.fullmatch(r"^[0-9a-fA-F]{40}$", cleaned):
        return "magnet"

    return "unknown"
