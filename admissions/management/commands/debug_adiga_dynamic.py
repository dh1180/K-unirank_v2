import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


ADIGA_RESULT_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"


class Command(BaseCommand):
    help = "ADIGA 동적 입시결과의 실제 DOM/네트워크 요청을 진단 파일로 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--code", default="0000194")
        parser.add_argument("--search-year", type=int, default=2027)
        parser.add_argument("--result-year", type=int, default=2026)
        parser.add_argument("--timeout", type=int, default=15)
        parser.add_argument(
            "--headed",
            action="store_true",
            help="Headless가 아닌 실제 Chrome 창으로 실행합니다.",
        )

    def handle(self, *args, **options):
        code = options["code"].strip()
        search_year = options["search_year"]
        result_year = options["result_year"]
        timeout = max(8, options["timeout"])
        headed = options["headed"]

        try:
            from selenium import webdriver
            from selenium.common.exceptions import WebDriverException
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise CommandError(
                "Selenium이 필요합니다. `pip install -r requirements.txt` 후 다시 실행해 주세요."
            ) from exc

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = Path.cwd() / "adiga_debug" / f"{code}_{search_year}_{stamp}"
        root.mkdir(parents=True, exist_ok=True)

        options_chrome = webdriver.ChromeOptions()
        if not headed:
            options_chrome.add_argument("--headless=new")
        options_chrome.add_argument("--disable-gpu")
        options_chrome.add_argument("--no-sandbox")
        options_chrome.add_argument("--disable-dev-shm-usage")
        options_chrome.add_argument("--window-size=1920,3000")
        options_chrome.add_argument("--lang=ko-KR")
        options_chrome.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        driver = None
        summary = {
            "code": code,
            "search_year": search_year,
            "result_year": result_year,
            "headed": headed,
            "tabs": {},
        }

        url = (
            f"{ADIGA_RESULT_URL}?menuId=PCUVTINF2000"
            f"&unvCd={code}&searchSyr={search_year}"
        )

        try:
            driver = webdriver.Chrome(options=options_chrome)
            driver.set_page_load_timeout(max(timeout, 25))
            driver.get(url)
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(1.5)

            self.write_text(root / "00_initial_source.html", driver.page_source)
            self.save_screenshot(driver, root / "00_initial.png")
            self.write_json(root / "00_scripts.json", self.collect_scripts(driver))

            for tab_code in ("20", "30", "40"):
                tab_dir = root / f"tab_{tab_code}"
                tab_dir.mkdir(parents=True, exist_ok=True)
                tab_summary = {"candidate_count": 0, "attempts": []}
                summary["tabs"][tab_code] = tab_summary

                tab_buttons = driver.find_elements(By.ID, f"tab_{tab_code}")
                if not tab_buttons:
                    tab_summary["error"] = "tab button not found"
                    continue

                driver.execute_script("arguments[0].click();", tab_buttons[0])
                time.sleep(1.0)

                self.flush_performance(driver)
                self.write_text(tab_dir / "01_before_source.html", driver.page_source)
                self.save_screenshot(driver, tab_dir / "01_before.png")

                candidates = self.mark_result_candidates(driver, result_year)
                tab_summary["candidate_count"] = len(candidates)
                self.write_json(tab_dir / "02_candidates.json", candidates)
                self.write_json(tab_dir / "02_tables_before.json", self.collect_tables(driver))

                if not candidates:
                    continue

                max_attempts = min(len(candidates), 8)

                for index in range(max_attempts):
                    attempt_dir = tab_dir / f"attempt_{index + 1:02d}"
                    attempt_dir.mkdir(parents=True, exist_ok=True)

                    candidate = candidates[index]
                    debug_id = candidate["debug_id"]
                    attempt_summary = {
                        "debug_id": debug_id,
                        "tag": candidate.get("tag"),
                        "text": candidate.get("text"),
                    }
                    tab_summary["attempts"].append(attempt_summary)

                    self.flush_performance(driver)

                    clicked = driver.execute_script(
                        r"""
                        const id = arguments[0];
                        const el = document.querySelector(
                            `[data-kunirank-debug-id="${id}"]`
                        );
                        if (!el) return false;

                        const target =
                            el.closest("button, a, [role='button']") ||
                            el.querySelector("button, a, [role='button']") ||
                            el;

                        target.scrollIntoView({block: "center"});
                        try { target.click(); } catch (_) {}

                        for (const type of ["mousedown", "mouseup", "click", "change"]) {
                            try {
                                target.dispatchEvent(
                                    new MouseEvent(type, {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window,
                                    })
                                );
                            } catch (_) {}
                        }
                        return true;
                        """,
                        debug_id,
                    )
                    attempt_summary["clicked"] = bool(clicked)
                    time.sleep(2.0)

                    self.write_text(attempt_dir / "source_after.html", driver.page_source)
                    self.save_screenshot(driver, attempt_dir / "after.png")
                    self.write_json(attempt_dir / "tables_after.json", self.collect_tables(driver))
                    self.write_json(
                        attempt_dir / "target_context_after.json",
                        self.collect_target_context(driver, debug_id),
                    )

                    network = self.collect_network(driver, attempt_dir)
                    attempt_summary["network_responses"] = len(network)
                    self.write_json(attempt_dir / "network_index.json", network)

                    interesting = self.collect_interesting_dom(driver, result_year)
                    self.write_json(attempt_dir / "interesting_dom.json", interesting)

            self.write_json(root / "summary.json", summary)

        except WebDriverException as exc:
            self.write_text(root / "ERROR.txt", repr(exc))
            raise CommandError(f"Chrome 진단 실행 실패: {exc}") from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

        archive = shutil.make_archive(str(root), "zip", root_dir=root)
        self.stdout.write(self.style.SUCCESS("ADIGA 진단 캡처 완료"))
        self.stdout.write(f"폴더: {root}")
        self.stdout.write(f"ZIP: {archive}")
        self.stdout.write("생성된 ZIP 파일을 그대로 ChatGPT에 첨부해 주세요.")

    def mark_result_candidates(self, driver, result_year):
        target = f"{result_year}학년도 전형 결과"
        return driver.execute_script(
            r"""
            const target = arguments[0];

            function textOf(el) {
                return (el.innerText || el.textContent || "")
                    .replace(/\s+/g, " ")
                    .trim();
            }

            function visible(el) {
                const style = getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function attrs(el) {
                const out = {};
                for (const attr of el.attributes || []) {
                    out[attr.name] = attr.value;
                }
                return out;
            }

            document.querySelectorAll("[data-kunirank-debug-id]").forEach(el => {
                el.removeAttribute("data-kunirank-debug-id");
            });

            const selectors = [
                "button", "a", "[role='button']", "dt", "dd", "li",
                "h1", "h2", "h3", "h4", "h5", "h6", "span", "strong",
                "p", "div", "[onclick]"
            ];

            const set = new Set();
            const found = [];

            for (const selector of selectors) {
                for (const el of document.querySelectorAll(selector)) {
                    if (set.has(el)) continue;
                    const text = textOf(el);
                    if (
                        visible(el) &&
                        text.includes(target) &&
                        text.length <= 240
                    ) {
                        set.add(el);
                        found.push(el);
                    }
                }
            }

            found.sort((a, b) => textOf(a).length - textOf(b).length);

            return found.map((el, index) => {
                const debugId = String(index + 1);
                el.setAttribute("data-kunirank-debug-id", debugId);

                const ancestors = [];
                let node = el.parentElement;
                let depth = 0;
                while (node && depth < 7) {
                    ancestors.push({
                        depth,
                        tag: node.tagName,
                        attrs: attrs(node),
                        text: textOf(node).slice(0, 1200),
                        outerHTML: node.outerHTML.slice(0, 8000),
                    });
                    node = node.parentElement;
                    depth += 1;
                }

                const siblings = [];
                let sibling = el.nextElementSibling;
                let count = 0;
                while (sibling && count < 4) {
                    siblings.push({
                        tag: sibling.tagName,
                        attrs: attrs(sibling),
                        text: textOf(sibling).slice(0, 1200),
                        outerHTML: sibling.outerHTML.slice(0, 8000),
                    });
                    sibling = sibling.nextElementSibling;
                    count += 1;
                }

                return {
                    debug_id: debugId,
                    tag: el.tagName,
                    text: textOf(el),
                    attrs: attrs(el),
                    outerHTML: el.outerHTML.slice(0, 12000),
                    parentHTML: el.parentElement
                        ? el.parentElement.outerHTML.slice(0, 12000)
                        : "",
                    ancestors,
                    next_siblings: siblings,
                };
            });
            """,
            target,
        ) or []

    def collect_target_context(self, driver, debug_id):
        return driver.execute_script(
            r"""
            const id = arguments[0];
            const el = document.querySelector(
                `[data-kunirank-debug-id="${id}"]`
            );
            if (!el) return {missing: true};

            function txt(node) {
                return (node && (node.innerText || node.textContent) || "")
                    .replace(/\s+/g, " ")
                    .trim();
            }

            function attrs(node) {
                const out = {};
                for (const attr of node.attributes || []) {
                    out[attr.name] = attr.value;
                }
                return out;
            }

            const levels = [];
            let node = el;
            for (let depth = 0; node && depth < 10; depth++) {
                levels.push({
                    depth,
                    tag: node.tagName,
                    attrs: attrs(node),
                    text: txt(node).slice(0, 3000),
                    html: node.outerHTML.slice(0, 20000),
                    tables: node.querySelectorAll
                        ? node.querySelectorAll("table").length
                        : 0,
                });
                node = node.parentElement;
            }
            return {levels};
            """,
            str(debug_id),
        )

    def collect_tables(self, driver):
        return driver.execute_script(
            r"""
            function txt(node) {
                return (node.innerText || node.textContent || "")
                    .replace(/\s+/g, " ")
                    .trim();
            }
            return [...document.querySelectorAll("table")].map((table, index) => {
                const style = getComputedStyle(table);
                const rect = table.getBoundingClientRect();
                return {
                    index,
                    visible: !(
                        style.display === "none" ||
                        style.visibility === "hidden" ||
                        rect.width === 0 ||
                        rect.height === 0
                    ),
                    text: txt(table).slice(0, 12000),
                    html: table.outerHTML.slice(0, 30000),
                };
            });
            """
        ) or []

    def collect_interesting_dom(self, driver, result_year):
        tokens = [
            f"{result_year}학년도 전형 결과",
            "모집인원",
            "경쟁률",
            "최종등록자",
            "70%",
        ]
        return driver.execute_script(
            r"""
            const tokens = arguments[0];
            function txt(node) {
                return (node.innerText || node.textContent || "")
                    .replace(/\s+/g, " ")
                    .trim();
            }
            const out = [];
            for (const el of document.querySelectorAll(
                "button, a, div, section, article, li, dt, dd, table, iframe"
            )) {
                const text = txt(el);
                if (!text || text.length > 20000) continue;
                if (!tokens.some(token => text.includes(token))) continue;
                out.push({
                    tag: el.tagName,
                    id: el.id || "",
                    className: typeof el.className === "string" ? el.className : "",
                    text: text.slice(0, 5000),
                    html: el.outerHTML.slice(0, 20000),
                });
                if (out.length >= 300) break;
            }
            return out;
            """,
            tokens,
        ) or []

    def collect_scripts(self, driver):
        return driver.execute_script(
            r"""
            return [...document.scripts].map((script, index) => ({
                index,
                src: script.src || "",
                text: script.src ? "" : (script.textContent || "").slice(0, 30000),
            }));
            """
        ) or []

    def flush_performance(self, driver):
        try:
            driver.get_log("performance")
        except Exception:
            pass

    def collect_network(self, driver, attempt_dir):
        try:
            logs = driver.get_log("performance")
        except Exception:
            return []

        items = []
        seen = set()
        body_dir = attempt_dir / "network_bodies"
        body_dir.mkdir(exist_ok=True)

        for raw in logs:
            try:
                message = json.loads(raw["message"])["message"]
            except Exception:
                continue

            if message.get("method") != "Network.responseReceived":
                continue

            params = message.get("params") or {}
            response = params.get("response") or {}
            url = response.get("url", "")
            request_id = params.get("requestId")
            if not request_id or not url or request_id in seen:
                continue
            seen.add(request_id)

            item = {
                "request_id": request_id,
                "url": url,
                "status": response.get("status"),
                "mime_type": response.get("mimeType", ""),
                "resource_type": params.get("type", ""),
            }

            if "adiga.kr" in url:
                try:
                    body_info = driver.execute_cdp_cmd(
                        "Network.getResponseBody",
                        {"requestId": request_id},
                    )
                    body = body_info.get("body", "")
                except Exception as exc:
                    body = ""
                    item["body_error"] = repr(exc)

                if body:
                    interesting = any(
                        token in body
                        for token in (
                            "모집인원",
                            "경쟁률",
                            "전형 결과",
                            "최종등록자",
                            "70%",
                            "univDetail",
                            "selection",
                        )
                    )
                    item["body_length"] = len(body)
                    item["interesting_body"] = interesting

                    if interesting or len(body) <= 400000:
                        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", url)[-110:]
                        ext = ".json" if "json" in item["mime_type"].lower() else ".txt"
                        body_path = body_dir / f"{len(items):03d}_{safe}{ext}"
                        self.write_text(body_path, body[:2000000])
                        item["body_file"] = str(body_path.name)

            items.append(item)

        return items

    def save_screenshot(self, driver, path):
        try:
            driver.save_screenshot(str(path))
        except Exception:
            pass

    def write_json(self, path, value):
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def write_text(self, path, value):
        path.write_text(value or "", encoding="utf-8", errors="replace")
