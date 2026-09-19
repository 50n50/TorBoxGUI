"""Settings tab for TorBox GUI."""

import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Any, Dict, Optional
import webbrowser
import customtkinter as ctk

from torbox.client import AuthenticationError, TorBoxClient
from torbox.config import Config, get_default_download_dir, save_config
from torbox.utils import format_bytes


class SettingsTab(ctk.CTkScrollableFrame):
    """View for configuring API credentials, preferences, and viewing account info."""

    def __init__(self, parent, client: Optional[TorBoxClient], config: Config, on_notify=None, on_config_updated=None):
        super().__init__(parent, fg_color="transparent")
        self.client = client
        self.config = config
        self.on_notify = on_notify
        self.on_config_updated = on_config_updated

        self._build_ui()
        self.load_account_info()

    def set_client(self, client: TorBoxClient):
        self.client = client
        self.load_account_info()

    def _build_ui(self):
        # 1. Account Info Card
        acc_card = ctk.CTkFrame(self, corner_radius=10)
        acc_card.pack(fill="x", padx=10, pady=(5, 10))

        acc_header = ctk.CTkFrame(acc_card, fg_color="transparent")
        acc_header.pack(fill="x", padx=15, pady=(15, 8))

        lbl = ctk.CTkLabel(acc_header, text="TorBox Account", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(side="left")

        self.refresh_acc_btn = ctk.CTkButton(
            acc_header,
            text="Refresh",
            width=80,
            height=28,
            command=self.load_account_info,
        )
        self.refresh_acc_btn.pack(side="right")

        self.acc_info_lbl = ctk.CTkLabel(
            acc_card,
            text="Checking account status...",
            font=ctk.CTkFont(size=13),
            text_color="gray",
            justify="left",
            anchor="w",
        )
        self.acc_info_lbl.pack(fill="x", padx=15, pady=(0, 15))

        # 2. API Credentials Card
        api_card = ctk.CTkFrame(self, corner_radius=10)
        api_card.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(api_card, text="API Token", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 8)
        )

        key_row = ctk.CTkFrame(api_card, fg_color="transparent")
        key_row.pack(fill="x", padx=15, pady=(0, 6))

        self.key_entry = ctk.CTkEntry(key_row, height=36, show="*")
        self.key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if self.config.api_key:
            self.key_entry.insert(0, self.config.api_key)

        self.show_var = ctk.BooleanVar(value=False)
        self.show_btn = ctk.CTkButton(
            key_row,
            text="Show",
            width=65,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
            command=self._toggle_show_key,
        )
        self.show_btn.pack(side="right")

        # Get API key link
        link_btn = ctk.CTkButton(
            api_card,
            text="Get your API key at torbox.app/settings",
            font=ctk.CTkFont(size=12, underline=True),
            fg_color="transparent",
            hover_color=("gray85", "gray25"),
            text_color=("blue", "#4da6ff"),
            anchor="w",
            command=lambda: webbrowser.open("https://torbox.app/settings"),
        )
        link_btn.pack(anchor="w", padx=15, pady=(2, 15))

        # 3. Downloads & Paths Card
        dl_card = ctk.CTkFrame(self, corner_radius=10)
        dl_card.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(dl_card, text="Download Directory", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 8)
        )

        dl_row = ctk.CTkFrame(dl_card, fg_color="transparent")
        dl_row.pack(fill="x", padx=15, pady=(0, 15))

        self.dl_entry = ctk.CTkEntry(dl_row, height=36)
        self.dl_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.dl_entry.insert(0, self.config.download_dir or str(get_default_download_dir()))

        browse_btn = ctk.CTkButton(
            dl_row,
            text="Browse...",
            width=80,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
            command=self._browse_dir,
        )
        browse_btn.pack(side="left", padx=(0, 6))

        open_folder_btn = ctk.CTkButton(
            dl_row,
            text="Open Folder",
            width=90,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
            command=self._open_folder,
        )
        open_folder_btn.pack(side="right")

        # 4. Preferences & Behavior Card
        pref_card = ctk.CTkFrame(self, corner_radius=10)
        pref_card.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(pref_card, text="Preferences", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        self.copy_var = ctk.BooleanVar(value=self.config.auto_copy_link)
        ctk.CTkCheckBox(pref_card, text="Auto-copy generated download links to clipboard", variable=self.copy_var).pack(
            anchor="w", padx=15, pady=5
        )

        self.browser_var = ctk.BooleanVar(value=self.config.auto_start_browser)
        ctk.CTkCheckBox(pref_card, text="Automatically open generated download links in browser", variable=self.browser_var).pack(
            anchor="w", padx=15, pady=5
        )

        self.cli_dl_var = ctk.BooleanVar(value=self.config.auto_download_cli)
        ctk.CTkCheckBox(pref_card, text="Automatically start downloading files when using CLI mode", variable=self.cli_dl_var).pack(
            anchor="w", padx=15, pady=5
        )

        # Appearance mode & Poll interval
        extra_row = ctk.CTkFrame(pref_card, fg_color="transparent")
        extra_row.pack(fill="x", padx=15, pady=(10, 15))

        ctk.CTkLabel(extra_row, text="Theme:").pack(side="left", padx=(0, 6))
        self.theme_menu = ctk.CTkOptionMenu(
            extra_row,
            values=["Dark", "Light", "System"],
            width=110,
            command=self._on_theme_changed,
        )
        self.theme_menu.set(self.config.theme)
        self.theme_menu.pack(side="left", padx=(0, 25))

        ctk.CTkLabel(extra_row, text="Cache Poll Interval (sec):").pack(side="left", padx=(0, 6))
        self.poll_entry = ctk.CTkEntry(extra_row, width=60)
        self.poll_entry.insert(0, str(self.config.poll_interval))
        self.poll_entry.pack(side="left")

        # Save Button
        save_frame = ctk.CTkFrame(self, fg_color="transparent")
        save_frame.pack(fill="x", padx=10, pady=(10, 20))

        self.save_btn = ctk.CTkButton(
            save_frame,
            text="Save Settings",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._save_settings,
        )
        self.save_btn.pack(side="right")

    def _toggle_show_key(self):
        if self.show_var.get():
            self.show_var.set(False)
            self.key_entry.configure(show="*")
            self.show_btn.configure(text="Show")
        else:
            self.show_var.set(True)
            self.key_entry.configure(show="")
            self.show_btn.configure(text="Hide")

    def _browse_dir(self):
        current = self.dl_entry.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(initialdir=current, parent=self)
        if chosen:
            self.dl_entry.delete(0, "end")
            self.dl_entry.insert(0, chosen)

    def _open_folder(self):
        p = Path(self.dl_entry.get().strip()).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(p))
        except Exception:
            pass

    def _on_theme_changed(self, choice: str):
        ctk.set_appearance_mode(choice)

    def load_account_info(self):
        if not self.client or not self.client.api_key:
            self.acc_info_lbl.configure(text="Account: Not connected. Please enter your API token below.")
            return

        self.refresh_acc_btn.configure(state="disabled")
        self.acc_info_lbl.configure(text="Fetching account details from TorBox...")

        def worker():
            try:
                res = self.client.verify_token()
                data = res.get("data", {})
                email = data.get("email", "Unknown")
                plan = data.get("plan", "Standard")
                customer = data.get("customer", "Active")
                total_dl = format_bytes(data.get("total_downloaded", 0))

                text = f"Email: {email}\nPlan Tier: {plan.capitalize()} | Status: {customer}\nTotal Downloaded: {total_dl}"
                self.after(0, lambda: self._on_acc_success(text))
            except AuthenticationError as e:
                self.after(0, lambda: self._on_acc_error(f"Authentication Error: {e.detail}"))
            except Exception as e:
                self.after(0, lambda: self._on_acc_error(f"Failed to load account info: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_acc_success(self, text: str):
        self.refresh_acc_btn.configure(state="normal")
        self.acc_info_lbl.configure(text=text, text_color="white" if ctk.get_appearance_mode() == "Dark" else "black")

    def _on_acc_error(self, err: str):
        self.refresh_acc_btn.configure(state="normal")
        self.acc_info_lbl.configure(text=err, text_color="#ff5555")

    def _save_settings(self):
        token = self.key_entry.get().strip()
        dl_dir = self.dl_entry.get().strip() or str(get_default_download_dir())

        try:
            poll_sec = max(2, int(self.poll_entry.get().strip()))
        except ValueError:
            poll_sec = 3

        self.config.api_key = token
        self.config.download_dir = dl_dir
        self.config.auto_copy_link = self.copy_var.get()
        self.config.auto_start_browser = self.browser_var.get()
        self.config.auto_download_cli = self.cli_dl_var.get()
        self.config.poll_interval = poll_sec
        self.config.theme = self.theme_menu.get()

        save_config(self.config)
        self._notify("Settings saved successfully!")

        if self.on_config_updated:
            self.on_config_updated(self.config)

        self.load_account_info()

    def _notify(self, msg: str, is_error: bool = False):
        if self.on_notify:
            self.on_notify(msg, is_error=is_error)
