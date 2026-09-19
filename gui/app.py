"""Main Application Window for TorBox GUI."""

from pathlib import Path
import threading
import tkinter as tk
from typing import Optional
import customtkinter as ctk

from torbox.client import TorBoxClient
from torbox.config import Config, load_config
from gui.download_tab import DownloadTab
from gui.library_tab import LibraryTab
from gui.settings_tab import SettingsTab
from gui.setup_dialog import SetupDialog


class TorBoxApp(ctk.CTk):
    """Main TorBox Desktop GUI Application."""

    def __init__(self, config: Optional[Config] = None, prefill_source: Optional[str] = None):
        super().__init__()

        self.config = config or load_config()
        self.prefill_source = prefill_source

        # Appearance configuration
        ctk.set_appearance_mode(self.config.theme)
        ctk.set_default_color_theme("blue")

        # Window properties
        self.title("TorBox GUI")
        self.geometry("980x680")
        self.minsize(880, 580)

        # Initialize API client if key exists
        self.client: Optional[TorBoxClient] = None
        if self.config.is_valid():
            self.client = TorBoxClient(self.config.api_key)

        self._active_tab = "download"
        self._build_layout()

        # Handle prefill or first-start setup
        self.after(200, self._check_first_start)

    def _build_layout(self):
        # Configure grid: Column 0 is sidebar (width 200), Column 1 is main area
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---------------- Sidebar ----------------
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        # Logo / Title
        brand_lbl = ctk.CTkLabel(
            self.sidebar_frame,
            text="TorBox GUI",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        brand_lbl.grid(row=0, column=0, padx=20, pady=(20, 2), sticky="w")

        sub_lbl = ctk.CTkLabel(
            self.sidebar_frame,
            text="Debrid & Cloud Manager",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        sub_lbl.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        # Navigation Buttons
        self.btn_download = ctk.CTkButton(
            self.sidebar_frame,
            text="Quick Download",
            height=40,
            corner_radius=6,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._switch_tab("download"),
        )
        self.btn_download.grid(row=2, column=0, padx=15, pady=5, sticky="ew")

        self.btn_library = ctk.CTkButton(
            self.sidebar_frame,
            text="Cloud Library",
            height=40,
            corner_radius=6,
            anchor="w",
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray75", "gray25"),
            font=ctk.CTkFont(size=13),
            command=lambda: self._switch_tab("library"),
        )
        self.btn_library.grid(row=3, column=0, padx=15, pady=5, sticky="ew")

        self.btn_settings = ctk.CTkButton(
            self.sidebar_frame,
            text="Settings",
            height=40,
            corner_radius=6,
            anchor="w",
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray75", "gray25"),
            font=ctk.CTkFont(size=13),
            command=lambda: self._switch_tab("settings"),
        )
        self.btn_settings.grid(row=4, column=0, padx=15, pady=5, sticky="ew")

        # Bottom of sidebar: status indicator & version
        status_box = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        status_box.grid(row=6, column=0, padx=15, pady=15, sticky="s")

        self.api_status_indicator = ctk.CTkLabel(
            status_box,
            text="API: Checking...",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self.api_status_indicator.pack(anchor="w")

        ver_lbl = ctk.CTkLabel(
            status_box,
            text="v1.0.0",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
        )
        ver_lbl.pack(anchor="w", pady=(2, 0))

        # ---------------- Main Content Area ----------------
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # Tab Views
        self.tab_download = DownloadTab(
            self.content_frame,
            client=self.client,
            config=self.config,
            on_notify=self.notify,
        )
        self.tab_library = LibraryTab(
            self.content_frame,
            client=self.client,
            config=self.config,
            on_notify=self.notify,
        )
        self.tab_settings = SettingsTab(
            self.content_frame,
            client=self.client,
            config=self.config,
            on_notify=self.notify,
            on_config_updated=self._on_config_updated,
        )

        # Place default tab
        self.tab_download.grid(row=0, column=0, sticky="nsew")

        # ---------------- Notification Toast Bar ----------------
        self.toast_bar = ctk.CTkLabel(
            self,
            text="",
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray80", "gray20"),
            corner_radius=4,
        )
        # Toast placed at bottom when triggered

    def _switch_tab(self, tab_name: str):
        self._active_tab = tab_name

        # Reset button styles
        for btn in (self.btn_download, self.btn_library, self.btn_settings):
            btn.configure(
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                font=ctk.CTkFont(size=13),
            )

        # Hide all tabs
        self.tab_download.grid_forget()
        self.tab_library.grid_forget()
        self.tab_settings.grid_forget()

        # Show target tab
        if tab_name == "download":
            self.btn_download.configure(
                fg_color=("#1f6aa5", "#2b84c8"),
                text_color="white",
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            self.tab_download.grid(row=0, column=0, sticky="nsew")

        elif tab_name == "library":
            self.btn_library.configure(
                fg_color=("#1f6aa5", "#2b84c8"),
                text_color="white",
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            self.tab_library.grid(row=0, column=0, sticky="nsew")
            self.tab_library.refresh_items()

        elif tab_name == "settings":
            self.btn_settings.configure(
                fg_color=("#1f6aa5", "#2b84c8"),
                text_color="white",
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            self.tab_settings.grid(row=0, column=0, sticky="nsew")

    def _check_first_start(self):
        if not self.config.is_valid():
            self._open_setup_dialog()
        else:
            self._update_connection_status()

        if self.prefill_source:
            self.tab_download.set_prefilled_input(self.prefill_source)

    def _open_setup_dialog(self):
        SetupDialog(
            parent=self,
            config=self.config,
            on_success=self._on_setup_completed,
        )

    def _on_setup_completed(self, updated_config: Config):
        self.config = updated_config
        self._on_config_updated(updated_config)
        self.notify("TorBox API configured successfully!")

    def _on_config_updated(self, updated_config: Config):
        self.config = updated_config
        if self.config.is_valid():
            self.client = TorBoxClient(self.config.api_key)
        else:
            self.client = None

        self.tab_download.set_client(self.client)
        self.tab_library.set_client(self.client)
        self.tab_settings.set_client(self.client)

        self._update_connection_status()

    def _update_connection_status(self):
        if not self.client or not self.client.api_key:
            self.api_status_indicator.configure(text="API: Not Configured", text_color="#ff5555")
            return

        self.api_status_indicator.configure(text="API: Connecting...", text_color="gray")

        def worker():
            try:
                res = self.client.verify_token()
                plan = res.get("data", {}).get("plan", "Standard")
                self.after(
                    0,
                    lambda: self.api_status_indicator.configure(
                        text=f"API: Connected ({plan})",
                        text_color="#44bb44",
                    ),
                )
            except Exception:
                self.after(
                    0,
                    lambda: self.api_status_indicator.configure(
                        text="API: Connection Error",
                        text_color="#ff5555",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def notify(self, message: str, is_error: bool = False, duration_ms: int = 4000):
        """Display non-blocking notification toast."""
        color = "#a83232" if is_error else ("#2b84c8" if ctk.get_appearance_mode() == "Dark" else "#1f6aa5")
        self.toast_bar.configure(text=f"  {message}  ", fg_color=color, text_color="white")
        self.toast_bar.place(relx=0.5, rely=0.96, anchor="center")

        def hide():
            self.toast_bar.place_forget()

        self.after(duration_ms, hide)
