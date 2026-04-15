"""
LinkedIn Easy Apply Automation - Main GUI Application
Automates job applications on LinkedIn using Selenium (no LinkedIn API required).
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import threading
import queue
from datetime import datetime

from linkedin_bot import LinkedInBot


CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "email": "",
    "password": "",
    "location": "United States",
    "job_roles": ["Software Engineer", "Python Developer"],
    "ignore_words": ["Senior", "Lead", "Manager", "Director", "Principal"],
    "min_delay": 3.0,
    "max_delay": 7.0,
    "max_applications": 50,
    "headless": False,
    "date_posted": "Any Time",
    "experience_level": "Any",
}

DATE_OPTIONS = ["Any Time", "Past Month", "Past Week", "Past 24 hours"]
EXPERIENCE_OPTIONS = ["Any", "Internship", "Entry level", "Associate", "Mid-Senior level", "Director"]


class LinkedInApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LinkedIn Easy Apply Bot")
        self.root.geometry("820x640")
        self.root.resizable(True, True)

        self.config = self._load_config()
        self.log_queue: queue.Queue = queue.Queue()
        self.bot: LinkedInBot | None = None
        self.bot_thread: threading.Thread | None = None
        self.is_running = False

        self._build_ui()
        self._poll_log_queue()

    # ------------------------------------------------------------------ config

    def _load_config(self) -> dict:
        cfg = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception:
                pass
        return cfg

    def _save_config(self):
        self._sync_config_from_ui()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            messagebox.showinfo("Saved", "Configuration saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save config:\n{e}")

    def _sync_config_from_ui(self):
        self.config["email"] = self.email_var.get().strip()
        self.config["password"] = self.password_var.get()
        self.config["location"] = self.location_var.get().strip()
        self.config["min_delay"] = float(self.min_delay_var.get())
        self.config["max_delay"] = float(self.max_delay_var.get())
        self.config["max_applications"] = int(self.max_apps_var.get())
        self.config["headless"] = self.headless_var.get()
        self.config["date_posted"] = self.date_var.get()
        self.config["experience_level"] = self.exp_var.get()
        self.config["job_roles"] = list(self.roles_lb.get(0, tk.END))
        self.config["ignore_words"] = list(self.ignore_lb.get(0, tk.END))

    # ------------------------------------------------------------------- ui

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        # Title
        ttk.Label(
            outer,
            text="LinkedIn Easy Apply Bot",
            font=("Helvetica", 15, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        # Notebook
        nb = ttk.Notebook(outer)
        nb.grid(row=1, column=0, sticky="nsew")

        self._tab_settings(nb)
        self._tab_roles(nb)
        self._tab_ignore(nb)
        self._tab_logs(nb)

        # Bottom controls
        ctrl = ttk.Frame(outer)
        ctrl.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.start_btn = ttk.Button(ctrl, text="Start Automation", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(ctrl, text="Stop", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(ctrl, text="Save Config", command=self._save_config).pack(side=tk.LEFT, padx=(0, 6))

        self.apps_label = ttk.Label(ctrl, text="Applied: 0")
        self.apps_label.pack(side=tk.RIGHT, padx=(6, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(outer, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).grid(
            row=3, column=0, sticky="ew", pady=(4, 0)
        )

    # ---- settings tab

    def _tab_settings(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Settings  ")
        frame.columnconfigure(1, weight=1)

        row = 0

        # Credentials
        ttk.Label(frame, text="LinkedIn Credentials", font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        row += 1

        ttk.Label(frame, text="Email:").grid(row=row, column=0, sticky="w", pady=3)
        self.email_var = tk.StringVar(value=self.config["email"])
        ttk.Entry(frame, textvariable=self.email_var, width=45).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(frame, text="Password:").grid(row=row, column=0, sticky="w", pady=3)
        self.password_var = tk.StringVar(value=self.config["password"])
        ttk.Entry(frame, textvariable=self.password_var, show="*", width=45).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8
        )
        row += 1

        # Search
        ttk.Label(frame, text="Search Settings", font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        row += 1

        ttk.Label(frame, text="Location:").grid(row=row, column=0, sticky="w", pady=3)
        self.location_var = tk.StringVar(value=self.config["location"])
        ttk.Entry(frame, textvariable=self.location_var, width=45).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(frame, text="Date Posted:").grid(row=row, column=0, sticky="w", pady=3)
        self.date_var = tk.StringVar(value=self.config["date_posted"])
        ttk.Combobox(frame, textvariable=self.date_var, values=DATE_OPTIONS, state="readonly", width=20).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        ttk.Label(frame, text="Experience Level:").grid(row=row, column=0, sticky="w", pady=3)
        self.exp_var = tk.StringVar(value=self.config["experience_level"])
        ttk.Combobox(frame, textvariable=self.exp_var, values=EXPERIENCE_OPTIONS, state="readonly", width=20).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        ttk.Label(frame, text="Max Applications:").grid(row=row, column=0, sticky="w", pady=3)
        self.max_apps_var = tk.StringVar(value=str(self.config["max_applications"]))
        ttk.Spinbox(frame, textvariable=self.max_apps_var, from_=1, to=500, width=8).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8
        )
        row += 1

        # Delays
        ttk.Label(frame, text="Delay Between Actions (seconds)", font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        row += 1

        ttk.Label(frame, text="Min Delay:").grid(row=row, column=0, sticky="w", pady=3)
        self.min_delay_var = tk.StringVar(value=str(self.config["min_delay"]))
        ttk.Spinbox(frame, textvariable=self.min_delay_var, from_=1, to=30, increment=0.5, width=8).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        ttk.Label(frame, text="Max Delay:").grid(row=row, column=0, sticky="w", pady=3)
        self.max_delay_var = tk.StringVar(value=str(self.config["max_delay"]))
        ttk.Spinbox(frame, textvariable=self.max_delay_var, from_=1, to=60, increment=0.5, width=8).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8
        )
        row += 1

        # Options
        ttk.Label(frame, text="Options", font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        row += 1

        self.headless_var = tk.BooleanVar(value=self.config["headless"])
        ttk.Checkbutton(
            frame,
            text="Headless mode (browser runs hidden in background)",
            variable=self.headless_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w")

    # ---- job roles tab

    def _tab_roles(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Job Roles  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Job roles / titles to search for (one per entry):",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.roles_lb, _ = self._make_listbox(frame, row=1)

        for role in self.config["job_roles"]:
            self.roles_lb.insert(tk.END, role)

        self.role_entry = ttk.Entry(frame, width=40)
        self.role_entry.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.role_entry.bind("<Return>", lambda _: self._add_role())

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(btn_row, text="Add", command=self._add_role).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Remove Selected", command=lambda: self._remove_item(self.roles_lb)).pack(side=tk.LEFT)

    # ---- ignore list tab

    def _tab_ignore(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Ignore List  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Words / phrases in job titles to skip (case-insensitive):",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.ignore_lb, _ = self._make_listbox(frame, row=1)

        for word in self.config["ignore_words"]:
            self.ignore_lb.insert(tk.END, word)

        self.ignore_entry = ttk.Entry(frame, width=40)
        self.ignore_entry.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.ignore_entry.bind("<Return>", lambda _: self._add_ignore())

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(btn_row, text="Add", command=self._add_ignore).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Remove Selected", command=lambda: self._remove_item(self.ignore_lb)).pack(side=tk.LEFT)

    # ---- logs tab

    def _tab_logs(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Logs  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        self.log_text.grid(row=0, column=0, sticky="nsew")

        # Color tags
        self.log_text.tag_config("INFO", foreground="#2196F3")
        self.log_text.tag_config("SUCCESS", foreground="#4CAF50")
        self.log_text.tag_config("WARN", foreground="#FF9800")
        self.log_text.tag_config("ERROR", foreground="#F44336")
        self.log_text.tag_config("SKIP", foreground="#9E9E9E")
        self.log_text.tag_config("DONE", foreground="#9C27B0")

        ttk.Button(frame, text="Clear Logs", command=self._clear_logs).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )

    # ---------------------------------------------------------------- helpers

    def _make_listbox(self, parent, row: int):
        container = ttk.Frame(parent)
        container.grid(row=row, column=0, columnspan=2, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        sb = ttk.Scrollbar(container)
        sb.grid(row=0, column=1, sticky="ns")

        lb = tk.Listbox(container, yscrollcommand=sb.set, selectmode=tk.SINGLE, height=10)
        lb.grid(row=0, column=0, sticky="nsew")
        sb.config(command=lb.yview)
        return lb, sb

    def _add_role(self):
        v = self.role_entry.get().strip()
        if v and v not in self.roles_lb.get(0, tk.END):
            self.roles_lb.insert(tk.END, v)
        self.role_entry.delete(0, tk.END)

    def _add_ignore(self):
        v = self.ignore_entry.get().strip()
        if v and v not in self.ignore_lb.get(0, tk.END):
            self.ignore_lb.insert(tk.END, v)
        self.ignore_entry.delete(0, tk.END)

    def _remove_item(self, lb: tk.Listbox):
        sel = lb.curselection()
        if sel:
            lb.delete(sel[0])

    def _clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ---------------------------------------------------------------- logging

    def _log(self, message: str):
        """Thread-safe log; called from bot thread via callback."""
        self.log_queue.put(message)

    def _poll_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self._write_log(msg)
        self.root.after(150, self._poll_log_queue)

    def _write_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {msg}\n"

        tag = "INFO"
        for t in ("SUCCESS", "WARN", "ERROR", "SKIP", "DONE", "INFO"):
            if f"[{t}]" in msg:
                tag = t
                break

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, full, tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # -------------------------------------------------------------- automation

    def _start(self):
        self._sync_config_from_ui()

        if not self.config["email"] or not self.config["password"]:
            messagebox.showerror("Missing credentials", "Please enter your LinkedIn email and password.")
            return

        if not self.config["job_roles"]:
            messagebox.showerror("No job roles", "Please add at least one job role to search for.")
            return

        if self.config["min_delay"] >= self.config["max_delay"]:
            messagebox.showerror("Invalid delays", "Min delay must be less than Max delay.")
            return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_var.set("Running...")
        self.apps_label.config(text="Applied: 0")

        self.bot = LinkedInBot(self.config, self._log, self._on_count_update)
        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()

    def _run_bot(self):
        try:
            self.bot.run()
        except Exception as exc:
            self._log(f"[ERROR] Unexpected crash: {exc}")
        finally:
            self.root.after(0, self._on_finished)

    def _stop(self):
        if self.bot:
            self.bot.request_stop()
        self.status_var.set("Stopping — waiting for browser to close...")
        self.stop_btn.config(state=tk.DISABLED)

    def _on_count_update(self, count: int):
        self.root.after(0, lambda: self.apps_label.config(text=f"Applied: {count}"))

    def _on_finished(self):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("Finished")


if __name__ == "__main__":
    root = tk.Tk()
    LinkedInApp(root)
    root.mainloop()
