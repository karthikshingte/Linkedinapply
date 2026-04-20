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
    # Easy Apply form auto-fill answers
    "form_answers": {
        "phone":              "",
        "years_experience":   "2",
        "authorized_to_work": "Yes",
        "require_sponsorship":"No",
        "willing_to_relocate":"No",
        "work_preference":    "Remote",
        "education_level":    "Bachelor's Degree",
        "exp_level_label":    "Entry level",
        "work_type":          "Full-time",
        "expected_salary":    "",
        "expected_rate":      "",
        "city":               "",
        "state":              "",
        "zip_code":           "",
        "country":            "United States",
        "linkedin_url":       "",
        "portfolio_url":      "",
        "default_yes_no":     "Yes",
        "cover_letter":       "",
    },
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
        self._collect_only_mode = False   # True when "Collect Only" was pressed

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
        self.config["form_answers"] = {
            "phone":              self.fa_phone.get().strip(),
            "years_experience":   self.fa_years.get().strip(),
            "authorized_to_work": self.fa_work_auth.get(),
            "require_sponsorship":self.fa_sponsorship.get(),
            "willing_to_relocate":self.fa_relocate.get(),
            "work_preference":    self.fa_work_pref.get(),
            "education_level":    self.fa_education.get(),
            "exp_level_label":    self.fa_exp_level.get(),
            "work_type":          self.fa_work_type.get(),
            "expected_salary":    self.fa_salary.get().strip(),
            "expected_rate":      self.fa_rate.get().strip(),
            "city":               self.fa_city.get().strip(),
            "state":              self.fa_state.get().strip(),
            "zip_code":           self.fa_zip.get().strip(),
            "country":            self.fa_country.get().strip(),
            "linkedin_url":       self.fa_linkedin.get().strip(),
            "portfolio_url":      self.fa_portfolio.get().strip(),
            "default_yes_no":     self.fa_default_yn.get(),
            "cover_letter":       self.fa_cover.get("1.0", tk.END).strip(),
        }

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
        # Modern theme
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"),
                         foreground="#1A237E")
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#666")
        style.configure("StatNum.TLabel", font=("Segoe UI", 22, "bold"))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # ── Header ──
        hdr = ttk.Frame(self.root, padding=(14, 10, 14, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="LinkedIn Easy Apply Bot",
                  style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(hdr,
                  text="  Collect → Apply  |  Form Auto-Fill  |  Feed Scanner",
                  style="Sub.TLabel").pack(side=tk.LEFT, padx=(10, 0))

        # ── Notebook ──
        nb = ttk.Notebook(self.root, padding=4)
        nb.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 0))

        self._tab_dashboard(nb)
        self._tab_settings(nb)
        self._tab_roles(nb)
        self._tab_ignore(nb)
        self._tab_filters(nb)
        self._tab_form_answers(nb)
        self._tab_feed_scanner(nb)
        self._tab_logs(nb)

        # ── Status bar ──
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var,
                  relief=tk.SUNKEN, anchor=tk.W, padding=(8, 3)).grid(
            row=2, column=0, sticky="ew", padx=10, pady=(4, 8))

    # ── dashboard tab ─────────────────────────────────────────────

    def _tab_dashboard(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="  Dashboard  ")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(3, weight=1)

        # ── Action buttons ──
        btn_frame = ttk.LabelFrame(f, text="Controls", padding=(10, 6))
        btn_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.start_btn = ttk.Button(btn_frame, text="▶  Collect + Apply",
                                    command=lambda: self._start(collect_only=False))
        self.start_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.collect_btn = ttk.Button(btn_frame, text="📋  Collect Only",
                                      command=lambda: self._start(collect_only=True))
        self.collect_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(btn_frame, text="⏹  Stop",
                                   command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Button(btn_frame, text="Apply Changes Now",
                   command=self._apply_changes).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Save Config",
                   command=self._save_config).pack(side=tk.LEFT, padx=(0, 4))
        self.apps_label = ttk.Label(btn_frame, text="Collected: 0 | Applied: 0",
                                    font=("Segoe UI", 9, "bold"))
        self.apps_label.pack(side=tk.RIGHT, padx=(10, 0))

        # ── Stats row ──
        stats = ttk.LabelFrame(f, text="Live Statistics", padding=10)
        stats.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        stats.columnconfigure((0, 1, 2, 3), weight=1)

        self._stat_collected = tk.StringVar(value="0")
        self._stat_applied   = tk.StringVar(value="0")
        self._stat_failed    = tk.StringVar(value="0")
        self._stat_skipped   = tk.StringVar(value="0")

        for col, (lbl, var, clr) in enumerate([
            ("Collected", self._stat_collected, "#1A237E"),
            ("Applied",   self._stat_applied,   "#2E7D32"),
            ("Failed",    self._stat_failed,     "#C62828"),
            ("Skipped",   self._stat_skipped,    "#E65100"),
        ]):
            box = ttk.Frame(stats)
            box.grid(row=0, column=col, padx=8, sticky="ew")
            ttk.Label(box, text=lbl, foreground="#666",
                      font=("Segoe UI", 9)).pack()
            tk.Label(box, textvariable=var, font=("Segoe UI", 22, "bold"),
                     fg=clr).pack()

        # ── Progress bar ──
        prog = ttk.Frame(f)
        prog.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        prog.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew")
        self.phase_label = ttk.Label(prog, text="", foreground="#555")
        self.phase_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Mini activity log ──
        log_frame = ttk.LabelFrame(f, text="Activity Log", padding=4)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.dash_log = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("Consolas", 9), height=8)
        self.dash_log.grid(row=0, column=0, sticky="nsew")
        for tag, fg in [("INFO","#1565C0"),("SUCCESS","#2E7D32"),("WARN","#E65100"),
                        ("ERROR","#C62828"),("COLLECT","#6A1B9A"),("SKIP","#757575"),
                        ("DONE","#2E7D32"),("DEBUG","#999")]:
            self.dash_log.tag_config(tag, foreground=fg)

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

    # ── form answers tab ──────────────────────────────────────────

    def _tab_form_answers(self, nb):
        outer = ttk.Frame(nb, padding=0)
        nb.add(outer, text="  Form Answers  ")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        frame = ttk.Frame(canvas, padding=12)
        frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(frame_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)

        frame.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Mouse-wheel scroll
        def _scroll(e):
            canvas.yview_scroll(-1 * (e.delta // 120), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        frame.columnconfigure(1, weight=1)
        fa = self.config.get("form_answers", DEFAULT_CONFIG["form_answers"])
        r = 0

        YES_NO      = ["Yes", "No"]
        WORK_PREF   = ["Remote", "Hybrid", "On-site", "Any"]
        EDU_LEVELS  = ["High School", "Associate's Degree", "Bachelor's Degree",
                       "Master's Degree", "PhD", "Other"]
        EXP_LEVELS  = ["Internship", "Entry level", "Associate", "Mid-Senior level", "Director"]
        WORK_TYPES  = ["Full-time", "Part-time", "Contract", "Temporary", "Internship"]

        def section(lbl):
            nonlocal r
            ttk.Separator(frame).grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 4))
            r += 1
            ttk.Label(frame, text=lbl, font=("Helvetica", 10, "bold")).grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(0, 4))
            r += 1

        def entry_row(lbl, var, show=""):
            nonlocal r
            ttk.Label(frame, text=lbl).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            ttk.Entry(frame, textvariable=var, show=show, width=38).grid(
                row=r, column=1, sticky="ew")
            r += 1

        def combo_row(lbl, var, values):
            nonlocal r
            ttk.Label(frame, text=lbl).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            ttk.Combobox(frame, textvariable=var, values=values,
                         state="readonly", width=25).grid(row=r, column=1, sticky="w")
            r += 1

        ttk.Label(frame,
                  text="These answers are used to auto-fill prerequisite questions in Easy Apply forms.\n"
                       "Leave a field blank to skip filling it.",
                  foreground="#444", wraplength=500, justify=tk.LEFT).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 4))
        r += 1

        # ── Contact ──────────────────────────────────────
        section("Contact Info")
        self.fa_phone = tk.StringVar(value=fa.get("phone", ""))
        entry_row("Phone Number:", self.fa_phone)

        self.fa_city  = tk.StringVar(value=fa.get("city", ""))
        entry_row("City:", self.fa_city)

        self.fa_state = tk.StringVar(value=fa.get("state", ""))
        entry_row("State / Province:", self.fa_state)

        self.fa_zip   = tk.StringVar(value=fa.get("zip_code", ""))
        entry_row("Zip / Postal Code:", self.fa_zip)

        self.fa_country = tk.StringVar(value=fa.get("country", "United States"))
        entry_row("Country:", self.fa_country)

        # ── Experience ────────────────────────────────────
        section("Experience & Work Authorization")

        self.fa_years = tk.StringVar(value=fa.get("years_experience", "2"))
        entry_row("Years of Experience  (used for any 'years of exp' question):", self.fa_years)

        self.fa_education = tk.StringVar(value=fa.get("education_level", "Bachelor's Degree"))
        combo_row("Highest Education Level:", self.fa_education, EDU_LEVELS)

        self.fa_exp_level = tk.StringVar(value=fa.get("exp_level_label", "Entry level"))
        combo_row("Experience Level (dropdowns):", self.fa_exp_level, EXP_LEVELS)

        self.fa_work_auth = tk.StringVar(value=fa.get("authorized_to_work", "Yes"))
        combo_row("Authorized to work in the US?", self.fa_work_auth, YES_NO)

        self.fa_sponsorship = tk.StringVar(value=fa.get("require_sponsorship", "No"))
        combo_row("Require visa sponsorship?", self.fa_sponsorship, YES_NO)

        self.fa_relocate = tk.StringVar(value=fa.get("willing_to_relocate", "No"))
        combo_row("Willing to relocate?", self.fa_relocate, YES_NO)

        self.fa_work_pref = tk.StringVar(value=fa.get("work_preference", "Remote"))
        combo_row("Work preference (Remote/Hybrid/On-site)?", self.fa_work_pref, WORK_PREF)

        self.fa_work_type = tk.StringVar(value=fa.get("work_type", "Full-time"))
        combo_row("Employment type (dropdowns):", self.fa_work_type, WORK_TYPES)

        # ── Compensation ─────────────────────────────────
        section("Compensation")

        self.fa_salary = tk.StringVar(value=fa.get("expected_salary", ""))
        entry_row("Expected Annual Salary ($ numbers only):", self.fa_salary)

        self.fa_rate = tk.StringVar(value=fa.get("expected_rate", ""))
        entry_row("Expected Hourly Rate ($ numbers only):", self.fa_rate)

        # ── Links ─────────────────────────────────────────
        section("Profile Links")

        self.fa_linkedin = tk.StringVar(value=fa.get("linkedin_url", ""))
        entry_row("LinkedIn Profile URL:", self.fa_linkedin)

        self.fa_portfolio = tk.StringVar(value=fa.get("portfolio_url", ""))
        entry_row("GitHub / Portfolio URL:", self.fa_portfolio)

        # ── Defaults ─────────────────────────────────────
        section("Fallback Behaviour")

        self.fa_default_yn = tk.StringVar(value=fa.get("default_yes_no", "Yes"))
        combo_row("Default answer for unknown Yes/No questions:", self.fa_default_yn, YES_NO)

        # ── Cover Letter ──────────────────────────────────
        section("Cover Letter (optional)")
        ttk.Label(frame, text="Pasted into any cover letter / additional info text box.\n"
                              "Leave blank to skip.", foreground="#555").grid(
            row=r, column=0, columnspan=2, sticky="w")
        r += 1
        self.fa_cover = tk.Text(frame, height=6, wrap=tk.WORD, font=("Consolas", 9))
        self.fa_cover.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        cover_text = fa.get("cover_letter", "")
        if cover_text:
            self.fa_cover.insert("1.0", cover_text)
        r += 1

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
        for t in ("SUCCESS","FOUND","WARN","ERROR","SKIP","DONE","DEBUG","COLLECT","INFO"):
            if f"[{t}]" in msg:
                tag = t
                break
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, full, tag)
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)

        # Mirror job-bot messages to the Dashboard mini-log
        if kind == "job":
            self.dash_log.config(state=tk.NORMAL)
            self.dash_log.insert(tk.END, full, tag)
            self.dash_log.see(tk.END)
            self.dash_log.config(state=tk.DISABLED)

    def _clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_feed_log(self):
        self.feed_log_text.config(state=tk.NORMAL)
        self.feed_log_text.delete("1.0", tk.END)
        self.feed_log_text.config(state=tk.DISABLED)

    # ──────────────────────────────────────────── job bot

    def _start(self, collect_only: bool = False):
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

        self._collect_only_mode = collect_only
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.collect_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        # Reset dashboard stats for a fresh run
        self._stat_collected.set("0")
        self._stat_applied.set("0")
        self._stat_failed.set("0")
        self._stat_skipped.set("0")
        self.progress.stop()
        self.progress.config(mode="indeterminate", value=0)
        self.phase_label.config(text="Starting…")

        # Clear dashboard mini-log
        self.dash_log.config(state=tk.NORMAL)
        self.dash_log.delete("1.0", tk.END)
        self.dash_log.config(state=tk.DISABLED)

        if collect_only:
            self.status_var.set("Phase 1 — Collecting jobs…")
            self.apps_label.config(text="Collected: 0")
        else:
            self.status_var.set("Phase 1 — Collecting jobs…")
            self.apps_label.config(text="Collected: 0 | Applied: 0")

        # Bot receives self.config BY REFERENCE — Apply Changes Now just updates
        # this same dict, and the bot reads it dynamically on every action.
        self.bot = LinkedInBot(self.config, self._log_job,
                               self._on_collect_update, self._on_apply_update)
        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()

    def _run_bot(self):
        try:
            self.bot.run(collect_only=self._collect_only_mode)
        except Exception as exc:
            self._log_job(f"[ERROR] Unexpected crash: {exc}")
        finally:
            self.root.after(0, self._on_bot_finished)

    def _stop(self):
        if self.bot:
            self.bot.request_stop()
        self.status_var.set("Stopping…")
        self.stop_btn.config(state=tk.DISABLED)

    # ── count callbacks (called from bot thread → schedule on main thread) ──

    def _on_collect_update(self, collected: int):
        """Called by the bot each time a job is added to the collected list."""
        def _update():
            if self._collect_only_mode:
                self.apps_label.config(text=f"Collected: {collected}")
            else:
                cur = self.apps_label.cget("text")
                applied_part = cur.split("|")[1].strip() if "|" in cur else "Applied: 0"
                self.apps_label.config(text=f"Collected: {collected} | {applied_part}")
            self.status_var.set(f"Phase 1 — Collecting jobs… ({collected} so far)")
            # Dashboard stats
            self._stat_collected.set(str(collected))
            self.phase_label.config(text="Phase 1 — Collecting job listings…")
            self.progress.config(mode="indeterminate")
            self.progress.start(20)
        self.root.after(0, _update)

    def _on_apply_update(self, applied: int, total: int):
        """Called by the bot each time an application succeeds/fails in Phase 2."""
        def _update():
            cur = self.apps_label.cget("text")
            collected_part = cur.split("|")[0].strip() if "|" in cur else "Collected: ?"
            self.apps_label.config(text=f"{collected_part} | Applied: {applied}/{total}")
            self.status_var.set(f"Phase 2 — Applying… ({applied}/{total})")
            # Dashboard stats & progress
            self._stat_applied.set(str(applied))
            if self.bot:
                self._stat_failed.set(str(len(self.bot.failed_jobs)))
                self._stat_skipped.set(str(len(self.bot.ignored_jobs)))
            self.progress.stop()
            self.progress.config(mode="determinate", maximum=total, value=applied)
            pct = int(applied / total * 100) if total else 0
            self.phase_label.config(text=f"Phase 2 — Applying… {applied}/{total} ({pct}%)")
        self.root.after(0, _update)

    def _on_bot_finished(self):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.collect_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        # Stop the indeterminate progress animation if still running
        self.progress.stop()

        if self.bot:
            self._stat_applied.set(str(self.bot.applied_count))
            self._stat_failed.set(str(len(self.bot.failed_jobs)))
            self._stat_skipped.set(str(len(self.bot.ignored_jobs)))
            total = self.bot._total_to_apply or 1
            self.progress.config(mode="determinate", maximum=total,
                                 value=self.bot.applied_count)

        if self._collect_only_mode:
            self.status_var.set("Collect phase complete — check linkedin_jobs.xlsx")
            self.phase_label.config(text="✔ Collection finished")
        else:
            applied = self.bot.applied_count if self.bot else 0
            failed  = len(self.bot.failed_jobs) if self.bot else 0
            skipped = len(self.bot.ignored_jobs) if self.bot else 0
            self.status_var.set(
                f"Finished — {applied} applied, {failed} failed, {skipped} skipped")
            self.phase_label.config(
                text=f"✔ Done — {applied} applied, {failed} failed, {skipped} skipped")

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
