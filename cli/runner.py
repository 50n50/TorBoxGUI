"""Command-Line Interface runner for TorBox."""

import argparse
import os
from pathlib import Path
import sys
import time
import tkinter as tk
from typing import Any, Dict, List, Optional
import webbrowser

from torbox.client import AuthenticationError, TorBoxClient, TorBoxError
from torbox.config import Config, load_config, save_config, get_default_download_dir
from torbox.downloader import FileDownloader
from torbox.utils import (
    detect_input_type,
    format_bytes,
    format_eta,
    format_speed,
    get_torrent_file_info,
    parse_magnet_info,
)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None


def print_msg(msg: str, style: str = ""):
    if HAS_RICH and console:
        console.print(msg, style=style)
    else:
        print(msg)


def prompt_api_key_interactive(cfg: Config) -> Config:
    """Prompt user for API token in terminal if not configured."""
    print_msg("[bold yellow]TorBox API key is not configured.[/bold yellow]" if HAS_RICH else "TorBox API key is not configured.")
    print_msg("You can find your API key at: https://torbox.app/settings\n")

    while True:
        token = input("Enter your TorBox API token: ").strip()
        if not token:
            print("Token cannot be empty.")
            continue

        print("Testing token...")
        client = TorBoxClient(token, timeout=15)
        try:
            res = client.verify_token()
            user_data = res.get("data", {})
            email = user_data.get("email", "User")
            plan = user_data.get("plan", "Standard")
            print_msg(f"[green]Success! Authenticated as {email} ({plan} plan).[/green]" if HAS_RICH else f"Success! Authenticated as {email} ({plan} plan).")

            cfg.api_key = token
            save_config(cfg)
            print_msg(f"Configuration saved to: {get_default_download_dir().parent / '.torboxgui' / 'config.json'}\n")
            return cfg
        except Exception as e:
            print_msg(f"[red]Error validating token: {e}[/red]" if HAS_RICH else f"Error validating token: {e}")
            retry = input("Try again? [Y/n]: ").strip().lower()
            if retry == "n":
                sys.exit(1)


def copy_clipboard(text: str):
    """Copy text to clipboard using Tkinter without showing window."""
    try:
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
    except Exception:
        pass


def run_cli(args: argparse.Namespace):
    cfg = load_config()

    # Manual config flag
    if args.config:
        cfg = prompt_api_key_interactive(cfg)
        if not args.source:
            return

    # Check API key
    if not cfg.is_valid():
        cfg = prompt_api_key_interactive(cfg)

    client = TorBoxClient(cfg.api_key)

    # Info flag
    if args.info:
        try:
            res = client.verify_token()
            data = res.get("data", {})
            print_msg("\n--- TorBox Account Info ---", style="bold cyan")
            print(f"Email:            {data.get('email', 'Unknown')}")
            print(f"Plan:             {data.get('plan', 'Standard').capitalize()}")
            print(f"Customer Status:  {data.get('customer', 'Active')}")
            print(f"Total Downloaded: {format_bytes(data.get('total_downloaded', 0))}")
            print(f"Download Dir:     {cfg.download_dir}")
            return
        except Exception as e:
            print_msg(f"Failed to fetch account info: {e}", style="red")
            sys.exit(1)

    source = args.source
    if not source:
        print("Error: No magnet link, file, or URL provided.")
        print("Usage: python main.py <MAGNET | FILE | URL> [options]")
        sys.exit(1)

    itype = detect_input_type(source)
    print_msg(f"Detected input type: [bold]{itype}[/bold]" if HAS_RICH else f"Detected input type: {itype}")

    # Check cache status if magnet or torrent
    info_hash = None
    if itype == "magnet":
        info_hash = parse_magnet_info(source).get("hash")
        if not info_hash and len(source.strip()) == 40:
            info_hash = source.strip().lower()
    elif itype == "torrent_file":
        info_hash = get_torrent_file_info(Path(source)).get("hash")

    is_cached = False
    if info_hash:
        print("Checking TorBox cache...")
        try:
            is_cached, _ = client.is_hash_cached(info_hash)
            if is_cached:
                print_msg("[green]Item is cached on TorBox (Instant Download Available)![/green]" if HAS_RICH else "Item is cached on TorBox (Instant Download Available)!")
            else:
                print_msg("[yellow]Item is NOT yet cached on TorBox servers.[/yellow]" if HAS_RICH else "Item is NOT yet cached on TorBox servers.")
        except Exception as e:
            print(f"Cache check note: {e}")

    # Create download on TorBox
    print("Submitting to TorBox...")
    item_id = None
    item_type = "torrent"

    try:
        if itype == "magnet":
            res = client.create_torrent(magnet=source, allow_zip=args.zip)
            item_id = _extract_id(res, "torrent_id")
            item_type = "torrent"
        elif itype == "torrent_file":
            res = client.create_torrent(file_path=source, allow_zip=args.zip)
            item_id = _extract_id(res, "torrent_id")
            item_type = "torrent"
        elif itype == "web_link":
            res = client.create_web_download(link=source)
            item_id = _extract_id(res, "web_id")
            item_type = "web"
        elif itype in ("usenet_file", "usenet_link"):
            if itype == "usenet_file":
                res = client.create_usenet_download(file_path=source)
            else:
                res = client.create_usenet_download(link=source)
            item_id = _extract_id(res, "usenet_id")
            item_type = "usenet"
        elif len(source.strip()) == 40:
            magnet = f"magnet:?xt=urn:btih:{source.strip()}"
            res = client.create_torrent(magnet=magnet, allow_zip=args.zip)
            item_id = _extract_id(res, "torrent_id")
            item_type = "torrent"
        else:
            raise TorBoxError(f"Unsupported format: {source}")

    except Exception as e:
        print_msg(f"[red]Error creating download: {e}[/red]" if HAS_RICH else f"Error creating download: {e}")
        sys.exit(1)

    print(f"Created TorBox task #{item_id}")

    # Check status from list
    item = _get_item(client, item_id, item_type)
    state = str(item.get("download_state", "")).lower() if item else ""
    prog = float(item.get("progress", 0)) if item else 0.0

    if state not in ("completed", "cached") and prog < 100:
        # Uncached
        print_msg(f"\n[yellow]Notice: This item is not yet cached.[/yellow] Current status: [bold]{state.capitalize()} ({prog:.1f}%)[/bold]" if HAS_RICH else f"\nNotice: This item is not yet cached. Current status: {state.capitalize()} ({prog:.1f}%)")

        if not args.wait:
            print("Item was added to your TorBox cloud queue.")
            print(f"TorBox ID: {item_id}")
            print("Run with '--wait' to wait for TorBox to finish caching, or check TorBoxGUI / web dashboard.")
            return

        # Wait / Poll loop
        print("Waiting for TorBox to finish caching...")
        poll_interval = max(2, cfg.poll_interval)
        while True:
            time.sleep(poll_interval)
            item = _get_item(client, item_id, item_type)
            if not item:
                continue

            state = str(item.get("download_state", "")).lower()
            prog = float(item.get("progress", 0))
            speed = item.get("download_speed", 0)
            seeds = item.get("seeds", 0)

            speed_str = f" | {format_speed(speed)}" if speed else ""
            seeds_str = f" | Seeds: {seeds}" if seeds else ""
            print(f"\rStatus: {state.capitalize()} | Progress: {prog:.1f}%{speed_str}{seeds_str}    ", end="", flush=True)

            if state in ("completed", "cached") or prog >= 100:
                print("\nTorBox cloud caching completed!")
                break

    # Item is ready! Generate download link
    try:
        if item_type == "torrent":
            cdn_link = client.request_torrent_dl(torrent_id=item_id, zip_link=args.zip, redirect=False)
            permalink = client.request_torrent_dl(torrent_id=item_id, zip_link=args.zip, redirect=True)
        elif item_type == "web":
            cdn_link = client.request_web_dl(web_id=item_id, redirect=False)
            permalink = client.request_web_dl(web_id=item_id, redirect=True)
        else:
            cdn_link = client.request_usenet_dl(usenet_id=item_id, redirect=False)
            permalink = client.request_usenet_dl(usenet_id=item_id, redirect=True)

    except Exception as e:
        print_msg(f"[red]Error requesting download link: {e}[/red]" if HAS_RICH else f"Error requesting download link: {e}")
        sys.exit(1)

    name = item.get("name", f"Download_{item_id}") if item else f"Download_{item_id}"
    size = item.get("size", 0) if item else 0

    print("\n" + "=" * 60)
    print_msg(f"[bold green]Download Ready:[/bold green] {name}" if HAS_RICH else f"Download Ready: {name}")
    print(f"Size:          {format_bytes(size)}")
    print(f"Direct CDN:    {cdn_link}")
    print(f"Permalink:     {permalink}")
    print("=" * 60 + "\n")

    # Clipboard copy
    if args.copy or cfg.auto_copy_link:
        copy_clipboard(cdn_link)
        print("Direct download link copied to clipboard.")

    # Open in browser
    if args.open or cfg.auto_start_browser:
        print("Opening in default browser...")
        webbrowser.open(cdn_link)

    # Local download
    if args.download or cfg.auto_download_cli:
        dest_dir = Path(args.output).expanduser().resolve() if args.output else cfg.ensure_download_dir()
        _download_cli_file(cdn_link, dest_dir, name)


def _download_cli_file(url: str, dest_dir: Path, title: str):
    print(f"Starting local download to: {dest_dir}...")
    dest_dir.mkdir(parents=True, exist_ok=True)

    if HAS_RICH and console:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading", total=None)

            def on_progress(downloaded, total, speed, eta):
                if total > 0:
                    progress.update(task, total=total, completed=downloaded)
                else:
                    progress.update(task, completed=downloaded)

            done_event = [False]
            err_msg = [None]

            def on_complete(path):
                done_event[0] = True

            def on_error(err):
                err_msg[0] = err
                done_event[0] = True

            downloader = FileDownloader(
                url=url,
                destination_dir=dest_dir,
                on_progress=on_progress,
                on_complete=on_complete,
                on_error=on_error,
            )
            downloader.start()

            while not done_event[0]:
                time.sleep(0.1)

            if err_msg[0]:
                print_msg(f"[red]Download failed: {err_msg[0]}[/red]")
            else:
                print_msg("[green]Download complete![/green]")

    else:
        # Basic terminal progress
        def on_progress(downloaded, total, speed, eta):
            pct = (downloaded / total * 100) if total > 0 else 0
            tot_str = format_bytes(total) if total > 0 else "?"
            print(f"\rDownloaded: {format_bytes(downloaded)} / {tot_str} ({pct:.1f}%) | Speed: {format_speed(speed)}   ", end="", flush=True)

        done_event = [False]
        err_msg = [None]

        def on_complete(path):
            done_event[0] = True

        def on_error(err):
            err_msg[0] = err
            done_event[0] = True

        downloader = FileDownloader(
            url=url,
            destination_dir=dest_dir,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )
        downloader.start()

        while not done_event[0]:
            time.sleep(0.1)

        print()
        if err_msg[0]:
            print(f"Download failed: {err_msg[0]}")
        else:
            print("Download complete!")


def _extract_id(res: Dict[str, Any], key_name: str) -> int:
    data = res.get("data")
    if isinstance(data, dict):
        for k in (key_name, "id", "torrent_id", "web_id", "usenet_id"):
            if k in data:
                return int(data[k])
    elif isinstance(data, (int, str)) and str(data).isdigit():
        return int(data)
    raise TorBoxError(f"Could not extract task ID from response: {res}")


def _get_item(client: TorBoxClient, item_id: int, item_type: str) -> Optional[Dict[str, Any]]:
    try:
        if item_type == "torrent":
            items = client.get_torrent_list(torrent_id=item_id)
        elif item_type == "web":
            items = client.get_web_list(web_id=item_id)
        else:
            items = client.get_usenet_list(usenet_id=item_id)

        for it in items:
            if it.get("id") == item_id or it.get("torrent_id") == item_id or it.get("web_id") == item_id:
                return it
        return items[0] if items else None
    except Exception:
        return None
