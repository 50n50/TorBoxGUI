# TorBoxGUI

A desktop graphical interface and command-line utility for TorBox.

## Features

- GUI powered by CustomTkinter with dark and light themes.
- First-run setup assistant for API key configuration.
- Support for magnet links, .torrent files, Usenet (.nzb or links), and web debrid links.
- Instant cache verification before downloading.
- Cloud download status monitoring for items not yet cached.
- Direct link generation, permalink generation, clipboard copying, and web browser launching.
- Integrated file downloader with progress tracking and pause/resume capability.
- TorBox cloud downloads library browser.
- Fast CLI mode for direct magnet and link processing.

## Requirements

- Python 3.10+
- Dependencies: `customtkinter`, `requests`, `pillow`, `rich`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

### Graphical User Interface

Launch the application:

```bash
python main.py
```

If launched for the first time, a setup dialog will prompt for your TorBox API token. The configuration is stored locally in `~/.torboxgui/config.json` or `./config.json`.

### Command-Line Interface

Run quickly with a magnet link or supported URL:

```bash
python main.py "magnet:?xt=urn:btih:..."
```

Additional CLI options:

- `--zip`: Request multi-file torrents as a ZIP archive.
- `-d, --download`: Automatically download the file to the configured download directory.
- `-o, --output <dir_or_file>`: Specify custom download destination.
- `-c, --copy`: Force copy the generated link to the system clipboard.
- `--open`: Open the generated link in your default browser.
- `--wait`: If uncached, wait and poll until TorBox finishes caching the file.
- `--gui`: Open the graphical interface with the provided magnet or URL preloaded.
- `--config`: Reconfigure the API key via the command line.

## Configuration

Settings are saved in JSON format:

```json
{
  "api_key": "YOUR_API_TOKEN",
  "download_dir": "C:/Users/.../Downloads/TorBox",
  "auto_copy_link": true,
  "auto_start_browser": false,
  "poll_interval": 3,
  "theme": "Dark"
}
```

## License

MIT
