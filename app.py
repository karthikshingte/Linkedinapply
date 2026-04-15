"""
LinkedIn Easy Apply Automation - Main GUI Application
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import threading
import queue
from datetime import datetime

from linkedin_bot import LinkedInBot, FeedScanner


CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "email": "",
    "password": "",
    "location": "United States",
    "job_roles": ["Software Engineer", "Python Developer"],
    "ignore_words": ["Senior", "Lead", "Manager", "Director", "Principal"],
    "job_type_keywords": [],
    "strict_role_match": True,
    "min_delay": 3.0,
    "max_delay": 7.0,
    "max_applications": 50,
    "headless": False,
    "date_posted": "Any Time",
    "experience_level": "Any",
    # Feed scanner
    "feed_keywords": ["C2C", "Contract", "W2", "Hiring", "Looking for"],
    "feed_max_scrolls": 30,
}

DATE_OPTIONS       = ["Any Time", "Past Month", "Past Week", "Past 24 hours"]
EXPERIENCE_OPTIONS = ["Any", "Internship", "Entry level", "Associate", "Mid-Senior level", "Director"]
SUGGESTED_JOB_KW   = ["Full-time", "Part-time", "Contract", "Temporary", "Internship",
                       "C2C", "W2", "1099", "Remote", "Hybrid", "On-site"]
SUGGESTED_FEED_KW  = ["C2C", "Contract", "W2", "1099", "Hiring", "Looking for", "Urgent",
                       "Remote", "Python", "Java", "Full Stack", "Data Engineer"]


class LinkedInApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LinkedIn Easy Apply Bot")
        self.root.geometry("880x680")
        self.root.resizable(True, True)

        self.config = self._load_config()

        # Separate queues so both bots can log simultaneously
        self.job_log_queue:  queue.Queue = queue.Queue()
        self.feed_log_queue: queue.Queue = queue.Queue()

        self.bot:         LinkedInBot | None = None
        self.feed_scanner: FeedScanner | None = None
        self.bot_thread:   threading.Thread | None = None
        self.feed_thread:  threading.Thread | None = None
        self.is_running      = False
        self.feed_is_running = False

        self._build_ui()
        self._poll_queues()

    # ──────────────────────────────────────────── config

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
            messagebox.showinfo("Saved", "Configuration saved.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save config:\n{e}")

    def _sync_config_from_ui(self):
        """Push all UI values into self.config (shared with the running bot)."""
        self.config["email"]             = self.email_var.get().strip()
        self.config["password"]          = self.password_var.get()
        self.config["location"]          = self.location_var.get().strip()
        self.config["min_delay"]         = float(self.min_delay_var.get())
        self.config["max_delay"]         = float(self.max_delay_var.get())
        self.config["max_applications"]  = int(self.max_apps_var.get())
        self.config["headless"]          = self.headless_var.get()
        self.config["date_posted"]       = self.date_var.get()
        self.config["experience_level"]  = self.exp_var.get()
        self.config["strict_role_match"] = self.strict_role_var.get()
        self.config["job_roles"]         = list(self.roles_lb.get(0, tk.END))
        self.config["ignore_words"]      = list(self.ignore_lb.get(0, tk.END))
        self.config["job_type_keywords"] = list(self.kw_lb.get(0, tk.END))
        self.config["feed_keywords"]     = list(self.feed_kw_lb.get(0, tk.END))
        self.config["feed_max_scrolls"]  = int(self.feed_scrolls_var.get())

    def _apply_changes(self):
        """
        Push UI values into the shared config dict mid-run.
        The running bot reads self.config dynamically on every action,
        so delays and filters take effect on the very next job processed.
        Role list / ignore list changes take effect at the start of the next role search.
        """
        self._sync_config_from_ui()
        self.status_var.set("Changes applied — take effect on next action")
        self.root.after(3000, lambda: self.status_var.set(
            "Running..." if self.is_running else "Ready"
        ))

    # ──────────────────────────────────────────── ui

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        ttk.Label(outer, text="LinkedIn Easy Apply Bot",
                  font=("Helvetica", 15, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

        nb = ttk.Notebook(outer)
        nb.grid(row=1, column=0, sticky="nsew")

        self._tab_settings(nb)
        self._tab_roles(nb)
        self._tab_ignore(nb)
        self._tab_filters(nb)
        self._tab_feed_scanner(nb)
        self._tab_logs(nb)

        # ── Job bot controls ──────────────────────────────────────
        job_ctrl = ttk.LabelFrame(outer, text="Job Bot", padding=(8, 4))
        job_ctrl.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.start_btn = ttk.Button(job_ctrl, text="Start Automation", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(job_ctrl, text="Stop", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.apply_btn = ttk.Button(job_ctrl, text="Apply Changes Now",
                                    command=self._apply_changes)
        self.apply_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(job_ctrl,
                  text="← push UI changes to running bot without restarting",
                  foreground="#555555").pack(side=tk.LEFT, padx=(0, 12))

        ttk.Button(job_ctrl, text="Save Config", command=self._save_config).pack(side=tk.LEFT)
        self.apps_label = ttk.Label(job_ctrl, text="Applied: 0", font=("Helvetica", 9, "bold"))
        self.apps_label.pack(side=tk.RIGHT)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(outer, textvariable=self.status_var,
                  relief=tk.SUNKEN, anchor=tk.W).grid(row=3, column=0, sticky="ew", pady=(4, 0))

    # ── settings tab ──────────────────────────────────────────────

    def _tab_settings(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Settings  ")
        frame.columnconfigure(1, weight=1)
        r = 0

        def section(lbl):
            nonlocal r
            ttk.Label(frame, text=lbl, font=("Helvetica", 10, "bold")).grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(8 if r else 0, 4))
            r += 1

        def field(lbl, widget_fn):
            nonlocal r
            ttk.Label(frame, text=lbl).grid(row=r, column=0, sticky="w", pady=3)
            widget_fn(r)
            r += 1

        def sep():
            nonlocal r
            ttk.Separator(frame).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
            r += 1

        section("LinkedIn Credentials")
        self.email_var = tk.StringVar(value=self.config["email"])
        field("Email:", lambda r: ttk.Entry(frame, textvariable=self.email_var, width=45).grid(
            row=r, column=1, sticky="ew"))

        self.password_var = tk.StringVar(value=self.config["password"])
        field("Password:", lambda r: ttk.Entry(frame, textvariable=self.password_var,
              show="*", width=45).grid(row=r, column=1, sticky="ew"))

        sep(); section("Search Settings")

        self.location_var = tk.StringVar(value=self.config["location"])
        field("Location:", lambda r: ttk.Entry(frame, textvariable=self.location_var, width=45).grid(
            row=r, column=1, sticky="ew"))

        self.date_var = tk.StringVar(value=self.config["date_posted"])
        field("Date Posted:", lambda r: ttk.Combobox(frame, textvariable=self.date_var,
              values=DATE_OPTIONS, state="readonly", width=20).grid(row=r, column=1, sticky="w"))

        self.exp_var = tk.StringVar(value=self.config["experience_level"])
        field("Experience Level:", lambda r: ttk.Combobox(frame, textvariable=self.exp_var,
              values=EXPERIENCE_OPTIONS, state="readonly", width=20).grid(row=r, column=1, sticky="w"))

        self.max_apps_var = tk.StringVar(value=str(self.config["max_applications"]))
        field("Max Applications:", lambda r: ttk.Spinbox(frame, textvariable=self.max_apps_var,
              from_=1, to=500, width=8).grid(row=r, column=1, sticky="w"))

        sep(); section("Delay Between Actions (seconds)")

        self.min_delay_var = tk.StringVar(value=str(self.config["min_delay"]))
        field("Min Delay:", lambda r: ttk.Spinbox(frame, textvariable=self.min_delay_var,
              from_=1, to=30, increment=0.5, width=8).grid(row=r, column=1, sticky="w"))

        self.max_delay_var = tk.StringVar(value=str(self.config["max_delay"]))
        field("Max Delay:", lambda r: ttk.Spinbox(frame, textvariable=self.max_delay_var,
              from_=1, to=60, increment=0.5, width=8).grid(row=r, column=1, sticky="w"))

        ttk.Label(frame, text="Tip: click 'Apply Changes Now' to push new delays to a running bot.",
                  foreground="#0277BD").grid(row=r, column=0, columnspan=2, sticky="w", pady=(2, 0))
        r += 1

        sep(); section("Options")
        self.headless_var = tk.BooleanVar(value=self.config["headless"])
        ttk.Checkbutton(frame, text="Headless mode (browser runs hidden)",
                        variable=self.headless_var).grid(row=r, column=0, columnspan=2, sticky="w")

    # ── job roles tab ─────────────────────────────────────────────

    def _tab_roles(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Job Roles  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="Job roles / titles to search for:").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.roles_lb, _ = self._make_listbox(frame, row=1)
        for v in self.config["job_roles"]:
            self.roles_lb.insert(tk.END, v)
        self.role_entry = ttk.Entry(frame, width=40)
        self.role_entry.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.role_entry.bind("<Return>", lambda _: self._add_to(self.roles_lb, self.role_entry))
        self._btn_row(frame, 3,
                      lambda: self._add_to(self.roles_lb, self.role_entry),
                      lambda: self._remove_from(self.roles_lb))

    # ── ignore list tab ───────────────────────────────────────────

    def _tab_ignore(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Ignore List  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="Words in job titles to skip (case-insensitive):").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.ignore_lb, _ = self._make_listbox(frame, row=1)
        for v in self.config["ignore_words"]:
            self.ignore_lb.insert(tk.END, v)
        self.ignore_entry = ttk.Entry(frame, width=40)
        self.ignore_entry.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.ignore_entry.bind("<Return>", lambda _: self._add_to(self.ignore_lb, self.ignore_entry))
        self._btn_row(frame, 3,
                      lambda: self._add_to(self.ignore_lb, self.ignore_entry),
                      lambda: self._remove_from(self.ignore_lb))

    # ── filters tab ───────────────────────────────────────────────

    def _tab_filters(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Filters  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        role_box = ttk.LabelFrame(frame, text="Role Title Matching", padding=10)
        role_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        role_box.columnconfigure(0, weight=1)
        self.strict_role_var = tk.BooleanVar(value=self.config.get("strict_role_match", True))
        ttk.Checkbutton(role_box,
                        text="Only apply if job title contains keywords from my Job Roles list",
                        variable=self.strict_role_var).grid(row=0, column=0, sticky="w")
        ttk.Label(role_box, text='e.g. searching "Python Developer" skips "Marketing Manager"',
                  foreground="#666").grid(row=1, column=0, sticky="w", pady=(2, 0))

        kw_box = ttk.LabelFrame(frame, text="Required Job Type Keywords", padding=10)
        kw_box.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        kw_box.columnconfigure(0, weight=1)
        ttk.Label(kw_box,
                  text="At least one keyword must appear in title or description. Leave empty = no filter.",
                  foreground="#444").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        sug = ttk.Frame(kw_box)
        sug.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(sug, text="Quick add: ").pack(side=tk.LEFT)
        for kw in SUGGESTED_JOB_KW:
            ttk.Button(sug, text=kw, width=len(kw)+1,
                       command=lambda k=kw: self._quick_add(self.kw_lb, k)).pack(side=tk.LEFT, padx=2)
        kw_box.rowconfigure(2, weight=1)
        self.kw_lb, _ = self._make_listbox(kw_box, row=2)
        self.kw_lb.configure(height=5)
        for kw in self.config.get("job_type_keywords", []):
            self.kw_lb.insert(tk.END, kw)
        self.kw_entry = ttk.Entry(kw_box, width=30)
        self.kw_entry.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.kw_entry.bind("<Return>", lambda _: self._add_to(self.kw_lb, self.kw_entry))
        self._btn_row(kw_box, 4,
                      lambda: self._add_to(self.kw_lb, self.kw_entry),
                      lambda: self._remove_from(self.kw_lb))

    # ── feed scanner tab ──────────────────────────────────────────

    def _tab_feed_scanner(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Feed Scanner  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Keywords
        kw_box = ttk.LabelFrame(frame, text="Keywords to find in feed posts", padding=10)
        kw_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        kw_box.columnconfigure(0, weight=1)

        ttk.Label(kw_box,
                  text="Any post containing at least one keyword will be saved to linkedin_feed_posts.xlsx.",
                  foreground="#444").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        sug = ttk.Frame(kw_box)
        sug.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(sug, text="Quick add: ").pack(side=tk.LEFT)
        for kw in SUGGESTED_FEED_KW:
            ttk.Button(sug, text=kw, width=len(kw)+1,
                       command=lambda k=kw: self._quick_add(self.feed_kw_lb, k)).pack(side=tk.LEFT, padx=2)

        kw_box.rowconfigure(2, weight=1)
        self.feed_kw_lb, _ = self._make_listbox(kw_box, row=2)
        self.feed_kw_lb.configure(height=6)
        for kw in self.config.get("feed_keywords", []):
            self.feed_kw_lb.insert(tk.END, kw)

        self.feed_kw_entry = ttk.Entry(kw_box, width=30)
        self.feed_kw_entry.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.feed_kw_entry.bind("<Return>", lambda _: self._add_to(self.feed_kw_lb, self.feed_kw_entry))
        self._btn_row(kw_box, 4,
                      lambda: self._add_to(self.feed_kw_lb, self.feed_kw_entry),
                      lambda: self._remove_from(self.feed_kw_lb))

        # Options row
        opt = ttk.Frame(frame)
        opt.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(opt, text="Max scrolls through feed:").pack(side=tk.LEFT)
        self.feed_scrolls_var = tk.StringVar(value=str(self.config.get("feed_max_scrolls", 30)))
        ttk.Spinbox(opt, textvariable=self.feed_scrolls_var,
                    from_=5, to=200, width=6).pack(side=tk.LEFT, padx=(6, 20))
        ttk.Label(opt, text="(each scroll loads ~3–5 more posts)",
                  foreground="#666").pack(side=tk.LEFT)

        # Feed log
        self.feed_log_text = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9), height=10)
        self.feed_log_text.grid(row=2, column=0, sticky="nsew")
        for tag, fg in [("INFO","#1565C0"),("SUCCESS","#2E7D32"),("WARN","#E65100"),
                        ("ERROR","#B71C1C"),("FOUND","#6A1B9A"),("DONE","#2E7D32"),("DEBUG","#999")]:
            self.feed_log_text.tag_config(tag, foreground=fg)

        # Feed controls
        feed_ctrl = ttk.Frame(frame)
        feed_ctrl.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.feed_start_btn = ttk.Button(feed_ctrl, text="Scan Feed Now",
                                         command=self._start_feed_scan)
        self.feed_start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.feed_stop_btn  = ttk.Button(feed_ctrl, text="Stop Scan",
                                         command=self._stop_feed_scan, state=tk.DISABLED)
        self.feed_stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(feed_ctrl, text="Clear Log",
                   command=self._clear_feed_log).pack(side=tk.LEFT, padx=(0, 6))
        self.feed_found_label = ttk.Label(feed_ctrl, text="Found: 0", font=("Helvetica", 9, "bold"))
        self.feed_found_label.pack(side=tk.RIGHT)

    # ── logs tab ──────────────────────────────────────────────────

    def _tab_logs(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="  Job Bot Logs  ")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD,
                                                   state=tk.DISABLED, font=("Consolas", 9))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        for tag, fg in [("INFO","#1565C0"),("SUCCESS","#2E7D32"),("WARN","#E65100"),
                        ("ERROR","#B71C1C"),("SKIP","#757575"),("DONE","#6A1B9A"),("DEBUG","#999")]:
            self.log_text.tag_config(tag, foreground=fg)
        ttk.Button(frame, text="Clear Logs", command=self._clear_logs).grid(
            row=1, column=0, sticky="w", pady=(4, 0))

    # ──────────────────────────────────────────── shared helpers

    def _make_listbox(self, parent, row: int):
        c = ttk.Frame(parent)
        c.grid(row=row, column=0, columnspan=2, sticky="nsew")
        c.columnconfigure(0, weight=1)
        c.rowconfigure(0, weight=1)
        sb = ttk.Scrollbar(c)
        sb.grid(row=0, column=1, sticky="ns")
        lb = tk.Listbox(c, yscrollcommand=sb.set, selectmode=tk.SINGLE, height=10)
        lb.grid(row=0, column=0, sticky="nsew")
        sb.config(command=lb.yview)
        return lb, sb

    def _btn_row(self, parent, row, add_cmd, rm_cmd):
        f = ttk.Frame(parent)
        f.grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(f, text="Add",             command=add_cmd).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(f, text="Remove Selected", command=rm_cmd).pack(side=tk.LEFT)

    def _add_to(self, lb, entry):
        v = entry.get().strip()
        if v and v not in lb.get(0, tk.END):
            lb.insert(tk.END, v)
        entry.delete(0, tk.END)

    def _remove_from(self, lb):
        sel = lb.curselection()
        if sel:
            lb.delete(sel[0])

    def _quick_add(self, lb, kw: str):
        if kw not in lb.get(0, tk.END):
            lb.insert(tk.END, kw)

    # ──────────────────────────────────────────── logging

    def _log_job(self, msg: str):
        self.job_log_queue.put(("job", msg))

    def _log_feed(self, msg: str):
        self.feed_log_queue.put(("feed", msg))

    def _poll_queues(self):
        for q in (self.job_log_queue, self.feed_log_queue):
            while not q.empty():
                kind, msg = q.get_nowait()
                self._write_log(msg, kind)
        self.root.after(150, self._poll_queues)

    def _write_log(self, msg: str, kind: str = "job"):
        widget = self.log_text if kind == "job" else self.feed_log_text
        ts   = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {msg}\n"
        tag  = "INFO"
        for t in ("SUCCESS","FOUND","WARN","ERROR","SKIP","DONE","DEBUG","INFO"):
            if f"[{t}]" in msg:
                tag = t
                break
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, full, tag)
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)

    def _clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_feed_log(self):
        self.feed_log_text.config(state=tk.NORMAL)
        self.feed_log_text.delete("1.0", tk.END)
        self.feed_log_text.config(state=tk.DISABLED)

    # ──────────────────────────────────────────── job bot

    def _start(self):
        self._sync_config_from_ui()
        if not self.config["email"] or not self.config["password"]:
            messagebox.showerror("Missing credentials", "Enter your LinkedIn email and password.")
            return
        if not self.config["job_roles"]:
            messagebox.showerror("No job roles", "Add at least one job role to search for.")
            return
        if float(self.config["min_delay"]) >= float(self.config["max_delay"]):
            messagebox.showerror("Invalid delays", "Min delay must be less than Max delay.")
            return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_var.set("Running...")
        self.apps_label.config(text="Applied: 0")

        # Bot receives self.config BY REFERENCE — Apply Changes Now just updates
        # this same dict, and the bot reads it dynamically on every action.
        self.bot = LinkedInBot(self.config, self._log_job, self._on_count_update)
        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()

    def _run_bot(self):
        try:
            self.bot.run()
        except Exception as exc:
            self._log_job(f"[ERROR] Unexpected crash: {exc}")
        finally:
            self.root.after(0, self._on_bot_finished)

    def _stop(self):
        if self.bot:
            self.bot.request_stop()
        self.status_var.set("Stopping…")
        self.stop_btn.config(state=tk.DISABLED)

    def _on_count_update(self, count: int):
        self.root.after(0, lambda: self.apps_label.config(text=f"Applied: {count}"))

    def _on_bot_finished(self):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("Finished")

    # ──────────────────────────────────────────── feed scanner

    def _start_feed_scan(self):
        self._sync_config_from_ui()
        if not self.config["email"] or not self.config["password"]:
            messagebox.showerror("Missing credentials", "Enter your LinkedIn email and password.")
            return
        if not self.config.get("feed_keywords"):
            messagebox.showerror("No keywords", "Add at least one keyword to search for in the feed.")
            return

        self.feed_is_running = True
        self.feed_start_btn.config(state=tk.DISABLED)
        self.feed_stop_btn.config(state=tk.NORMAL)
        self.feed_found_label.config(text="Found: 0")

        self.feed_scanner = FeedScanner(self.config, self._log_feed, self._on_feed_found)
        self.feed_thread = threading.Thread(target=self._run_feed_scan, daemon=True)
        self.feed_thread.start()

    def _run_feed_scan(self):
        try:
            self.feed_scanner.run()
        except Exception as exc:
            self._log_feed(f"[ERROR] Feed scan crash: {exc}")
        finally:
            self.root.after(0, self._on_feed_finished)

    def _stop_feed_scan(self):
        if self.feed_scanner:
            self.feed_scanner.request_stop()
        self.feed_stop_btn.config(state=tk.DISABLED)

    def _on_feed_found(self, count: int):
        self.root.after(0, lambda: self.feed_found_label.config(text=f"Found: {count}"))

    def _on_feed_finished(self):
        self.feed_is_running = False
        self.feed_start_btn.config(state=tk.NORMAL)
        self.feed_stop_btn.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    LinkedInApp(root)
    root.mainloop()
