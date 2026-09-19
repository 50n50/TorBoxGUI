"""Library tab for viewing and managing TorBox cloud downloads."""

import os
from pathlib import Path
import threading
import tkinter as tk
from typing import Any, Dict, List, Optional
import webbrowser
import customtkinter as ctk

from torbox.client import TorBoxClient, TorBoxError
from torbox.config import Config
from torbox.utils import format_bytes, format_speed


class LibraryTab(ctk.CTkFrame):
    """View active and completed cloud downloads on the TorBox account."""

    def __init__(self, parent, client: Optional[TorBoxClient], config: Config, on_notify=None):
        super().__init__(parent, fg_color="transparent")
        self.client = client
        self.config = config
        self.on_notify = on_notify

        self._items: List[Dict[str, Any]] = []
        self._filtered_items: List[Dict[str, Any]] = []
        self._current_filter = "All"
        self._is_refreshing = False

        self._build_ui()

    def set_client(self, client: TorBoxClient):
        self.client = client

    def _build_ui(self):
        # Header Controls
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(5, 10))

        title_lbl = ctk.CTkLabel(
            header,
            text="Cloud Downloads Library",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_lbl.pack(side="left")

        self.refresh_btn = ctk.CTkButton(
            header,
            text="Refresh",
            width=90,
            height=32,
            command=self.refresh_items,
        )
        self.refresh_btn.pack(side="right")

        # Filter and Search bar
        filter_bar = ctk.CTkFrame(self, fg_color="transparent")
        filter_bar.pack(fill="x", padx=10, pady=(0, 10))

        self.segmented_filter = ctk.CTkSegmentedButton(
            filter_bar,
            values=["All", "Torrents", "Web DL", "Usenet"],
            command=self._on_filter_changed,
        )
        self.segmented_filter.set("All")
        self.segmented_filter.pack(side="left")

        self.search_entry = ctk.CTkEntry(
            filter_bar,
            placeholder_text="Search downloads...",
            width=220,
            height=32,
        )
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        # Scrollable items list
        self.items_container = ctk.CTkScrollableFrame(self, corner_radius=10)
        self.items_container.pack(fill="both", expand=True, padx=10, pady=5)

        self.empty_lbl = ctk.CTkLabel(
            self.items_container,
            text="No downloads found or account not connected.\nClick 'Refresh' to fetch items.",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        )
        self.empty_lbl.pack(pady=40)

    def refresh_items(self):
        if not self.client or not self.client.api_key:
            self._notify("TorBox API key is not configured.", is_error=True)
            return

        if self._is_refreshing:
            return

        self._is_refreshing = True
        self.refresh_btn.configure(state="disabled", text="Loading...")
        threading.Thread(target=self._fetch_items_worker, daemon=True).start()

    def _fetch_items_worker(self):
        all_items: List[Dict[str, Any]] = []
        try:
            # 1. Fetch Torrents
            try:
                torrents = self.client.get_torrent_list(bypass_cache=True)
                for t in torrents:
                    t["_type"] = "Torrents"
                    all_items.append(t)
            except Exception:
                pass

            # 2. Fetch Web Downloads
            try:
                web_dls = self.client.get_web_list(bypass_cache=True)
                for w in web_dls:
                    w["_type"] = "Web DL"
                    all_items.append(w)
            except Exception:
                pass

            # 3. Fetch Usenet
            try:
                usenet_dls = self.client.get_usenet_list(bypass_cache=True)
                for u in usenet_dls:
                    u["_type"] = "Usenet"
                    all_items.append(u)
            except Exception:
                pass

            self.after(0, lambda: self._on_fetch_success(all_items))
        except Exception as e:
            self.after(0, lambda: self._on_fetch_error(str(e)))

    def _on_fetch_success(self, items: List[Dict[str, Any]]):
        self._is_refreshing = False
        self.refresh_btn.configure(state="normal", text="Refresh")
        self._items = items
        self._apply_filter()

    def _on_fetch_error(self, err: str):
        self._is_refreshing = False
        self.refresh_btn.configure(state="normal", text="Refresh")
        self._notify(f"Failed to fetch library: {err}", is_error=True)

    def _on_filter_changed(self, value: str):
        self._current_filter = value
        self._apply_filter()

    def _on_search_changed(self, event=None):
        self._apply_filter()

    def _apply_filter(self):
        query = self.search_entry.get().strip().lower()
        filtered = []

        for it in self._items:
            # Type filter
            if self._current_filter != "All" and it.get("_type") != self._current_filter:
                continue

            # Text filter
            name = str(it.get("name", "")).lower()
            if query and query not in name:
                continue

            filtered.append(it)

        self._render_items(filtered)

    def _render_items(self, items: List[Dict[str, Any]]):
        # Clear existing children
        for child in self.items_container.winfo_children():
            child.destroy()

        if not items:
            lbl = ctk.CTkLabel(
                self.items_container,
                text="No downloads found.",
                font=ctk.CTkFont(size=14),
                text_color="gray",
            )
            lbl.pack(pady=40)
            return

        for it in items:
            self._create_item_card(it)

    def _create_item_card(self, it: Dict[str, Any]):
        card = ctk.CTkFrame(self.items_container, corner_radius=8)
        card.pack(fill="x", padx=5, pady=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 2))

        name = it.get("name", "Unnamed Item")
        title_lbl = ctk.CTkLabel(
            header,
            text=name,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            wraplength=550,
            justify="left",
        )
        title_lbl.pack(side="left")

        # Type tag & State badge
        itype = it.get("_type", "Torrents")
        tag_lbl = ctk.CTkLabel(
            header,
            text=f"[{itype}]",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        tag_lbl.pack(side="right", padx=(8, 0))

        state = str(it.get("download_state", "queued")).lower()
        badge_color = {
            "completed": "#44bb44",
            "cached": "#44bb44",
            "downloading": "#e5a50a",
            "seeding": "#3399ff",
            "queued": "gray",
            "error": "#ff5555",
        }.get(state, "gray")

        badge = ctk.CTkLabel(
            header,
            text=f" {state.upper()} ",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="white",
            fg_color=badge_color,
            corner_radius=4,
        )
        badge.pack(side="right")

        # Progress bar
        prog = float(it.get("progress", 0))
        pbar = ctk.CTkProgressBar(card, height=8)
        pbar.pack(fill="x", padx=12, pady=4)
        pbar.set(prog / 100.0)

        # Meta info row
        meta_row = ctk.CTkFrame(card, fg_color="transparent")
        meta_row.pack(fill="x", padx=12, pady=(2, 10))

        size_str = format_bytes(it.get("size", 0))
        speed = it.get("download_speed", 0)
        speed_str = f" | {format_speed(speed)}" if speed else ""
        meta_lbl = ctk.CTkLabel(
            meta_row,
            text=f"{size_str} ({prog:.1f}%){speed_str}",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        meta_lbl.pack(side="left")

        # Action Buttons
        del_btn = ctk.CTkButton(
            meta_row,
            text="Delete",
            width=65,
            height=26,
            fg_color="#a83232",
            hover_color="#c83e3e",
            command=lambda item=it: self._delete_item(item),
        )
        del_btn.pack(side="right", padx=(6, 0))

        link_btn = ctk.CTkButton(
            meta_row,
            text="Get Link",
            width=75,
            height=26,
            command=lambda item=it: self._get_item_link(item),
        )
        link_btn.pack(side="right")

    def _get_item_link(self, it: Dict[str, Any]):
        itype = it.get("_type")
        item_id = it.get("id") or it.get("torrent_id") or it.get("web_id") or it.get("usenet_id")
        if not item_id:
            return

        def worker():
            try:
                if itype == "Torrents":
                    cdn = self.client.request_torrent_dl(torrent_id=item_id, zip_link=True)
                    perm = self.client.request_torrent_dl(torrent_id=item_id, zip_link=True, redirect=True)
                elif itype == "Web DL":
                    cdn = self.client.request_web_dl(web_id=item_id)
                    perm = self.client.request_web_dl(web_id=item_id, redirect=True)
                else:
                    cdn = self.client.request_usenet_dl(usenet_id=item_id)
                    perm = self.client.request_usenet_dl(usenet_id=item_id, redirect=True)

                self.after(0, lambda: self._show_link_popup(it.get("name", "Download"), cdn, perm))
            except Exception as e:
                self.after(0, lambda: self._notify(f"Link error: {e}", is_error=True))

        threading.Thread(target=worker, daemon=True).start()

    def _show_link_popup(self, name: str, cdn_link: str, permalink: str):
        # Open a small link popup window
        popup = ctk.CTkToplevel(self)
        popup.title("Download Link")
        popup.geometry("480x280")
        popup.resizable(False, False)
        popup.transient(self.winfo_toplevel())
        popup.grab_set()

        title = ctk.CTkLabel(
            popup,
            text=name,
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=440,
            justify="left",
        )
        title.pack(padx=20, pady=(20, 10), anchor="w")

        cdn_lbl = ctk.CTkLabel(popup, text="Direct CDN Link:", font=ctk.CTkFont(weight="bold"))
        cdn_lbl.pack(padx=20, anchor="w")

        cdn_row = ctk.CTkFrame(popup, fg_color="transparent")
        cdn_row.pack(fill="x", padx=20, pady=(2, 10))

        cdn_ent = ctk.CTkEntry(cdn_row, height=32)
        cdn_ent.pack(side="left", fill="x", expand=True, padx=(0, 6))
        cdn_ent.insert(0, cdn_link)

        copy_btn = ctk.CTkButton(
            cdn_row,
            text="Copy",
            width=60,
            height=32,
            command=lambda: self._copy_to_clip(cdn_link),
        )
        copy_btn.pack(side="right")

        perm_lbl = ctk.CTkLabel(popup, text="Permalink (Redirect URL):", font=ctk.CTkFont(weight="bold"))
        perm_lbl.pack(padx=20, anchor="w")

        perm_row = ctk.CTkFrame(popup, fg_color="transparent")
        perm_row.pack(fill="x", padx=20, pady=(2, 15))

        perm_ent = ctk.CTkEntry(perm_row, height=32)
        perm_ent.pack(side="left", fill="x", expand=True, padx=(0, 6))
        perm_ent.insert(0, permalink)

        copy_perm_btn = ctk.CTkButton(
            perm_row,
            text="Copy",
            width=60,
            height=32,
            command=lambda: self._copy_to_clip(permalink),
        )
        copy_perm_btn.pack(side="right")

        act_row = ctk.CTkFrame(popup, fg_color="transparent")
        act_row.pack(fill="x", padx=20, pady=5)

        open_btn = ctk.CTkButton(
            act_row,
            text="Open in Browser",
            command=lambda: webbrowser.open(cdn_link),
        )
        open_btn.pack(side="left")

        close_btn = ctk.CTkButton(
            act_row,
            text="Close",
            fg_color="gray30",
            hover_color="gray40",
            command=popup.destroy,
        )
        close_btn.pack(side="right")

    def _delete_item(self, it: Dict[str, Any]):
        itype = it.get("_type")
        item_id = it.get("id") or it.get("torrent_id") or it.get("web_id") or it.get("usenet_id")
        name = it.get("name", "Item")
        if not item_id:
            return

        def worker():
            try:
                if itype == "Torrents":
                    self.client.control_torrent(torrent_id=item_id, operation="delete")
                elif itype == "Web DL":
                    self.client.control_web(web_id=item_id, operation="delete")
                else:
                    self.client.control_usenet(usenet_id=item_id, operation="delete")

                self.after(0, lambda: self._on_item_deleted(name))
            except Exception as e:
                self.after(0, lambda: self._notify(f"Delete failed: {e}", is_error=True))

        threading.Thread(target=worker, daemon=True).start()

    def _on_item_deleted(self, name: str):
        self._notify(f"Deleted from TorBox: {name}")
        self.refresh_items()

    def _copy_to_clip(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._notify("Copied to clipboard!")

    def _notify(self, msg: str, is_error: bool = False):
        if self.on_notify:
            self.on_notify(msg, is_error=is_error)
