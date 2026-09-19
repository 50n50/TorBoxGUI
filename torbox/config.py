"""Configuration management for TorBox GUI & CLI."""

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Optional


def get_default_download_dir() -> Path:
    """Returns the default download directory (~/Downloads/TorBox)."""
    home = Path.home()
    dl_dir = home / "Downloads" / "TorBox"
    return dl_dir


def get_default_config_path() -> Path:
    """Returns the path to the user configuration file."""
    # If a config.json exists in the current working directory, prefer it
    local_cfg = Path("config.json").resolve()
    if local_cfg.is_file():
        return local_cfg

    # Otherwise use ~/.torboxgui/config.json
    cfg_dir = Path.home() / ".torboxgui"
    return cfg_dir / "config.json"


@dataclass
class Config:
    api_key: str = ""
    download_dir: str = field(default_factory=lambda: str(get_default_download_dir()))
    auto_copy_link: bool = True
    auto_start_browser: bool = False
    auto_download_cli: bool = False
    poll_interval: int = 3
    theme: str = "Dark"  # "Dark", "Light", "System"

    def is_valid(self) -> bool:
        """Check if essential configuration (API key) is present."""
        return bool(self.api_key and self.api_key.strip())

    def ensure_download_dir(self) -> Path:
        """Creates and returns the download directory."""
        path = Path(self.download_dir).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


def load_config(custom_path: Optional[Path] = None) -> Config:
    """Load configuration from JSON file or return default if not found."""
    cfg_path = custom_path or get_default_config_path()

    if cfg_path.is_file():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Config(
                    api_key=data.get("api_key", ""),
                    download_dir=data.get("download_dir", str(get_default_download_dir())),
                    auto_copy_link=data.get("auto_copy_link", True),
                    auto_start_browser=data.get("auto_start_browser", False),
                    auto_download_cli=data.get("auto_download_cli", False),
                    poll_interval=int(data.get("poll_interval", 3)),
                    theme=data.get("theme", "Dark"),
                )
        except Exception:
            pass

    return Config()


def save_config(config: Config, custom_path: Optional[Path] = None) -> Path:
    """Save configuration to JSON file."""
    cfg_path = custom_path or get_default_config_path()

    # Ensure parent directory exists
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2)

    return cfg_path
