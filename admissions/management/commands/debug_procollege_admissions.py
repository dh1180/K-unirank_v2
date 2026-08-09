from pathlib import Path
import json
import time

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError


PROCOLLEGE_URL = "https://www.procollege.kr/web/entrance/webEntrancePreResult.do"


class Command(BaseCommand):
    help = (
        "전문대학포털(Procollege) 전년도 입시결과 페이지의 검색 폼/테이블 DOM을 진단합니다. "
        "DB는 절대 변경하지 않습니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--university",
            default="인하공업전문대학",
            help="검색을 시도할 전문대학명 (기본: 인하공업전문대학)",
        )
        parser.add_argument(
            "--dump-html",
            action="store_true",
            help="검색 후 HTML을 procollege_debug.html 로 저장합니다.",
        )
        parser.add_argument(
            "--no-search",
            action="store_true",
            help="검색 시도 없이 초기 페이지 DOM만 진단합니다.",
        )

    def handle(self, *args, **options):
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import Select
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError as exc:
            raise CommandError("selenium이 설치되어 있지 않습니다.") from exc

        university = options["university"].strip()

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1600,1200")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )

        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            wait = WebDriverWait(driver, 20)

            self.stdout.write(self.style.WARNING("DB는 변경하지 않습니다. DOM 진단 전용입니다."))
            self.stdout.write(f"접속: {PROCOLLEGE_URL}")

            driver.get(PROCOLLEGE_URL)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=== 초기 페이지 ==="))
            self.stdout.write(f"title: {driver.title}")
            self.stdout.write(f"url: {driver.current_url}")

            self._print_controls(driver, Select)
            self._print_tables(driver.page_source, label="초기")

            if not options["no_search"]:
                self.stdout.write("")
                self.stdout.write(
                    self.style.SUCCESS(f"=== 대학명 검색 자동 시도: {university} ===")
                )
                self._attempt_search(driver, university, Select, By)
                time.sleep(3)

                self.stdout.write(f"검색 후 url: {driver.current_url}")
                self._print_tables(driver.page_source, label="검색 후")

            if options["dump_html"]:
                output = Path.cwd() / "procollege_debug.html"
                output.write_text(driver.page_source, encoding="utf-8")
                self.stdout.write(self.style.SUCCESS(f"HTML 저장: {output}"))

        except Exception as exc:
            raise CommandError(f"Procollege 진단 실패: {type(exc).__name__}: {exc}") from exc
        finally:
            if driver:
                driver.quit()

    def _print_controls(self, driver, Select):
        self.stdout.write("")
        self.stdout.write("=== SELECT 목록 ===")
        selects = driver.find_elements("tag name", "select")
        if not selects:
            self.stdout.write("select 없음")
        for index, element in enumerate(selects, start=1):
            try:
                options = [
                    (opt.get_attribute("value") or "", (opt.text or "").strip())
                    for opt in Select(element).options
                ]
            except Exception:
                options = []
            self.stdout.write(
                f"[SELECT {index}] "
                f"id={element.get_attribute('id')!r} "
                f"name={element.get_attribute('name')!r} "
                f"class={element.get_attribute('class')!r}"
            )
            self.stdout.write(
                "  options="
                + json.dumps(options[:25], ensure_ascii=False)
            )

        self.stdout.write("")
        self.stdout.write("=== INPUT 목록 ===")
        inputs = driver.find_elements("tag name", "input")
        for index, element in enumerate(inputs, start=1):
            self.stdout.write(
                f"[INPUT {index}] "
                f"type={element.get_attribute('type')!r} "
                f"id={element.get_attribute('id')!r} "
                f"name={element.get_attribute('name')!r} "
                f"value={element.get_attribute('value')!r} "
                f"placeholder={element.get_attribute('placeholder')!r} "
                f"displayed={element.is_displayed()}"
            )

        self.stdout.write("")
        self.stdout.write("=== BUTTON 목록 ===")
        buttons = driver.find_elements("tag name", "button")
        for index, element in enumerate(buttons, start=1):
            self.stdout.write(
                f"[BUTTON {index}] "
                f"text={(element.text or '').strip()!r} "
                f"type={element.get_attribute('type')!r} "
                f"id={element.get_attribute('id')!r} "
                f"name={element.get_attribute('name')!r} "
                f"onclick={element.get_attribute('onclick')!r} "
                f"displayed={element.is_displayed()}"
            )

    def _attempt_search(self, driver, university, Select, By):
        # 1. '대학명 / 전공명' 옵션이 들어 있는 select가 있으면 대학명을 선택.
        selected_search_type = False
        for element in driver.find_elements(By.TAG_NAME, "select"):
            try:
                select = Select(element)
                texts = [(option.text or "").strip() for option in select.options]
                if "대학명" in texts and "전공명" in texts:
                    select.select_by_visible_text("대학명")
                    self.stdout.write(
                        f"검색구분 select 선택: "
                        f"id={element.get_attribute('id')!r}, "
                        f"name={element.get_attribute('name')!r} -> 대학명"
                    )
                    selected_search_type = True
                    break
            except Exception:
                continue

        if not selected_search_type:
            self.stdout.write(self.style.WARNING("대학명/전공명 select를 자동 탐지하지 못했습니다."))

        # 2. 표시 중인 text/search input 가운데 검색어 입력칸 후보를 선정.
        candidates = []
        for element in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='search']"):
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                placeholder = (element.get_attribute("placeholder") or "").strip()
                name = (element.get_attribute("name") or "").lower()
                elem_id = (element.get_attribute("id") or "").lower()

                score = 0
                if "검색" in placeholder:
                    score += 20
                if any(token in name for token in ("str", "search", "keyword", "query")):
                    score += 8
                if any(token in elem_id for token in ("str", "search", "keyword", "query")):
                    score += 8
                candidates.append((score, element))
            except Exception:
                continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            self.stdout.write(self.style.ERROR("검색어 input을 찾지 못했습니다."))
            return

        search_input = candidates[0][1]
        search_input.clear()
        search_input.send_keys(university)
        self.stdout.write(
            f"검색어 입력: "
            f"id={search_input.get_attribute('id')!r}, "
            f"name={search_input.get_attribute('name')!r} -> {university}"
        )

        # 3. 화면에 보이는 '검색' 버튼을 우선 클릭.
        search_buttons = []
        for element in driver.find_elements(By.TAG_NAME, "button"):
            try:
                text = " ".join((element.text or "").split())
                if not element.is_displayed() or not element.is_enabled():
                    continue

                score = 0
                if text == "검색":
                    score = 100
                elif "선택조건검색" in text:
                    score = 20
                elif "검색" in text:
                    score = 10
                if score:
                    search_buttons.append((score, element))
            except Exception:
                continue

        search_buttons.sort(key=lambda item: item[0], reverse=True)

        if search_buttons:
            button = search_buttons[0][1]
            self.stdout.write(f"검색 버튼 클릭: {(button.text or '').strip()!r}")
            driver.execute_script("arguments[0].click();", button)
            return

        # 4. 버튼을 못 찾으면 input에서 Enter.
        self.stdout.write(self.style.WARNING("검색 버튼 자동 탐지 실패 -> Enter 검색 시도"))
        from selenium.webdriver.common.keys import Keys
        search_input.send_keys(Keys.ENTER)

    def _print_tables(self, html, label):
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        self.stdout.write("")
        self.stdout.write(f"=== {label} TABLE 목록: {len(tables)}개 ===")

        if not tables:
            self.stdout.write("table 없음")
            return

        for index, table in enumerate(tables, start=1):
            headers = [
                " ".join(cell.get_text(" ", strip=True).split())
                for cell in table.find_all("th")
            ]

            rows = []
            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                values = [
                    " ".join(cell.get_text(" ", strip=True).split())
                    for cell in cells
                ]
                if values:
                    rows.append(values)

            joined_headers = " | ".join(headers)
            looks_admission = any(
                token in joined_headers
                for token in (
                    "대학명",
                    "전공명",
                    "모집시기",
                    "경쟁률",
                    "합격자평균",
                    "합격자최저",
                )
            )

            self.stdout.write(
                f"[TABLE {index}] "
                f"id={table.get('id')!r} "
                f"class={table.get('class')!r} "
                f"rows={len(rows)} "
                f"입시후보={looks_admission}"
            )
            self.stdout.write(f"  headers={headers[:30]}")

            for sample_index, values in enumerate(rows[:5], start=1):
                self.stdout.write(
                    f"  row{sample_index}={json.dumps(values, ensure_ascii=False)}"
                )
