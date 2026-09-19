"""Quick Download tab for TorBox GUI."""

import os
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog
from typing import Any, Dict, List, Optional
import webbrowser
import customtkinter as ctk

from torbox.client import AuthenticationError, TorBoxClient, TorBoxError
from torbox.config import Config
from torbox.downloader import FileDownloader
from torbox.utils import (
    detect_input_type,
    format_bytes,
    format_eta,
    format_speed,
    get_torrent_file_info,
    parse_magnet_info,
)


class DownloadTab(ctk.CTkScrollableFrame):
    """View for generating downloads for magnets, torrents, and web links."""

    def __init__(self, parent, client: Optional[TorBoxClient], config: Config, on_notify=None):
        super().__init__(parent, fg_color="transparent")
        self.client = client
        self.config = config
        self.on_notify = on_notify

        self._active_downloader: Optional[FileDownloader] = None
        self._polling_stop_flag = threading.Event()
        self._current_torrent_data: Optional[Dict[str, Any]] = None
        self._generated_cdn_link: str = ""
        self._generated_permalink: str = ""

        self._build_ui()

    def set_client(self, client: TorBoxClient):
        self.client = client

    def _build_ui(self):
        # 1. Input Section Card
        input_card = ctk.CTkFrame(self, corner_radius=10)
        input_card.pack(fill="x", padx=10, pady=(5, 10))

        title_frame = ctk.CTkFrame(input_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(15, 5))

        lbl = ctk.CTkLabel(
            title_frame,
            text="Generate TorBox Download",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        lbl.pack(side="left")

        self.type_badge = ctk.CTkLabel(
            title_frame,
            text="Enter link or select file",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.type_badge.pack(side="right")

        # Input Textbox / Entry
        entry_frame = ctk.CTkFrame(input_card, fg_color="transparent")
        entry_frame.pack(fill="x", padx=15, pady=5)

        self.input_entry = ctk.CTkEntry(
            entry_frame,
            placeholder_text="Paste Magnet URI, Torrent file path, Web/Debrid link, or NZB URL...",
            height=40,
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_entry.bind("<KeyRelease>", self._on_input_changed)

        paste_btn = ctk.CTkButton(
            entry_frame,
            text="Paste",
            width=70,
            height=40,
            command=self._paste_clipboard,
        )
        paste_btn.pack(side="left", padx=(0, 6))

        browse_btn = ctk.CTkButton(
            entry_frame,
            text="Browse File...",
            width=100,
            height=40,
            fg_color="gray30",
            hover_color="gray40",
            command=self._browse_file,
        )
        browse_btn.pack(side="right")

        # Cache & Options Row
        options_row = ctk.CTkFrame(input_card, fg_color="transparent")
        options_row.pack(fill="x", padx=15, pady=(8, 12))

        # Check Cache button and status
        self.check_cache_btn = ctk.CTkButton(
            options_row,
            text="Check Cache",
            width=110,
            height=32,
            fg_color="gray30",
            hover_color="gray40",
            command=self._check_cache_action,
        )
        self.check_cache_btn.pack(side="left", padx=(0, 10))

        self.cache_status_lbl = ctk.CTkLabel(
            options_row,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray",
        )
        self.cache_status_lbl.pack(side="left")

        # Checkbox options
        opt_frame = ctk.CTkFrame(input_card, fg_color="transparent")
        opt_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.zip_var = ctk.BooleanVar(value=True)
        self.zip_cb = ctk.CTkCheckBox(opt_frame, text="Download as ZIP (if multi-file)", variable=self.zip_var)
        self.zip_cb.pack(side="left", padx=(0, 20))

        self.copy_var = ctk.BooleanVar(value=self.config.auto_copy_link)
        self.copy_cb = ctk.CTkCheckBox(opt_frame, text="Auto-copy link to clipboard", variable=self.copy_var)
        self.copy_cb.pack(side="left", padx=(0, 20))

        self.browser_var = ctk.BooleanVar(value=self.config.auto_start_browser)
        self.browser_cb = ctk.CTkCheckBox(opt_frame, text="Open in web browser", variable=self.browser_var)
        self.browser_cb.pack(side="left")

        # Action Button Frame
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=5)

        self.generate_btn = ctk.CTkButton(
            action_frame,
            text="Generate Download Link",
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._on_generate_click,
        )
        self.generate_btn.pack(fill="x")

        # 2. Cloud Status / Polling Card (Hidden by default)
        self.cloud_card = ctk.CTkFrame(self, corner_radius=10)
        self.cloud_card_lbl = ctk.CTkLabel(
            self.cloud_card,
            text="Cloud Cache Processing",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.cloud_card_lbl.pack(anchor="w", padx=15, pady=(12, 4))

        self.cloud_status_lbl = ctk.CTkLabel(
            self.cloud_card,
            text="TorBox is caching this item...",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.cloud_status_lbl.pack(anchor="w", padx=15, pady=(0, 8))

        self.cloud_pbar = ctk.CTkProgressBar(self.cloud_card)
        self.cloud_pbar.pack(fill="x", padx=15, pady=5)
        self.cloud_pbar.set(0)

        cloud_btn_row = ctk.CTkFrame(self.cloud_card, fg_color="transparent")
        cloud_btn_row.pack(fill="x", padx=15, pady=(6, 12))

        self.cancel_poll_btn = ctk.CTkButton(
            cloud_btn_row,
            text="Stop Waiting",
            width=100,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            command=self._stop_polling,
        )
        self.cancel_poll_btn.pack(side="right")

        # 3. Results Card (Hidden by default)
        self.result_card = ctk.CTkFrame(self, corner_radius=10)

        res_header = ctk.CTkFrame(self.result_card, fg_color="transparent")
        res_header.pack(fill="x", padx=15, pady=(15, 5))

        self.res_title_lbl = ctk.CTkLabel(
            res_header,
            text="Download Ready",
            font=ctk.CTkFont(size=16, weight="bold"),
            wraplength=700,
            justify="left",
        )
        self.res_title_lbl.pack(side="left")

        self.res_size_lbl = ctk.CTkLabel(
            res_header,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.res_size_lbl.pack(side="right")

        # File selection dropdown (if multi-file)
        self.file_picker_frame = ctk.CTkFrame(self.result_card, fg_color="transparent")
        self.file_picker_lbl = ctk.CTkLabel(self.file_picker_frame, text="Select File:")
        self.file_picker_lbl.pack(side="left", padx=(0, 10))

        self.file_option_menu = ctk.CTkOptionMenu(
            self.file_picker_frame,
            values=["All Files (ZIP Archive)"],
            command=self._on_file_selected,
            width=400,
        )
        self.file_option_menu.pack(side="left", fill="x", expand=True)

        # Links display frame
        links_frame = ctk.CTkFrame(self.result_card, fg_color="transparent")
        links_frame.pack(fill="x", padx=15, pady=8)

        cdn_lbl = ctk.CTkLabel(links_frame, text="Direct CDN Link:", font=ctk.CTkFont(weight="bold"))
        cdn_lbl.pack(anchor="w")

        cdn_row = ctk.CTkFrame(links_frame, fg_color="transparent")
        cdn_row.pack(fill="x", pady=(2, 8))

        self.cdn_entry = ctk.CTkEntry(cdn_row, height=34)
        self.cdn_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        copy_cdn_btn = ctk.CTkButton(
            cdn_row,
            text="Copy",
            width=65,
            height=34,
            command=lambda: self._copy_to_clipboard(self.cdn_entry.get()),
        )
        copy_cdn_btn.pack(side="right")

        permalink_lbl = ctk.CTkLabel(links_frame, text="Permalink (Redirect URL):", font=ctk.CTkFont(weight="bold"))
        permalink_lbl.pack(anchor="w")

        perm_row = ctk.CTkFrame(links_frame, fg_color="transparent")
        perm_row.pack(fill="x", pady=(2, 10))

        self.perm_entry = ctk.CTkEntry(perm_row, height=34)
        self.perm_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        copy_perm_btn = ctk.CTkButton(
            perm_row,
            text="Copy",
            width=65,
            height=34,
            command=lambda: self._copy_to_clipboard(self.perm_entry.get()),
        )
        copy_perm_btn.pack(side="right")

        # Action Buttons on Result Card
        res_actions = ctk.CTkFrame(self.result_card, fg_color="transparent")
        res_actions.pack(fill="x", padx=15, pady=(5, 15))

        self.browser_btn = ctk.CTkButton(
            res_actions,
            text="Open in Browser",
            width=130,
            height=38,
            fg_color="gray30",
            hover_color="gray40",
            command=self._open_in_browser,
        )
        self.browser_btn.pack(side="left", padx=(0, 10))

        self.copy_all_btn = ctk.CTkButton(
            res_actions,
            text="Copy Direct Link",
            width=130,
            height=38,
            command=lambda: self._copy_to_clipboard(self._generated_cdn_link),
        )
        self.copy_all_btn.pack(side="left", padx=(0, 10))

        self.download_local_btn = ctk.CTkButton(
            res_actions,
            text="Download to PC",
            width=140,
            height=38,
            fg_color=("#1f6aa5", "#2b84c8"),
            font=ctk.CTkFont(weight="bold"),
            command=self._start_local_download,
        )
        self.download_local_btn.pack(side="right")

        # 4. Local File Downloader Progress Card (Hidden by default)
        self.dl_progress_card = ctk.CTkFrame(self, corner_radius=10)
        dl_header = ctk.CTkFrame(self.dl_progress_card, fg_color="transparent")
        dl_header.pack(fill="x", padx=15, pady=(12, 4))

        self.dl_title_lbl = ctk.CTkLabel(
            dl_header,
            text="Downloading to Local PC...",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.dl_title_lbl.pack(side="left")

        self.dl_speed_lbl = ctk.CTkLabel(
            dl_header,
            text="0 B/s",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.dl_speed_lbl.pack(side="right")

        self.dl_pbar = ctk.CTkProgressBar(self.dl_progress_card)
        self.dl_pbar.pack(fill="x", padx=15, pady=5)
        self.dl_pbar.set(0)

        dl_info_row = ctk.CTkFrame(self.dl_progress_card, fg_color="transparent")
        dl_info_row.pack(fill="x", padx=15, pady=(2, 12))

        self.dl_details_lbl = ctk.CTkLabel(
            dl_info_row,
            text="0 B / 0 B (ETA: calculating...)",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.dl_details_lbl.pack(side="left")

        self.cancel_dl_btn = ctk.CTkButton(
            dl_info_row,
            text="Cancel",
            width=80,
            height=28,
            fg_color="gray30",
            hover_color="gray40",
            command=self._cancel_local_download,
        )
        self.cancel_dl_btn.pack(side="right")

        self.open_folder_btn = ctk.CTkButton(
            dl_info_row,
            text="Open Folder",
            width=90,
            height=28,
            command=self._open_destination_folder,
        )

    # ---------------- UI Event Handlers ----------------

    def set_prefilled_input(self, text: str):
        """Set prefilled input text and trigger validation."""
        self.input_entry.delete(0, "end")
        self.input_entry.insert(0, text.strip())
        self._on_input_changed()

    def _paste_clipboard(self):
        try:
            content = self.clipboard_get()
            if content:
                self.input_entry.delete(0, "end")
                self.input_entry.insert(0, content.strip())
                self._on_input_changed()
        except Exception:
            pass

    def _browse_file(self):
        chosen = filedialog.askopenfilename(
            title="Select Torrent or NZB File",
            filetypes=[
                ("Supported Files", "*.torrent;*.nzb"),
                ("Torrent Files", "*.torrent"),
                ("NZB Files", "*.nzb"),
                ("All Files", "*.*"),
            ],
            parent=self,
        )
        if chosen:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, chosen)
            self._on_input_changed()

    def _on_input_changed(self, event=None):
        val = self.input_entry.get().strip()
        itype = detect_input_type(val)
        type_labels = {
            "magnet": "Detected: Magnet URI",
            "torrent_file": "Detected: Torrent File",
            "usenet_file": "Detected: Usenet NZB File",
            "usenet_link": "Detected: Usenet Link",
            "web_link": "Detected: Web Debrid Link",
            "unknown": "Detected: Unknown Format",
        }
        self.type_badge.configure(text=type_labels.get(itype, "Enter link or file"))
        self.cache_status_lbl.configure(text="")

    def _extract_hash_from_input(self) -> Optional[str]:
        val = self.input_entry.get().strip()
        itype = detect_input_type(val)

        if itype == "magnet":
            minfo = parse_magnet_info(val)
            if minfo.get("hash"):
                return minfo["hash"]
            # If bare 40-char hex
            if len(val) == 40:
                return val.lower()

        elif itype == "torrent_file":
            tinfo = get_torrent_file_info(Path(val))
            return tinfo.get("hash")

        return None

    def _check_cache_action(self):
        if not self.client or not self.client.api_key:
            self._notify("Error: API token not configured.", is_error=True)
            return

        h = self._extract_hash_from_input()
        if not h:
            val = self.input_entry.get().strip()
            itype = detect_input_type(val)
            if itype == "web_link":
                self.cache_status_lbl.configure(
                    text="Web link will be verified upon creation",
                    text_color="gray",
                )
            else:
                self.cache_status_lbl.configure(
                    text="Cannot extract hash. Check magnet or torrent file.",
                    text_color="#ff5555",
                )
            return

        self.cache_status_lbl.configure(text="Checking TorBox cache...", text_color="gray")
        self.check_cache_btn.configure(state="disabled")

        threading.Thread(target=self._check_cache_worker, args=(h,), daemon=True).start()

    def _check_cache_worker(self, info_hash: str):
        try:
            is_cached, details = self.client.is_hash_cached(info_hash)
            self.after(0, lambda: self._on_cache_checked(is_cached, details))
        except Exception as e:
            self.after(0, lambda: self._on_cache_error(str(e)))

    def _on_cache_checked(self, is_cached: bool, details: Optional[Dict]):
        self.check_cache_btn.configure(state="normal")
        if is_cached:
            size_str = ""
            if details and details.get("size"):
                size_str = f" ({format_bytes(details['size'])})"
            self.cache_status_lbl.configure(
                text=f"Instant Cache Available{size_str}",
                text_color="#44bb44",
            )
        else:
            self.cache_status_lbl.configure(
                text="Not Cached Yet (Will download to cloud first)",
                text_color="#e5a50a",
            )

    def _on_cache_error(self, err: str):
        self.check_cache_btn.configure(state="normal")
        self.cache_status_lbl.configure(text=f"Cache check error: {err}", text_color="#ff5555")

    # ---------------- Download Generation Workflow ----------------

    def _on_generate_click(self):
        val = self.input_entry.get().strip()
        if not val:
            self._notify("Please enter a magnet link, URL, or select a file.", is_error=True)
            return

        if not self.client or not self.client.api_key:
            self._notify("TorBox API token is not configured.", is_error=True)
            return

        # Hide old results
        self.result_card.pack_forget()
        self.cloud_card.pack_forget()

        self.generate_btn.configure(state="disabled", text="Processing request...")

        threading.Thread(target=self._generate_worker, args=(val,), daemon=True).start()

    def _generate_worker(self, source: str):
        itype = detect_input_type(source)
        try:
            if itype == "magnet":
                res = self.client.create_torrent(
                    magnet=source,
                    allow_zip=self.zip_var.get(),
                )
                torrent_id = self._extract_id_from_create_res(res, "torrent_id")
                self._handle_torrent_created(torrent_id, source)

            elif itype == "torrent_file":
                res = self.client.create_torrent(
                    file_path=source,
                    allow_zip=self.zip_var.get(),
                )
                torrent_id = self._extract_id_from_create_res(res, "torrent_id")
                self._handle_torrent_created(torrent_id, source)

            elif itype == "web_link":
                res = self.client.create_web_download(link=source)
                web_id = self._extract_id_from_create_res(res, "web_id")
                self._handle_web_created(web_id, source)

            elif itype in ("usenet_file", "usenet_link"):
                if itype == "usenet_file":
                    res = self.client.create_usenet_download(file_path=source)
                else:
                    res = self.client.create_usenet_download(link=source)
                usenet_id = self._extract_id_from_create_res(res, "usenet_id")
                self._handle_usenet_created(usenet_id, source)

            else:
                # If it's a bare hash
                if len(source) == 40:
                    magnet = f"magnet:?xt=urn:btih:{source}"
                    res = self.client.create_torrent(magnet=magnet, allow_zip=self.zip_var.get())
                    torrent_id = self._extract_id_from_create_res(res, "torrent_id")
                    self._handle_torrent_created(torrent_id, magnet)
                else:
                    raise TorBoxError(f"Unsupported or unrecognized input: {source}")

        except AuthenticationError as e:
            self.after(0, lambda: self._on_generate_error(f"Authentication Failed: {e.detail}"))
        except Exception as e:
            self.after(0, lambda: self._on_generate_error(str(e)))

    def _extract_id_from_create_res(self, res: Dict[str, Any], key_name: str) -> int:
        data = res.get("data")
        if isinstance(data, dict):
            if key_name in data:
                return int(data[key_name])
            if "id" in data:
                return int(data["id"])
            if "torrent_id" in data:
                return int(data["torrent_id"])
            if "web_id" in data:
                return int(data["web_id"])
            if "usenet_id" in data:
                return int(data["usenet_id"])
        elif isinstance(data, (int, str)) and str(data).isdigit():
            return int(data)

        # Fallback to query list
        raise TorBoxError(f"Unexpected response format from TorBox: {res}")

    def _handle_torrent_created(self, torrent_id: int, source: str):
        # Fetch item status from mylist
        item = self._find_item_in_list(self.client.get_torrent_list(torrent_id=torrent_id), torrent_id)

        if not item:
            # Poll once more
            time.sleep(1)
            item = self._find_item_in_list(self.client.get_torrent_list(), torrent_id)

        # Check if item is already completed / cached
        download_state = str(item.get("download_state", "")).lower() if item else ""
        progress = float(item.get("progress", 0)) if item else 0.0

        if download_state in ("completed", "cached") or progress >= 100:
            # Instant completion!
            self._render_torrent_ready(torrent_id, item)
        else:
            # Item is still downloading or queued in TorBox cloud
            self.after(0, lambda: self._show_cloud_polling(torrent_id, item, "torrent"))
            self._start_polling_worker(torrent_id, "torrent")

    def _handle_web_created(self, web_id: int, source: str):
        item = self._find_item_in_list(self.client.get_web_list(web_id=web_id), web_id)
        download_state = str(item.get("download_state", "")).lower() if item else ""
        progress = float(item.get("progress", 0)) if item else 0.0

        if download_state in ("completed", "cached") or progress >= 100:
            self._render_web_ready(web_id, item)
        else:
            self.after(0, lambda: self._show_cloud_polling(web_id, item, "web"))
            self._start_polling_worker(web_id, "web")

    def _handle_usenet_created(self, usenet_id: int, source: str):
        item = self._find_item_in_list(self.client.get_usenet_list(usenet_id=usenet_id), usenet_id)
        download_state = str(item.get("download_state", "")).lower() if item else ""
        progress = float(item.get("progress", 0)) if item else 0.0

        if download_state in ("completed", "cached") or progress >= 100:
            self._render_usenet_ready(usenet_id, item)
        else:
            self.after(0, lambda: self._show_cloud_polling(usenet_id, item, "usenet"))
            self._start_polling_worker(usenet_id, "usenet")

    def _find_item_in_list(self, item_list: List[Dict[str, Any]], target_id: int) -> Optional[Dict[str, Any]]:
        for it in item_list:
            if it.get("id") == target_id or it.get("torrent_id") == target_id or it.get("web_id") == target_id:
                return it
        return item_list[0] if item_list else None

    # ---------------- Cloud Polling for Uncached Items ----------------

    def _show_cloud_polling(self, item_id: int, item: Optional[Dict[str, Any]], item_type: str):
        self.generate_btn.configure(state="normal", text="Generate Download Link")
        self.cloud_card.pack(fill="x", padx=10, pady=10, after=self.generate_btn.master)

        name = item.get("name", f"{item_type.capitalize()} #{item_id}") if item else f"ID: {item_id}"
        state = item.get("download_state", "downloading") if item else "downloading"
        prog = item.get("progress", 0) if item else 0

        self.cloud_card_lbl.configure(text=f"Item Not Yet Cached: Downloading to Cloud ({name})")
        self.cloud_status_lbl.configure(
            text=f"Status: {state.capitalize()} | Progress: {prog}% | TorBox is caching this item...",
            text_color="#e5a50a",
        )
        self.cloud_pbar.set(float(prog) / 100.0)

    def _start_polling_worker(self, item_id: int, item_type: str):
        self._polling_stop_flag.clear()
        threading.Thread(target=self._poll_loop, args=(item_id, item_type), daemon=True).start()

    def _poll_loop(self, item_id: int, item_type: str):
        poll_interval = max(2, self.config.poll_interval)
        while not self._polling_stop_flag.is_set():
            time.sleep(poll_interval)
            if self._polling_stop_flag.is_set():
                break

            try:
                if item_type == "torrent":
                    items = self.client.get_torrent_list(torrent_id=item_id)
                elif item_type == "web":
                    items = self.client.get_web_list(web_id=item_id)
                else:
                    items = self.client.get_usenet_list(usenet_id=item_id)

                item = self._find_item_in_list(items, item_id)
                if not item:
                    continue

                state = str(item.get("download_state", "")).lower()
                progress = float(item.get("progress", 0))
                speed = item.get("download_speed", 0)
                seeds = item.get("seeds", 0)

                # Update UI
                self.after(0, lambda s=state, p=progress, sp=speed, sd=seeds: self._update_poll_ui(s, p, sp, sd))

                if state in ("completed", "cached") or progress >= 100:
                    # Finished caching!
                    if item_type == "torrent":
                        self._render_torrent_ready(item_id, item)
                    elif item_type == "web":
                        self._render_web_ready(item_id, item)
                    else:
                        self._render_usenet_ready(item_id, item)
                    break

            except Exception:
                pass

    def _update_poll_ui(self, state: str, progress: float, speed: float, seeds: int):
        self.cloud_pbar.set(progress / 100.0)
        speed_text = f" | Speed: {format_speed(speed)}" if speed else ""
        seeds_text = f" | Seeds: {seeds}" if seeds else ""
        self.cloud_status_lbl.configure(
            text=f"Status: {state.capitalize()} | Progress: {progress:.1f}%{speed_text}{seeds_text}",
            text_color="#e5a50a",
        )

    def _stop_polling(self):
        self._polling_stop_flag.set()
        self.cloud_status_lbl.configure(
            text="Stopped waiting. The item will continue downloading in your TorBox cloud.",
            text_color="gray",
        )

    # ---------------- Render Ready Download Links ----------------

    def _render_torrent_ready(self, torrent_id: int, item: Optional[Dict[str, Any]]):
        self._current_torrent_data = item
        # Get CDN download link
        zip_wanted = self.zip_var.get()
        cdn_link = self.client.request_torrent_dl(torrent_id=torrent_id, zip_link=zip_wanted, redirect=False)
        permalink = self.client.request_torrent_dl(torrent_id=torrent_id, zip_link=zip_wanted, redirect=True)

        self._generated_cdn_link = cdn_link
        self._generated_permalink = permalink

        self.after(0, lambda: self._display_results(item, cdn_link, permalink, torrent_id, "torrent"))

    def _render_web_ready(self, web_id: int, item: Optional[Dict[str, Any]]):
        cdn_link = self.client.request_web_dl(web_id=web_id, redirect=False)
        permalink = self.client.request_web_dl(web_id=web_id, redirect=True)
        self._generated_cdn_link = cdn_link
        self._generated_permalink = permalink
        self.after(0, lambda: self._display_results(item, cdn_link, permalink, web_id, "web"))

    def _render_usenet_ready(self, usenet_id: int, item: Optional[Dict[str, Any]]):
        cdn_link = self.client.request_usenet_dl(usenet_id=usenet_id, redirect=False)
        permalink = self.client.request_usenet_dl(usenet_id=usenet_id, redirect=True)
        self._generated_cdn_link = cdn_link
        self._generated_permalink = permalink
        self.after(0, lambda: self._display_results(item, cdn_link, permalink, usenet_id, "usenet"))

    def _display_results(
        self,
        item: Optional[Dict[str, Any]],
        cdn_link: str,
        permalink: str,
        item_id: int,
        item_type: str,
    ):
        self.generate_btn.configure(state="normal", text="Generate Download Link")
        self.cloud_card.pack_forget()

        name = item.get("name", f"Download_{item_id}") if item else f"Download_{item_id}"
        size = item.get("size", 0) if item else 0

        self.res_title_lbl.configure(text=name)
        self.res_size_lbl.configure(text=format_bytes(size))

        self.cdn_entry.delete(0, "end")
        self.cdn_entry.insert(0, cdn_link)

        self.perm_entry.delete(0, "end")
        self.perm_entry.insert(0, permalink)

        # Files dropdown if multiple files
        files = item.get("files", []) if item else []
        if files and len(files) > 1:
            self.file_picker_frame.pack(fill="x", padx=15, pady=(0, 8), before=self.cdn_entry.master.master)
            options = ["All Files (ZIP Archive)"] + [f"{f.get('name', f'File {idx}')} ({format_bytes(f.get('size', 0))})" for idx, f in enumerate(files)]
            self.file_option_menu.configure(values=options)
            self.file_option_menu.set(options[0])
        else:
            self.file_picker_frame.pack_forget()

        self.result_card.pack(fill="x", padx=10, pady=10)

        # Auto actions
        if self.copy_var.get() and cdn_link:
            self._copy_to_clipboard(cdn_link, notify=False)

        if self.browser_var.get() and cdn_link:
            webbrowser.open(cdn_link)

        self._notify(f"Download ready: {name}")

    def _on_file_selected(self, choice: str):
        """User selected a specific file from the dropdown."""
        if not self._current_torrent_data:
            return

        torrent_id = self._current_torrent_data.get("id") or self._current_torrent_data.get("torrent_id")
        if not torrent_id:
            return

        if choice.startswith("All Files"):
            cdn_link = self.client.request_torrent_dl(torrent_id=torrent_id, zip_link=True, redirect=False)
            permalink = self.client.request_torrent_dl(torrent_id=torrent_id, zip_link=True, redirect=True)
        else:
            # Find file index
            files = self._current_torrent_data.get("files", [])
            selected_idx = 0
            for idx, f in enumerate(files):
                label = f"{f.get('name', f'File {idx}')} ({format_bytes(f.get('size', 0))})"
                if label == choice:
                    selected_idx = f.get("id", idx)
                    break

            cdn_link = self.client.request_torrent_dl(torrent_id=torrent_id, file_id=selected_idx, zip_link=False, redirect=False)
            permalink = self.client.request_torrent_dl(torrent_id=torrent_id, file_id=selected_idx, zip_link=False, redirect=True)

        self._generated_cdn_link = cdn_link
        self._generated_permalink = permalink

        self.cdn_entry.delete(0, "end")
        self.cdn_entry.insert(0, cdn_link)

        self.perm_entry.delete(0, "end")
        self.perm_entry.insert(0, permalink)

    def _on_generate_error(self, err: str):
        self.generate_btn.configure(state="normal", text="Generate Download Link")
        self._notify(f"Generation error: {err}", is_error=True)

    # ---------------- Clipboard & Browser Helpers ----------------

    def _copy_to_clipboard(self, text: str, notify: bool = True):
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        if notify:
            self._notify("Link copied to clipboard!")

    def _open_in_browser(self):
        url = self.cdn_entry.get().strip() or self._generated_cdn_link
        if url:
            webbrowser.open(url)

    # ---------------- Local Downloader ----------------

    def _start_local_download(self):
        url = self.cdn_entry.get().strip() or self._generated_cdn_link
        if not url:
            self._notify("No download link available.", is_error=True)
            return

        dl_dir = self.config.ensure_download_dir()
        self.dl_progress_card.pack(fill="x", padx=10, pady=10)
        self.download_local_btn.configure(state="disabled")

        self.open_folder_btn.pack_forget()
        self.cancel_dl_btn.pack(side="right")
        self.dl_title_lbl.configure(text="Downloading to Local PC...")
        self.dl_pbar.set(0)

        self._active_downloader = FileDownloader(
            url=url,
            destination_dir=dl_dir,
            on_progress=self._on_local_dl_progress,
            on_complete=self._on_local_dl_complete,
            on_error=self._on_local_dl_error,
        )
        self._active_downloader.start()

    def _on_local_dl_progress(self, downloaded: int, total: int, speed: float, eta: float):
        fraction = (downloaded / total) if total > 0 else 0.0
        self.after(0, lambda: self._update_local_dl_ui(downloaded, total, speed, eta, fraction))

    def _update_local_dl_ui(self, downloaded: int, total: int, speed: float, eta: float, fraction: float):
        self.dl_pbar.set(fraction)
        self.dl_speed_lbl.configure(text=format_speed(speed))
        total_str = format_bytes(total) if total > 0 else "Unknown"
        self.dl_details_lbl.configure(
            text=f"{format_bytes(downloaded)} / {total_str} ({fraction * 100:.1f}%) | ETA: {format_eta(eta)}"
        )

    def _on_local_dl_complete(self, filepath: Path):
        self.after(0, lambda: self._finish_local_dl_ui(filepath))

    def _finish_local_dl_ui(self, filepath: Path):
        self.download_local_btn.configure(state="normal")
        self.dl_pbar.set(1.0)
        self.dl_title_lbl.configure(text=f"Download Complete: {filepath.name}")
        self.dl_speed_lbl.configure(text="Done")
        self.cancel_dl_btn.pack_forget()
        self.open_folder_btn.pack(side="right")
        self._notify(f"Downloaded: {filepath.name}")

    def _on_local_dl_error(self, err: str):
        self.after(0, lambda: self._error_local_dl_ui(err))

    def _error_local_dl_ui(self, err: str):
        self.download_local_btn.configure(state="normal")
        self.dl_title_lbl.configure(text="Download Failed")
        self.dl_details_lbl.configure(text=f"Error: {err}", text_color="#ff5555")
        self._notify(f"Download failed: {err}", is_error=True)

    def _cancel_local_download(self):
        if self._active_downloader:
            self._active_downloader.cancel()
        self.dl_progress_card.pack_forget()
        self.download_local_btn.configure(state="normal")

    def _open_destination_folder(self):
        dl_dir = self.config.ensure_download_dir()
        try:
            os.startfile(str(dl_dir))
        except Exception:
            pass

    def _notify(self, msg: str, is_error: bool = False):
        if self.on_notify:
            self.on_notify(msg, is_error=is_error)
