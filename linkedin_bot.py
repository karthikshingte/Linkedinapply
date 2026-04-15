"""
LinkedIn Easy Apply Bot — Selenium automation engine.
No LinkedIn API required; drives a real Chrome browser session.
"""

import time
import random
import os
from datetime import datetime
from typing import Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    from webdriver_manager.chrome import ChromeDriverManager
    USE_WDM = True
except ImportError:
    USE_WDM = False

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_OK = True
except ImportError:
    EXCEL_OK = False

# ──────────────────────────────────────────────────────────────────────────────
# URL helpers
# ──────────────────────────────────────────────────────────────────────────────

DATE_FILTER_MAP = {
    "Past 24 hours": "r86400",
    "Past Week":     "r604800",
    "Past Month":    "r2592000",
    "Any Time":      "",
}

EXPERIENCE_FILTER_MAP = {
    "Internship":       "1",
    "Entry level":      "2",
    "Associate":        "3",
    "Mid-Senior level": "4",
    "Director":         "5",
    "Any":              "",
}


def _build_search_url(role: str, location: str, date_posted: str, experience: str) -> str:
    params = [
        f"keywords={role.replace(' ', '%20')}",
        f"location={location.replace(' ', '%20')}",
        "f_LF=f_AL",          # Easy Apply filter
        "sortBy=DD",          # Most recent first
    ]
    date_code = DATE_FILTER_MAP.get(date_posted, "")
    if date_code:
        params.append(f"f_TPR={date_code}")
    exp_code = EXPERIENCE_FILTER_MAP.get(experience, "")
    if exp_code:
        params.append(f"f_E={exp_code}")
    return "https://www.linkedin.com/jobs/search/?" + "&".join(params)


# ──────────────────────────────────────────────────────────────────────────────
# Excel export
# ──────────────────────────────────────────────────────────────────────────────

HEADER_FILL  = PatternFill("solid", fgColor="1F4E79") if EXCEL_OK else None
SUCCESS_FILL = PatternFill("solid", fgColor="C6EFCE") if EXCEL_OK else None
IGNORE_FILL  = PatternFill("solid", fgColor="FFEB9C") if EXCEL_OK else None
FAIL_FILL    = PatternFill("solid", fgColor="FFC7CE") if EXCEL_OK else None


def _make_sheet(wb, title: str, headers: list[str], fill):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for col, _ in enumerate(headers, 1):
        cell = ws.cell(1, col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")
    return ws


def _auto_width(ws):
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 80)


def export_to_excel(applied: list, ignored: list, failed: list, log: Callable) -> str:
    if not EXCEL_OK:
        log("[WARN] openpyxl not installed — skipping Excel export. Run: pip install openpyxl")
        return ""

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"linkedin_jobs_{ts}.xlsx"

    wb = openpyxl.Workbook()
    wb.remove(wb.active)   # remove default sheet

    # Applied sheet
    ws_a = _make_sheet(
        wb, "Applied",
        ["#", "Job Title", "Company", "URL", "Applied At", "Role Searched"],
        PatternFill("solid", fgColor="1F4E79"),
    )
    for i, j in enumerate(applied, 1):
        ws_a.append([i, j["title"], j["company"], j["url"], j["timestamp"], j["role"]])
        for col in range(1, 7):
            ws_a.cell(i + 1, col).fill = SUCCESS_FILL
    _auto_width(ws_a)

    # Ignored sheet
    ws_i = _make_sheet(
        wb, "Ignored",
        ["#", "Job Title", "Company", "URL", "Ignored At", "Matched Word"],
        PatternFill("solid", fgColor="7F6000"),
    )
    for i, j in enumerate(ignored, 1):
        ws_i.append([i, j["title"], j["company"], j["url"], j["timestamp"], j["reason"]])
        for col in range(1, 7):
            ws_i.cell(i + 1, col).fill = IGNORE_FILL
    _auto_width(ws_i)

    # Failed sheet
    ws_f = _make_sheet(
        wb, "Failed",
        ["#", "Job Title", "Company", "URL", "Failed At", "Reason"],
        PatternFill("solid", fgColor="9C0006"),
    )
    for i, j in enumerate(failed, 1):
        ws_f.append([i, j["title"], j["company"], j["url"], j["timestamp"], j["reason"]])
        for col in range(1, 7):
            ws_f.cell(i + 1, col).fill = FAIL_FILL
    _auto_width(ws_f)

    wb.save(filename)
    log(f"[INFO] Excel report saved: {os.path.abspath(filename)}")
    return filename


# ──────────────────────────────────────────────────────────────────────────────
# Bot
# ──────────────────────────────────────────────────────────────────────────────

# All selectors to try for job card list items — LinkedIn changes these often
CARD_SELECTORS = [
    "li.jobs-search-results__list-item",
    "li[data-occludable-job-id]",
    "div.job-card-container",
    "div[data-job-id]",
    "li.scaffold-layout__list-item",
    "div.jobs-search-results__list > li",
    "ul > li.ember-view",
]

# Selectors to detect when the page has loaded jobs
PAGE_READY_SELECTORS = [
    "div.jobs-search-results-list",
    "ul.jobs-search-results__list",
    "div.scaffold-layout__list",
    "div[class*='jobs-search-results']",
    "div.jobs-search-results__list-item",
]


class LinkedInBot:

    def __init__(
        self,
        config: dict,
        log: Callable[[str], None],
        count_callback: Callable[[int], None] | None = None,
    ):
        self.config = config
        self.log = log
        self.count_callback = count_callback
        self.driver: webdriver.Chrome | None = None
        self.wait: WebDriverWait | None = None
        self._stop_flag = False
        self.applied_count = 0

        # Job tracking
        self.applied_jobs: list[dict] = []
        self.ignored_jobs: list[dict] = []
        self.failed_jobs:  list[dict] = []

    # ─────────────────────────────────────────────────────────────── control

    def request_stop(self):
        self._stop_flag = True

    def _should_stop(self) -> bool:
        return self._stop_flag

    # ─────────────────────────────────────────────────────────────── delays

    def _delay(self, lo: float | None = None, hi: float | None = None):
        lo = lo if lo is not None else float(self.config.get("min_delay", 3))
        hi = hi if hi is not None else float(self.config.get("max_delay", 7))
        time.sleep(random.uniform(lo, hi))

    def _short(self):
        time.sleep(random.uniform(0.8, 1.6))

    # ─────────────────────────────────────────────────────────────── browser

    def _setup_driver(self):
        opts = Options()
        if self.config.get("headless", False):
            opts.add_argument("--headless=new")

        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--start-maximized")
        opts.add_argument("--window-size=1440,900")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        if USE_WDM:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
        else:
            self.driver = webdriver.Chrome(options=opts)

        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
        )
        self.wait = WebDriverWait(self.driver, 15)
        self.log("[INFO] Browser launched.")

    # ─────────────────────────────────────────────────────────────── login

    def _login(self) -> bool:
        self.log("[INFO] Opening LinkedIn login page...")
        self.driver.get("https://www.linkedin.com/login")
        self._delay(2, 4)

        try:
            email_field = self.wait.until(EC.presence_of_element_located((By.ID, "username")))
            self._type_human(email_field, self.config["email"])
            pw = self.driver.find_element(By.ID, "password")
            self._type_human(pw, self.config["password"])
            self._short()
            pw.send_keys(Keys.RETURN)
            self._delay(4, 6)
        except TimeoutException:
            self.log("[ERROR] Login page did not load.")
            return False

        url = self.driver.current_url
        if any(k in url for k in ("feed", "mynetwork", "jobs", "home")):
            self.log("[INFO] Login successful.")
            return True

        if any(k in url for k in ("checkpoint", "challenge", "security", "verification")):
            self.log("[WARN] Security check required — complete it in the browser (90 s).")
            deadline = time.time() + 90
            while time.time() < deadline:
                time.sleep(3)
                if any(k in self.driver.current_url for k in ("feed", "mynetwork", "jobs")):
                    self.log("[INFO] Security check passed.")
                    return True
            self.log("[ERROR] Security check timed out.")
            return False

        self.log("[ERROR] Login failed — unexpected URL: " + url)
        return False

    def _type_human(self, element, text: str):
        element.clear()
        for ch in text:
            element.send_keys(ch)
            time.sleep(random.uniform(0.04, 0.13))

    # ─────────────────────────────────────────────────────────────── search

    def _search(self, role: str):
        url = _build_search_url(
            role,
            self.config.get("location", "United States"),
            self.config.get("date_posted", "Any Time"),
            self.config.get("experience_level", "Any"),
        )
        self.log(f"[INFO] Searching: {role}  →  {url}")
        self.driver.get(url)
        self._delay(4, 6)

    # ─────────────────────────────────────────────────────────────── cards

    def _wait_for_page_ready(self):
        """Wait until any known results container appears."""
        combined = ", ".join(PAGE_READY_SELECTORS)
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, combined))
            )
        except TimeoutException:
            self.log("[WARN] Page ready timeout — trying anyway.")

    def _get_job_cards(self) -> list:
        self._wait_for_page_ready()
        time.sleep(1.5)   # let JS render the list

        for sel in CARD_SELECTORS:
            cards = self.driver.find_elements(By.CSS_SELECTOR, sel)
            visible = [c for c in cards if c.is_displayed()]
            if len(visible) > 1:
                self.log(f"[DEBUG] {len(visible)} cards found ({sel})")
                return visible

        # Last resort: dump page title for debugging
        self.log(f"[DEBUG] No cards found. Page title: '{self.driver.title}'")
        self.log(f"[DEBUG] Current URL: {self.driver.current_url}")
        return []

    def _get_title(self, card) -> str:
        for sel in [
            "a.job-card-list__title--link",
            "a.job-card-list__title",
            "a.job-card-container__link",
            "strong",
            "a[href*='/jobs/view/']",
        ]:
            try:
                t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t:
                    return t
            except NoSuchElementException:
                continue
        return "Unknown Title"

    def _get_company(self, card) -> str:
        for sel in [
            ".job-card-container__company-name",
            ".job-card-container__primary-description",
            "a.job-card-container__company-name",
            ".artdeco-entity-lockup__subtitle span",
            ".job-card-list__company-name",
            "span.job-card-container__company-name",
        ]:
            try:
                t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t:
                    return t
            except NoSuchElementException:
                continue
        return "Unknown Company"

    def _get_url(self, card) -> str:
        for sel in [
            "a.job-card-list__title--link",
            "a.job-card-list__title",
            "a.job-card-container__link",
            "a[href*='/jobs/view/']",
        ]:
            try:
                href = card.find_element(By.CSS_SELECTOR, sel).get_attribute("href")
                if href:
                    return href.split("?")[0]
            except NoSuchElementException:
                continue
        return self.driver.current_url

    def _should_skip(self, title: str) -> tuple[bool, str]:
        lower = title.lower()
        for word in self.config.get("ignore_words", []):
            if word.strip().lower() in lower:
                return True, word
        return False, ""

    def _click_card(self, card) -> bool:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
            self._short()
            card.click()
            self._delay(2, 3)
            return True
        except Exception as e:
            self.log(f"[WARN] Could not click card: {e}")
            return False

    # ─────────────────────────────────────────────────────────────── apply

    def _click_easy_apply(self) -> bool:
        selectors = [
            "button.jobs-apply-button",
            "button[aria-label*='Easy Apply']",
            "button[aria-label*='easy apply']",
            ".jobs-s-apply button",
            ".jobs-apply-button",
        ]
        for sel in selectors:
            try:
                btn = WebDriverWait(self.driver, 6).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                if "easy apply" in (btn.text or btn.get_attribute("aria-label") or "").lower():
                    btn.click()
                    self._delay(1.5, 3)
                    return True
            except Exception:
                continue
        return False

    def _find_btn(self, *fragments: str):
        for btn in self.driver.find_elements(By.TAG_NAME, "button"):
            if not btn.is_displayed():
                continue
            label = (btn.get_attribute("aria-label") or "").lower()
            text  = (btn.text or "").lower()
            for f in fragments:
                if f.lower() in label or f.lower() in text:
                    return btn
        return None

    def _click_next_or_review(self) -> bool:
        btn = self._find_btn(
            "continue to next step", "next step", "next",
            "review your application", "review"
        )
        if btn and btn.is_enabled():
            try:
                btn.click()
                self._delay(1.5, 2.5)
                return True
            except Exception:
                pass
        return False

    def _click_submit(self) -> bool:
        btn = self._find_btn("submit application", "submit")
        if btn and btn.is_enabled():
            try:
                btn.click()
                self._delay(2, 3.5)
                return True
            except Exception:
                pass
        return False

    def _close_modal(self):
        for sel in [
            "button[aria-label='Dismiss']",
            "button[aria-label='Close']",
            ".artdeco-modal__dismiss",
            "button[data-test-modal-close-btn]",
        ]:
            try:
                btn = WebDriverWait(self.driver, 4).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                btn.click()
                self._short()
                return
            except Exception:
                continue

    def _discard(self):
        btn = self._find_btn("discard", "discard application")
        if btn:
            try:
                btn.click()
                self._short()
            except Exception:
                pass

    def _handle_form(self) -> tuple[bool, str]:
        """
        Navigate multi-step Easy Apply form.
        Returns (success, failure_reason).
        """
        for step in range(15):
            if self._should_stop():
                self._close_modal()
                self._discard()
                return False, "stopped by user"

            self._delay(1, 2)

            if self._click_submit():
                self._delay(1, 2)
                self._close_modal()
                return True, ""

            if self._click_next_or_review():
                continue

            self._close_modal()
            self._discard()
            return False, "no navigation button found at step " + str(step + 1)

        self._close_modal()
        self._discard()
        return False, "exceeded max form steps"

    # ─────────────────────────────────────────────────────────────── pagination

    def _next_page(self, current: int) -> bool:
        try:
            btn = self.driver.find_element(
                By.CSS_SELECTOR, f'button[aria-label="Page {current + 1}"]'
            )
            btn.click()
            self._delay(3, 5)
            return True
        except NoSuchElementException:
            return False

    def _scroll_list(self):
        for sel in [
            "div.jobs-search-results-list",
            "ul.jobs-search-results__list",
            "div.scaffold-layout__list",
        ]:
            try:
                panel = self.driver.find_element(By.CSS_SELECTOR, sel)
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", panel
                )
                self._delay(1.5, 2.5)
                return
            except Exception:
                continue
        # Fallback: scroll the window
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        self._delay(1.5, 2)

    # ─────────────────────────────────────────────────────────────── main

    def run(self):
        try:
            self._setup_driver()

            if not self._login():
                return

            max_apps = int(self.config.get("max_applications", 50))
            roles    = self.config.get("job_roles", [])

            for role in roles:
                if self._should_stop() or self.applied_count >= max_apps:
                    break

                self._search(role)
                page = 1

                while not self._should_stop() and self.applied_count < max_apps:
                    self._scroll_list()
                    cards = self._get_job_cards()

                    if not cards:
                        self.log(f"[INFO] No job cards found for '{role}' on page {page}.")
                        break

                    seen: set[str] = set()

                    for idx in range(len(cards)):
                        if self._should_stop() or self.applied_count >= max_apps:
                            break

                        try:
                            cards = self._get_job_cards()
                            if idx >= len(cards):
                                break
                            card = cards[idx]
                        except Exception:
                            break

                        try:
                            title   = self._get_title(card)
                            company = self._get_company(card)
                            url     = self._get_url(card)
                            now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            if title in seen:
                                continue
                            seen.add(title)

                            skip, matched_word = self._should_skip(title)
                            if skip:
                                self.log(f"[SKIP] '{title}' @ {company}  (matched: '{matched_word}')")
                                self.ignored_jobs.append({
                                    "title": title, "company": company,
                                    "url": url, "timestamp": now,
                                    "reason": matched_word, "role": role,
                                })
                                continue

                            self.log(f"[INFO] Trying: {title} @ {company}")

                            if not self._click_card(card):
                                reason = "could not click card"
                                self.log(f"[WARN] {reason}: {title}")
                                self.failed_jobs.append({
                                    "title": title, "company": company,
                                    "url": url, "timestamp": now,
                                    "reason": reason, "role": role,
                                })
                                continue

                            # URL is more accurate after clicking
                            url = self.driver.current_url.split("?")[0]

                            if not self._click_easy_apply():
                                reason = "no Easy Apply button"
                                self.log(f"[SKIP] {reason}: {title}")
                                self.failed_jobs.append({
                                    "title": title, "company": company,
                                    "url": url, "timestamp": now,
                                    "reason": reason, "role": role,
                                })
                                continue

                            success, fail_reason = self._handle_form()

                            if success:
                                self.applied_count += 1
                                self.applied_jobs.append({
                                    "title": title, "company": company,
                                    "url": url, "timestamp": now,
                                    "reason": "", "role": role,
                                })
                                if self.count_callback:
                                    self.count_callback(self.applied_count)
                                self.log(
                                    f"[SUCCESS] Applied ({self.applied_count}/{max_apps}): "
                                    f"{title} @ {company}"
                                )
                            else:
                                self.log(f"[WARN] Failed ({fail_reason}): {title}")
                                self.failed_jobs.append({
                                    "title": title, "company": company,
                                    "url": url, "timestamp": now,
                                    "reason": fail_reason, "role": role,
                                })

                            self._delay()

                        except StaleElementReferenceException:
                            self.log("[WARN] DOM changed mid-loop; refreshing card list.")
                            break
                        except Exception as exc:
                            self.log(f"[ERROR] {exc}")
                            try:
                                self._close_modal()
                                self._discard()
                            except Exception:
                                pass

                    if not self._next_page(page):
                        break
                    page += 1

            self.log(
                f"\n[DONE] Applied: {len(self.applied_jobs)}  |  "
                f"Ignored: {len(self.ignored_jobs)}  |  "
                f"Failed: {len(self.failed_jobs)}"
            )

            # Export results to Excel
            export_to_excel(self.applied_jobs, self.ignored_jobs, self.failed_jobs, self.log)

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.log("[INFO] Browser closed.")
