"""Built-in file downloader with progress tracking and cancellation."""

import os
from pathlib import Path
import re
import threading
import time
from typing import Callable, Optional, Union
import urllib.parse
import requests


class FileDownloader:
    """Streams file download in chunks with progress reporting and cancellation."""

    def __init__(
        self,
        url: str,
        destination_dir: Union[str, Path],
        filename: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, float, float], None]] = None,
        on_complete: Optional[Callable[[Path], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        chunk_size: int = 1024 * 1024,  # 1MB chunks
    ):
        self.url = url
        self.destination_dir = Path(destination_dir)
        self.filename = filename
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.chunk_size = chunk_size

        self._cancelled = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the download in a background thread."""
        self._cancelled = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        """Signal the download to cancel."""
        self._cancelled = True

    def _extract_filename(self, resp: requests.Response) -> str:
        """Extract filename from Content-Disposition header or URL path."""
        cd = resp.headers.get("Content-Disposition", "")
        if cd:
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)["\']?', cd, re.IGNORECASE)
            if match:
                extracted = urllib.parse.unquote(match.group(1).strip())
                # Sanitize
                return re.sub(r'[<>:"/\\|?*]', '_', extracted)

        # Fallback to URL path
        parsed = urllib.parse.urlparse(self.url)
        path_name = os.path.basename(parsed.path)
        if path_name and "." in path_name:
            return re.sub(r'[<>:"/\\|?*]', '_', urllib.parse.unquote(path_name))

        return "downloaded_file"

    def _run(self):
        try:
            self.destination_dir.mkdir(parents=True, exist_ok=True)

            with requests.get(self.url, stream=True, timeout=30) as resp:
                resp.raise_for_status()

                actual_name = self.filename or self._extract_filename(resp)
                target_path = self.destination_dir / actual_name

                # Avoid overwriting existing files if needed
                base = target_path.stem
                suffix = target_path.suffix
                counter = 1
                while target_path.exists():
                    target_path = self.destination_dir / f"{base}_{counter}{suffix}"
                    counter += 1

                temp_path = target_path.with_suffix(target_path.suffix + ".part")

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                start_time = time.time()
                last_time = start_time
                last_downloaded = 0
                speed = 0.0
                eta = 0.0

                with open(temp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=self.chunk_size):
                        if self._cancelled:
                            temp_path.unlink(missing_ok=True)
                            if self.on_error:
                                self.on_error("Download cancelled by user.")
                            return

                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            elapsed = now - last_time
                            if elapsed >= 0.5:
                                speed = (downloaded - last_downloaded) / elapsed
                                last_time = now
                                last_downloaded = downloaded
                                if speed > 0 and total_size > downloaded:
                                    eta = (total_size - downloaded) / speed
                                else:
                                    eta = 0.0

                                if self.on_progress:
                                    self.on_progress(downloaded, total_size, speed, eta)

                # Move part file to final file
                temp_path.rename(target_path)

                if self.on_progress:
                    self.on_progress(downloaded, total_size, speed, 0.0)

                if self.on_complete:
                    self.on_complete(target_path)

        except Exception as e:
            if self.on_error:
                self.on_error(str(e))

