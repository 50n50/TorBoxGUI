"""Setup Dialog for first-time launch and API configuration."""

from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Optional
import webbrowser
import customtkinter as ctk

from torbox.client import TorBoxClient, AuthenticationError
from torbox.config import Config, save_config, get_default_download_dir


class SetupDialog(ctk.CTkToplevel):
    """First-start configuration wizard modal dialog."""

    def __init__(
        self,
        parent: ctk.CTk,
        config: Config,
        on_success: Optional[Callable[[Config], None]] = None,
        title: str = "TorBox Setup",
    ):
        super().__init__(parent)
        self.parent = parent
        self.config = config
        self.on_success = on_success

        self.title(title)
        self.geometry("540x480")
        self.resizable(False, False)

        # Modal behavior
        self.transient(parent)
        self.grab_set()

        self._center_window()
        self._create_widgets()

    def _center_window(self):
        self.update_idletasks()
        p_x = self.parent.winfo_x()
        p_y = self.parent.winfo_y()
        p_w = self.parent.winfo_width()
        p_h = self.parent.winfo_height()

        w = 540
        h = 480
        x = p_x + max(0, (p_w - w) // 2)
        y = p_y + max(0, (p_h - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _create_widgets(self):
        # Header Frame
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(25, 10))

        title_lbl = ctk.CTkLabel(
            header,
            text="Welcome to TorBox GUI",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            header,
            text="Please configure your TorBox API token to get started.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Main Card Frame
        card = ctk.CTkFrame(self, corner_radius=10)
        card.pack(fill="both", expand=True, padx=25, pady=10)

        # API Key Section
        api_lbl = ctk.CTkLabel(card, text="TorBox API Token *", font=ctk.CTkFont(size=13, weight="bold"))
        api_lbl.pack(anchor="w", padx=20, pady=(15, 5))

        api_input_frame = ctk.CTkFrame(card, fg_color="transparent")
        api_input_frame.pack(fill="x", padx=20)

        self.api_entry = ctk.CTkEntry(
            api_input_frame,
            placeholder_text="Enter your TorBox API token",
            show="*",
            height=36,
        )
        self.api_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if self.config.api_key:
            self.api_entry.insert(0, self.config.api_key)

        self.show_key_var = ctk.BooleanVar(value=False)
        self.toggle_btn = ctk.CTkButton(
            api_input_frame,
            text="Show",
            width=60,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
            command=self._toggle_show_key,
        )
        self.toggle_btn.pack(side="right")

        # Get API key link button
        link_btn = ctk.CTkButton(
            card,
            text="Open TorBox Account Settings to find your API key",
            font=ctk.CTkFont(size=12, underline=True),
            fg_color="transparent",
            hover_color=("gray85", "gray25"),
            text_color=("blue", "#4da6ff"),
            anchor="w",
            command=lambda: webbrowser.open("https://torbox.app/settings"),
        )
        link_btn.pack(anchor="w", padx=20, pady=(4, 15))

        # Download Directory Section
        dl_lbl = ctk.CTkLabel(card, text="Default Download Directory", font=ctk.CTkFont(size=13, weight="bold"))
        dl_lbl.pack(anchor="w", padx=20, pady=(5, 5))

        dl_frame = ctk.CTkFrame(card, fg_color="transparent")
        dl_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.dl_entry = ctk.CTkEntry(dl_frame, height=36)
        self.dl_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        initial_dir = self.config.download_dir or str(get_default_download_dir())
        self.dl_entry.insert(0, initial_dir)

        browse_btn = ctk.CTkButton(
            dl_frame,
            text="Browse...",
            width=80,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
            command=self._browse_dir,
        )
        browse_btn.pack(side="right")

        # Status / Feedback label
        self.status_lbl = ctk.CTkLabel(
            card,
            text="",
            font=ctk.CTkFont(size=12),
            wraplength=460,
        )
        self.status_lbl.pack(fill="x", padx=20, pady=(10, 5))

        # Action Buttons Frame
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=25, pady=(10, 25))

        self.save_btn = ctk.CTkButton(
            btn_frame,
            text="Validate & Save",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_validate_save,
        )
        self.save_btn.pack(side="right", padx=(10, 0))

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            height=40,
            fg_color="gray35",
            hover_color="gray45",
            command=self._on_cancel,
        )
        cancel_btn.pack(side="right")

    def _toggle_show_key(self):
        if self.show_key_var.get():
            self.show_key_var.set(False)
            self.api_entry.configure(show="*")
            self.toggle_btn.configure(text="Show")
        else:
            self.show_key_var.set(True)
            self.api_entry.configure(show="")
            self.toggle_btn.configure(text="Hide")

    def _browse_dir(self):
        current = self.dl_entry.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(initialdir=current, parent=self)
        if chosen:
            self.dl_entry.delete(0, "end")
            self.dl_entry.insert(0, chosen)

    def _on_validate_save(self):
        token = self.api_entry.get().strip()
        dl_dir = self.dl_entry.get().strip() or str(get_default_download_dir())

        if not token:
            self.status_lbl.configure(text="Error: API token cannot be empty.", text_color="#ff5555")
            return

        self.save_btn.configure(state="disabled", text="Testing token...")
        self.status_lbl.configure(text="Contacting TorBox API...", text_color="gray")

        # Run verification in background thread
        threading.Thread(target=self._verify_and_save_worker, args=(token, dl_dir), daemon=True).start()

    def _verify_and_save_worker(self, token: str, dl_dir: str):
        client = TorBoxClient(token, timeout=15)
        try:
            res = client.verify_token()
            user_data = res.get("data", {})
            email = user_data.get("email", "User")
            plan = user_data.get("plan", "Standard")

            # Update config
            self.config.api_key = token
            self.config.download_dir = dl_dir
            save_config(self.config)

            # UI Update on main thread
            self.after(0, lambda: self._on_verify_success(email, plan))
        except AuthenticationError as e:
            self.after(0, lambda: self._on_verify_error(f"Authentication failed: {e.detail}"))
        except Exception as e:
            self.after(0, lambda: self._on_verify_error(f"Connection error: {str(e)}"))

    def _on_verify_success(self, email: str, plan: str):
        self.status_lbl.configure(
            text=f"Success! Connected as {email} (Plan: {plan}).",
            text_color="#44bb44",
        )
        self.save_btn.configure(state="normal", text="Saved!")

        # Short pause before closing
        self.after(700, self._finish_success)

    def _on_verify_error(self, err_msg: str):
        self.status_lbl.configure(text=err_msg, text_color="#ff5555")
        self.save_btn.configure(state="normal", text="Validate & Save")

    def _finish_success(self):
        if self.on_success:
            self.on_success(self.config)
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.grab_release()
        self.destroy()
