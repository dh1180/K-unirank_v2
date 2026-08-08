import hashlib
import re
import time
from collections import defaultdict
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DataError, transaction

from admissions.models import AdmissionMetric, AdmissionResult, AdmissionSource, RecruitmentUnit
from admissions.services.adiga import (
    AdigaUniversityDetail,
    extract_result_year,
    has_result_section,
    parse_admission_results,
    parse_university_detail,
    parse_university_entries,
)
from universities.models import University, UniversityCampus, UniversityExternalMapping
from universities.services.university_normalizer import (
    canonical_university_name,
    normalize_address,
    normalize_university_name,
    ranking_university_name,
)


ADIGA_LIST_URL = "https://www.adiga.kr/ucp/uvt/uni/univView.do"
ADIGA_RESULT_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"
ADIGA_SOURCE = "ADIGA"


class Command(BaseCommand):
    help = "대입정보포털 어디가의 최신 공개 입시결과를 가져옵니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--search-year",
            type=int,
            default=date.today().year + 1,
            help="어디가 화면에서 먼저 조회할 학년도입니다. 기본값은 다음 학년도입니다.",
        )
        parser.add_argument(
            "--fallback-years",
            type=int,
            default=1,
            help="최신 화면에 결과가 없을 때 이전 화면을 몇 년까지 확인할지 지정합니다. 기본값 1.",
        )
        parser.add_argument(
            "--university",
            default="",
            help="특정 대학명만 시험할 때 사용합니다.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="처리할 매칭 대학 수를 제한합니다. 0이면 전체입니다.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.2,
            help="대학별 요청 사이 대기 시간입니다.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 저장합니다. 생략하면 매칭과 파싱 결과만 확인합니다.",
        )
        parser.add_argument(
            "--map-only",
            action="store_true",
            help="상세 페이지로 대학 코드를 검증하고 매핑만 저장합니다.",
        )
        parser.add_argument(
            "--show-rows",
            action="store_true",
            help="파싱된 모집단위의 핵심 값을 최대 20건 출력합니다.",
        )
        parser.add_argument(
            "--no-browser-fallback",
            action="store_true",
            help=(
                "최신 결과가 동적으로 로드되는 경우 Chrome 렌더링 fallback을 "
                "사용하지 않습니다."
            ),
        )
        parser.add_argument(
            "--browser-timeout",
            type=int,
            default=15,
            help="동적 ADIGA 결과를 기다릴 최대 시간(초)입니다. 기본값 15.",
        )
        parser.add_argument(
            "--skip-existing",
            "--retry-failed",
            dest="skip_existing",
            action="store_true",
            help=(
                "해당 search-year의 직전 학년도 ADIGA 결과가 이미 DB에 저장된 "
                "코드는 건너뜁니다. 이전 실행에서 실패/누락된 대학만 다시 시도할 "
                "때 사용합니다. --retry-failed는 같은 옵션의 별칭입니다."
            ),
        )

    def handle(self, *args, **options):
        search_year = options["search_year"]
        fallback_years = max(0, options["fallback_years"])
        target_name = options["university"].strip()
        limit = max(0, options["limit"])
        delay = max(0, options["delay"])
        apply_changes = options["apply"]
        map_only = options["map_only"]
        show_rows = options["show_rows"]
        browser_fallback = not options["no_browser_fallback"]
        browser_timeout = max(5, options["browser_timeout"])
        skip_existing = options["skip_existing"]
        target_admission_year = search_year - 1

        session = self.build_session()
        list_html = self.fetch(
            session,
            ADIGA_LIST_URL,
            params={"menuId": "PCUVTINF2000", "searchSyr": search_year},
        )
        entries = parse_university_entries(list_html)

        if not entries:
            raise CommandError(
                "어디가 대학 목록에서 대학 코드를 찾지 못했습니다. "
                "사이트 구조가 바뀌었을 수 있습니다."
            )

        entries = self.prefilter_entries(entries, target_name)
        active_universities = list(
            University.objects.filter(is_active=True).prefetch_related("campuses")
        )
        stats = defaultdict(int)
        processed = 0

        self.stdout.write(
            f"ADIGA 코드 후보 {len(entries)}개를 상세 페이지에서 다시 검증합니다."
        )
        if not apply_changes:
            self.stdout.write(self.style.WARNING("미리보기 모드입니다. DB는 변경하지 않습니다."))
        if skip_existing:
            self.stdout.write(
                f"기존 {target_admission_year}학년도 ADIGA 결과가 저장된 코드는 건너뜁니다."
            )

        for entry in entries:
            if limit and processed >= limit:
                break

            if skip_existing and self.has_existing_adiga_results(
                code=entry.code,
                search_year=search_year,
                admission_year=target_admission_year,
            ):
                stats["skipped_existing"] += 1
                continue

            # 요청 성공 여부와 관계없이 대학별 간격을 보장한다.
            # 이전 구현은 실패 시 continue로 delay를 건너뛰어 DNS 장애 때 요청이
            # 연속으로 몰릴 수 있었다.
            if delay:
                time.sleep(delay)

            primary_html = None
            try:
                primary_html = self.fetch_result_page(
                    session=session,
                    code=entry.code,
                    search_year=search_year,
                )
            except CommandError as exc:
                stats["failed"] += 1
                self.stderr.write(f"[{entry.code}] {exc}")
                continue

            detail = parse_university_detail(primary_html, code=entry.code)
            if detail is None:
                stats["invalid_code"] += 1
                continue

            university = self.match_detail_university(
                detail=detail,
                code=entry.code,
                universities=active_universities,
            )
            if university is None:
                stats["unmatched"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"미매칭: {detail.name} | {detail.address or '주소 없음'} | {entry.code}"
                    )
                )
                continue

            if target_name and not self.matches_target(target_name, university, detail):
                continue

            processed += 1
            stats["matched"] += 1

            if apply_changes:
                with transaction.atomic():
                    campus = self.save_mapping(detail, university)
            else:
                campus = self.find_existing_adiga_campus(entry.code)

            if map_only:
                self.stdout.write(
                    f"[{processed}] {entry.code} {detail.name} -> {university.name}"
                )
                continue

            try:
                selected = self.find_latest_result_page(
                    session=session,
                    code=entry.code,
                    first_html=primary_html,
                    first_search_year=search_year,
                    fallback_years=fallback_years,
                    browser_fallback=browser_fallback,
                    browser_timeout=browser_timeout,
                )
            except CommandError as exc:
                stats["failed"] += 1
                self.stderr.write(
                    f"[{entry.code}] {university.name}: {exc}"
                )
                continue

            used_search_year, admission_year, html, rows = selected
            fallback_note = ""
            if used_search_year != search_year:
                fallback_note = f" / {used_search_year} 화면 fallback"
            elif "<!-- KUNIRANK_ELEMENT_RENDERED -->" in html:
                fallback_note = " / Chrome 엘리먼트 결과"

            self.stdout.write(
                f"[{processed}] {entry.code} {detail.name} -> {university.name} | "
                f"{admission_year}학년도 {len(rows)}건{fallback_note}"
            )

            if show_rows and rows:
                self.print_row_samples(rows)

            if not rows:
                stats["empty"] += 1
            elif apply_changes:
                try:
                    with transaction.atomic():
                        saved = self.save_results(
                            university=university,
                            campus=campus,
                            detail=detail,
                            search_year=used_search_year,
                            admission_year=admission_year,
                            html=html,
                            rows=rows,
                        )
                except DataError as exc:
                    stats["failed"] += 1
                    self.stderr.write(
                        f"[{entry.code}] {university.name} DB 저장 실패: {exc}"
                    )
                    continue

                stats["saved"] += saved
            else:
                stats["parsed"] += len(rows)

        if apply_changes and stats["saved"]:
            call_command("recalculate_admission_aggregates")

        self.print_stats(stats)

    def prefilter_entries(self, entries, target_name):
        if not target_name:
            return entries

        rough_matches = [
            entry
            for entry in entries
            if entry.name and target_name in entry.name
        ]
        remaining = [entry for entry in entries if entry not in rough_matches]
        return rough_matches + remaining

    def find_latest_result_page(
        self,
        session,
        code,
        first_html,
        first_search_year,
        fallback_years,
        browser_fallback,
        browser_timeout,
    ):
        """최신 공개 결과를 우선 사용하고 Chrome 상세표로 보강한다.

        2027 화면의 requests HTML에도 일부 결과표가 들어오는 대학이 있다.
        이전 구현은 여기서 한 행이라도 파싱되면 즉시 반환해서, 예를 들어
        학생부종합만 31건 잡힌 상태에서 학생부교과/정시 및 상세 팝업의
        공식 평균백분위를 전혀 확인하지 않았다.

        최신 화면에 결과 영역이 있으면 정적 HTML 결과가 있더라도 Chrome을
        한 번 더 사용해 세 탭의 Q2/상세표를 수집하고 두 결과를 합친다.
        Chrome 보강이 실패해도 정적 HTML에 정상 결과가 있으면 그것은 보존한다.
        """
        attempts = [(first_search_year, first_html)]

        for offset in range(1, fallback_years + 1):
            year = first_search_year - offset
            try:
                html = self.fetch_result_page(session, code, year)
            except CommandError:
                continue
            attempts.append((year, html))

        last = None

        for used_search_year, html in attempts:
            admission_year = extract_result_year(
                html,
                fallback=used_search_year - 1,
            )
            static_rows = parse_admission_results(html, admission_year)
            last = (used_search_year, admission_year, html, static_rows)

            latest_result_exists = has_result_section(html, admission_year)

            # 최신 Q2가 있는 화면은 정적 HTML만 믿지 않는다. ADIGA 상세 팝업에
            # 학생부 환산등급/수능 과목별 백분위/공식 평균백분위가 더 들어있다.
            if latest_result_exists and browser_fallback:
                try:
                    rendered_html = self.fetch_rendered_result_page(
                        code=code,
                        search_year=used_search_year,
                        admission_year=admission_year,
                        timeout=browser_timeout,
                    )
                    rendered_rows = parse_admission_results(
                        rendered_html,
                        admission_year,
                    )
                except CommandError:
                    # 정적 HTML에서 이미 결과를 얻었다면 Chrome 일시 실패 때문에
                    # 정상 데이터까지 버리지 않는다.
                    if static_rows:
                        return last
                    raise

                merged_rows = self.merge_admission_rows(
                    static_rows,
                    rendered_rows,
                )
                if merged_rows:
                    return (
                        used_search_year,
                        admission_year,
                        rendered_html,
                        merged_rows,
                    )

            if static_rows:
                return last

            if latest_result_exists:
                if not browser_fallback:
                    raise CommandError(
                        f"{admission_year}학년도 결과 제목은 존재하지만 "
                        "결과표가 동적으로 로드됩니다. "
                        "--no-browser-fallback을 제거해 주세요."
                    )

                raise CommandError(
                    f"{admission_year}학년도 결과 영역은 존재하지만 "
                    "Chrome 렌더링 후에도 모집단위 결과를 읽지 못했습니다. "
                    "이 대학은 이전 연도로 fallback하지 않습니다."
                )

            # 결과 제목 자체가 없을 때만 다음(이전) searchSyr를 확인한다.

        return last or (
            first_search_year,
            first_search_year - 1,
            first_html,
            [],
        )

    def merge_admission_rows(self, base_rows, enrichment_rows):
        """정적 결과와 Chrome 상세 결과를 중복 없이 합친다.

        동일 모집단위/전형은 Chrome 상세표의 지표를 우선해 보강한다.
        서로 다른 교과 전형처럼 selection_name이 다른 행은 합치지 않는다.
        """
        merged = {}
        order = []

        def identity(row):
            return (
                (row.recruitment_unit or "").strip(),
                row.admission_phase,
                row.selection_category,
                (row.selection_name or "").strip(),
                (row.recruitment_group or "").strip(),
            )

        def add(row, prefer=False):
            key = identity(row)
            current = merged.get(key)
            if current is None:
                merged[key] = row
                order.append(key)
                return

            # 상세 팝업 값으로 기존 행을 보강한다. 객체는 dataclass라 직접 수정 가능하다.
            if prefer:
                if row.recruitment_count is not None:
                    current.recruitment_count = row.recruitment_count
                if row.applicant_count is not None:
                    current.applicant_count = row.applicant_count
                if row.registered_count is not None:
                    current.registered_count = row.registered_count
                if row.competition_rate is not None:
                    current.competition_rate = row.competition_rate
                current.metrics.update(row.metrics or {})
            else:
                for code, value in (row.metrics or {}).items():
                    current.metrics.setdefault(code, value)

        for row in base_rows or []:
            add(row, prefer=False)
        for row in enrichment_rows or []:
            add(row, prefer=True)

        return [merged[key] for key in order]

    def fetch_rendered_result_page(
        self,
        code,
        search_year,
        admission_year,
        timeout,
    ):
        """ADIGA가 렌더링한 실제 입시결과 엘리먼트를 직접 수집한다."""
        try:
            from selenium import webdriver
            from selenium.common.exceptions import WebDriverException
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise CommandError(
                "최신 ADIGA 입시결과는 브라우저 렌더링이 필요합니다. "
                "`pip install -r requirements.txt` 후 다시 실행해 주세요."
            ) from exc

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,3000")
        options.add_argument("--lang=ko-KR")

        url = (
            f"{ADIGA_RESULT_URL}?menuId=PCUVTINF2000"
            f"&searchSyr={search_year}&unvCd={code}"
        )

        driver = None

        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(max(timeout, 20))
            driver.get(url)

            wait = WebDriverWait(driver, timeout)
            wait.until(
                lambda d: d.execute_script(
                    "return document.readyState"
                ) == "complete"
            )

            rendered_sections = []

            for tab_code in ("20", "30", "40"):
                tab_buttons = driver.find_elements(
                    By.ID,
                    f"tab_{tab_code}",
                )
                if not tab_buttons:
                    continue

                driver.execute_script(
                    "arguments[0].click();",
                    tab_buttons[0],
                )
                self.wait_for_short_dom_settle(driver)

                result_html = self.collect_adiga_result_elements(
                    driver=driver,
                    admission_year=admission_year,
                    tab_code=tab_code,
                    timeout=timeout,
                )

                if not result_html:
                    continue

                section = (
                    f'<section id="tab_{tab_code}">'
                    f'<div>Q {admission_year}학년도 전형 결과</div>'
                    f'{result_html}'
                    f'</section>'
                )

                rows = parse_admission_results(
                    section,
                    admission_year,
                )

                if self.valid_result_rows(rows):
                    rendered_sections.append(section)

            if not rendered_sections:
                # v24 fallback: 탭 클릭 과정에서 실제 tbAdmRes가 DOM에 생성됐다면
                # 전체 렌더링 HTML을 기존 parser에 그대로 통과시켜 본다.
                # parser는 Q2 결과 섹션과 탭 순서를 다시 검증하므로 Q1 표 오탐을
                # 그대로 저장하지 않는다.
                full_page_html = driver.page_source
                full_page_rows = parse_admission_results(
                    full_page_html,
                    admission_year,
                )
                if self.valid_result_rows(full_page_rows):
                    return (
                        "<!-- KUNIRANK_FULL_BROWSER_RENDERED -->"
                        + full_page_html
                    )

                state = self.adiga_browser_debug_state(
                    driver,
                    admission_year,
                )
                raise CommandError(
                    f"Chrome에서 {admission_year}학년도 Q2 결과 DOM을 "
                    "찾지 못했습니다. "
                    f"Q2텍스트={state['q2_count']}개, "
                    f"Q2leaf={state.get('q2_leaf_count', 0)}개, "
                    f"상세버튼={state['detail_count']}개, "
                    f"tbAdmRes={state['block_count']}개, "
                    f"tblBase={state['table_count']}개"
                )

            html = (
                "<!-- KUNIRANK_ELEMENT_RENDERED -->"
                "<html><body>"
                + "".join(rendered_sections)
                + "</body></html>"
            )

            rows = parse_admission_results(
                html,
                admission_year,
            )

            if not self.valid_result_rows(rows):
                raise CommandError(
                    f"{admission_year}학년도 결과 엘리먼트는 찾았지만 "
                    "모집인원/경쟁률 검증을 통과하지 못했습니다."
                )

            return html

        except WebDriverException as exc:
            raise CommandError(
                "Chrome을 이용한 ADIGA 엘리먼트 수집에 실패했습니다. "
                f"원인: {exc}"
            ) from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def collect_adiga_result_elements(
        self,
        driver,
        admission_year,
        tab_code,
        timeout,
    ):
        """Q2를 열고, 가능하면 '입시결과 상세정보' 팝업을 최우선 수집한다.

        최신 ADIGA는 본문 Q2 안에 요약표(환산점수만)를 두고,
        `입시결과 상세정보` 팝업에서 환산등급/과목별 백분위/공식 평균백분위를
        더 자세히 제공하는 대학이 있다. 요약표를 먼저 반환하면 공식 평백이
        사라지므로 상세 팝업을 먼저 시도하고, 실패할 때만 본문 표를 사용한다.
        """
        import time

        deadline = time.time() + max(10, timeout)

        # Q2가 이미 열린 상태라면 상세 팝업부터 시도한다.
        detail_html = self.collect_adiga_detail_popup(
            driver=driver,
            admission_year=admission_year,
            tab_code=tab_code,
            timeout=min(max(5, timeout), 12),
        )
        if detail_html:
            return detail_html

        targets = self.find_adiga_result_click_targets(
            driver,
            admission_year,
        )

        for target_index in range(len(targets)):
            self.click_adiga_result_target(
                driver,
                target_index,
            )
            self.wait_for_short_dom_settle(driver)

            click_deadline = min(deadline, time.time() + 3.5)
            while time.time() < click_deadline:
                detail_html = self.collect_adiga_detail_popup(
                    driver=driver,
                    admission_year=admission_year,
                    tab_code=tab_code,
                    timeout=5,
                )
                if detail_html:
                    return detail_html

                # 상세 버튼이 아직 생성 중일 수 있으므로 잠깐 기다린다.
                if self.has_adiga_result_detail_button(driver, tab_code):
                    time.sleep(0.25)
                    continue

                time.sleep(0.20)

            if time.time() >= deadline:
                break

        # 상세 팝업이 없는 대학만 본문 결과표를 사용한다.
        html = self.adiga_result_tables_by_semantic_category(
            driver,
            tab_code,
        )
        if html:
            return html

        html = self.adiga_result_blocks_by_tab_code(
            driver,
            tab_code,
        )
        if html:
            return html

        return ""

    def collect_adiga_detail_popup(
        self,
        driver,
        admission_year,
        tab_code,
        timeout=8,
    ):
        """현재 탭의 '입시결과 상세정보'를 열어 상세 결과 HTML을 반환한다.

        ADIGA는 대학에 따라 새 창(window.open) 또는 같은 문서의 modal로
        상세표를 표시한다. 두 방식을 모두 지원한다.
        """
        import time

        original_handle = driver.current_window_handle
        before_handles = set(driver.window_handles)

        clicked = bool(
            driver.execute_script(
                r"""
                const tabCode = String(arguments[0]);

                function parseArgs(el) {
                    const onclick = el.getAttribute("onclick") || "";
                    if (!onclick.includes("fnUnvAnsDetailPopup")) return null;
                    const match = onclick.match(
                        /fnUnvAnsDetailPopup\s*\(([\s\S]*?)\)/
                    );
                    if (!match) return null;
                    return match[1]
                        .split(",")
                        .map(value => value.trim().replace(/^['\"]|['\"]$/g, ""));
                }

                const candidates = [
                    ...document.querySelectorAll("[onclick]")
                ];

                for (const el of candidates) {
                    const args = parseArgs(el);
                    if (!args || args.length < 3 || args[2] !== tabCode) continue;

                    try { el.scrollIntoView({block: "center"}); } catch (_) {}
                    try { el.click(); return true; } catch (_) {}
                    try {
                        el.dispatchEvent(new MouseEvent("click", {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                        }));
                        return true;
                    } catch (_) {}
                }
                return false;
                """,
                str(tab_code),
            )
        )

        if not clicked:
            return ""

        deadline = time.time() + max(3, timeout)
        popup_handle = None

        try:
            popup_grace_deadline = min(deadline, time.time() + 1.2)
            while time.time() < deadline:
                current_handles = set(driver.window_handles)
                new_handles = current_handles - before_handles
                if new_handles:
                    popup_handle = next(iter(new_handles))
                    driver.switch_to.window(popup_handle)
                    break

                # window.open 방식의 새 창이 뜰 시간을 먼저 준다. 메인 페이지의
                # 요약표를 inline 상세표로 오인하면 공식 평균백분위가 누락된다.
                if time.time() >= popup_grace_deadline:
                    inline_html = self.adiga_visible_detail_tables_html(
                        driver,
                        tab_code,
                    )
                    if inline_html:
                        return inline_html

                time.sleep(0.15)

            if popup_handle is None:
                return ""

            # 새 창 상세 결과
            while time.time() < deadline:
                try:
                    ready = driver.execute_script("return document.readyState")
                except Exception:
                    ready = None

                if ready == "complete":
                    popup_html = driver.page_source
                    wrapped = (
                        f'<section id="tab_{tab_code}" '
                        f'data-kunirank-tab-code="{tab_code}">'
                        f'<div>Q {admission_year}학년도 전형 결과</div>'
                        f'{popup_html}'
                        f'</section>'
                    )
                    rows = parse_admission_results(wrapped, admission_year)
                    if self.valid_result_rows(rows):
                        return wrapped

                time.sleep(0.20)

            return ""
        finally:
            # 팝업을 열었다면 항상 닫고 원래 대학 페이지로 복귀한다.
            try:
                if popup_handle is not None and popup_handle in driver.window_handles:
                    driver.close()
            except Exception:
                pass
            try:
                if original_handle in driver.window_handles:
                    driver.switch_to.window(original_handle)
            except Exception:
                pass

    def adiga_visible_detail_tables_html(self, driver, tab_code):
        """같은 페이지 modal에 생성된 상세 결과표를 현재 탭 코드로 감싼다."""
        return driver.execute_script(
            r"""
            const tabCode = String(arguments[0]);

            function compact(text) {
                return (text || "").replace(/\s+/g, "").trim();
            }

            function visible(el) {
                if (!el) return false;
                const style = getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function isResultTable(table) {
                const text = compact(table.textContent || "");
                return text.includes("모집단위") &&
                       text.includes("모집인원") &&
                       text.includes("경쟁률");
            }

            function nearestTitle(table) {
                let node = table;
                for (let depth = 0; node && depth < 8; depth++, node = node.parentElement) {
                    const candidates = [
                        ...node.querySelectorAll("h1,h2,h3,h4,h5,h6,strong,.tit")
                    ];
                    let best = null;
                    for (const title of candidates) {
                        if (title.closest("table")) continue;
                        const pos = title.compareDocumentPosition(table);
                        if (pos & Node.DOCUMENT_POSITION_FOLLOWING) best = title;
                    }
                    if (best) return best.outerHTML;
                }
                return "";
            }

            const parts = [];
            const seen = new Set();
            for (const table of document.querySelectorAll("table.tblBase, table")) {
                if (!visible(table) || !isResultTable(table)) continue;
                const signature = compact(table.textContent || "");
                if (!signature || seen.has(signature)) continue;
                seen.add(signature);
                parts.push(
                    `<div class="tbAdmRes" data-kunirank-tab-code="${tabCode}">` +
                    nearestTitle(table) + table.outerHTML + `</div>`
                );
            }
            return parts.join("\n");
            """,
            str(tab_code),
        ) or ""

    def adiga_result_tables_by_semantic_category(self, driver, tab_code):
        """본문 결과를 block 단위가 아니라 *table 단위*로 분류한다.

        한 tbAdmRes 안에 종합/교과/정시 표가 함께 남는 대학에서 block의 첫 제목만
        보고 분류하면 교과가 사라질 수 있다. 각 table 바로 앞 제목과 헤더를 사용한다.
        """
        return driver.execute_script(
            r"""
            const wanted = String(arguments[0]);

            function compact(text) {
                return (text || "").replace(/\s+/g, "").trim();
            }

            function visible(el) {
                if (!el) return false;
                const style = getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function isResultTable(table) {
                const text = compact(table.textContent || "");
                return text.includes("모집단위") &&
                       text.includes("모집인원") &&
                       text.includes("경쟁률");
            }

            function ancestorTabCode(table) {
                let node = table;
                for (let depth = 0; node && depth < 15; depth++, node = node.parentElement) {
                    const attrs = [
                        node.id || "",
                        node.className || "",
                        node.getAttribute?.("data-tab") || "",
                        node.getAttribute?.("data-tab-code") || "",
                        node.getAttribute?.("data-target") || "",
                        node.getAttribute?.("aria-labelledby") || "",
                    ].join(" ");
                    const match = String(attrs).match(/(?:^|[^0-9])(20|30|40)(?:[^0-9]|$)/);
                    if (match && /tab|panel|content|pane|tsrd|slcn|article|artcl/i.test(attrs)) {
                        return match[1];
                    }
                }
                return null;
            }

            function nearestTitle(table) {
                const block = table.closest("div.tbAdmRes") || table.parentElement;
                if (!block) return null;
                let best = null;
                for (const title of block.querySelectorAll("h1,h2,h3,h4,h5,h6,strong,.tit")) {
                    if (title.closest("table")) continue;
                    const pos = title.compareDocumentPosition(table);
                    if (pos & Node.DOCUMENT_POSITION_FOLLOWING) best = title;
                }
                return best;
            }

            function classify(table) {
                const titleEl = nearestTitle(table);
                const title = compact(titleEl ? titleEl.textContent : "");
                const body = compact(table.textContent || "");

                if (title.includes("학생부교과") ||
                    title.includes("교과우수자") ||
                    title.includes("교과성적우수") ||
                    title.includes("교과추천") ||
                    title.includes("학교장추천")) return "30";

                if (title.includes("학생부종합") ||
                    title.includes("학교생활우수자") ||
                    title.includes("미래인재") ||
                    title.includes("활동우수") ||
                    title.includes("강원인재")) return "20";

                if (title.includes("수능위주") ||
                    title.includes("수능전형") ||
                    title.startsWith("수능")) return "40";

                // 수능 결과표의 고유 헤더. '환산점수'만으로는 교과와 구분하지 않는다.
                if (body.includes("백분위") ||
                    body.includes("평균백분위") ||
                    body.includes("수능표준점수") ||
                    body.includes("총점(수능)") ||
                    body.includes("과목별백분위")) return "40";

                const ancestor = ancestorTabCode(table);
                if (ancestor) return ancestor;

                return null;
            }

            const result = [];
            const seen = new Set();

            for (const table of document.querySelectorAll("table.tblBase, table")) {
                if (!visible(table) || !isResultTable(table)) continue;
                if (classify(table) !== wanted) continue;

                const signature = compact(table.textContent || "");
                if (!signature || seen.has(signature)) continue;
                seen.add(signature);

                const titleEl = nearestTitle(table);
                result.push(
                    `<div class="tbAdmRes" data-kunirank-tab-code="${wanted}">` +
                    (titleEl ? titleEl.outerHTML : "") +
                    table.outerHTML +
                    `</div>`
                );
            }

            return result.join("\n");
            """,
            str(tab_code),
        ) or ""

    def find_adiga_result_click_targets(
        self,
        driver,
        admission_year,
    ):
        """Q2 문구 주변에서 실제 클릭 이벤트가 걸릴 수 있는 요소를 표시한다."""
        target = f"{admission_year}학년도 전형 결과"

        return driver.execute_script(
            r"""
            const targetText = arguments[0];

            function normalize(text) {
                return (text || "")
                    .replace(/\s+/g, " ")
                    .trim();
            }

            function visible(el) {
                if (!el) return false;
                const style = getComputedStyle(el);
                if (
                    style.display === "none" ||
                    style.visibility === "hidden"
                ) {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            document.querySelectorAll(
                "[data-kunirank-q2-click]"
            ).forEach(el => {
                el.removeAttribute("data-kunirank-q2-click");
            });

            const raw = [
                ...document.querySelectorAll(
                    "button, a, [role='button'], summary, dt, " +
                    "h1, h2, h3, h4, h5, h6, div, li, span, p"
                )
            ].filter(el => {
                if (!visible(el)) return false;
                const text = normalize(
                    el.innerText || el.textContent || ""
                );
                return (
                    text === targetText ||
                    text === `Q ${targetText}` ||
                    (
                        text.includes(targetText) &&
                        text.length <= targetText.length + 18
                    )
                );
            });

            raw.sort((a, b) => {
                const at = normalize(a.innerText || a.textContent || "");
                const bt = normalize(b.innerText || b.textContent || "");
                return at.length - bt.length;
            });

            const ordered = [];
            const seen = new Set();

            function add(el) {
                if (!el || seen.has(el)) return;
                seen.add(el);
                ordered.push(el);
            }

            for (const label of raw.slice(0, 5)) {
                add(label.closest(
                    "button, a, [role='button'], summary, dt"
                ));

                for (const child of label.querySelectorAll(
                    "button, a, [role='button'], summary"
                )) {
                    add(child);
                }

                let node = label;
                for (let depth = 0; node && depth < 8; depth++) {
                    add(node);

                    if (node.previousElementSibling) {
                        const previous = node.previousElementSibling;
                        const previousText = normalize(
                            previous.innerText || previous.textContent || ""
                        );
                        if (
                            previousText.includes(targetText) ||
                            previous.matches(
                                "button, a, [role='button'], summary, dt"
                            )
                        ) {
                            add(previous);
                        }
                    }

                    node = node.parentElement;
                }
            }

            const result = [];

            ordered.forEach((el, index) => {
                if (!visible(el)) return;
                el.setAttribute(
                    "data-kunirank-q2-click",
                    String(result.length)
                );
                result.push({
                    index: result.length,
                    tag: el.tagName,
                    className: el.className || "",
                    text: normalize(
                        el.innerText || el.textContent || ""
                    ).slice(0, 140),
                });
            });

            return result;
            """,
            target,
        ) or []

    def click_adiga_result_target(
        self,
        driver,
        target_index,
    ):
        """표시한 Q2 후보 하나를 브라우저 클릭과 DOM 이벤트 둘 다로 누른다."""
        return bool(
            driver.execute_script(
                r"""
                const index = String(arguments[0]);
                const el = document.querySelector(
                    `[data-kunirank-q2-click='${index}']`
                );

                if (!el) return false;

                el.scrollIntoView({block: "center"});

                try {
                    el.click();
                } catch (_) {}

                for (const type of [
                    "pointerdown",
                    "mousedown",
                    "pointerup",
                    "mouseup",
                    "click"
                ]) {
                    try {
                        el.dispatchEvent(
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
                int(target_index),
            )
        )

    def has_adiga_result_detail_button(
        self,
        driver,
        tab_code,
    ):
        """Q2가 열려 tabCode에 맞는 입시결과 상세정보 버튼이 생겼는지 확인한다."""
        return bool(
            driver.execute_script(
                r"""
                const tabCode = String(arguments[0]);

                for (const el of document.querySelectorAll("[onclick]")) {
                    const onclick = el.getAttribute("onclick") || "";
                    if (!onclick.includes("fnUnvAnsDetailPopup")) {
                        continue;
                    }

                    const match = onclick.match(
                        /fnUnvAnsDetailPopup\s*\(([\s\S]*?)\)/
                    );
                    if (!match) continue;

                    const args = match[1]
                        .split(",")
                        .map(value =>
                            value.trim().replace(/^['\"]|['\"]$/g, "")
                        );

                    if (args.length >= 3 && args[2] === tabCode) {
                        return true;
                    }
                }

                return false;
                """,
                str(tab_code),
            )
        )

    def adiga_result_blocks_by_semantic_category(
        self,
        driver,
        tab_code,
    ):
        """tbAdmRes 자체의 명시적 의미 정보로 20/30/40 결과를 분류한다.

        최신 ADIGA에서는 Q2 accordion wrapper나 onclick 버튼이 없어도
        결과 블록이 DOM에 생성되는 경우가 있다. 이때 문서 위치만으로 분류하면
        중첩/중복 Q2 노드 때문에 잘못된 탭에 귀속될 수 있다.

        우선순위:
        1. 가까운 조상 DOM의 tab_20 / tab_30 / tab_40 식별자
        2. tbAdmRes 제목의 '학생부 종합' / '학생부 교과' / '수능' 문구
        3. 정시 결과표에만 나타나는 수능 백분위/표준점수 헤더

        전형명 자체(예: 미래인재, 학교장추천)로 카테고리를 추측하지 않는다.
        """
        return driver.execute_script(
            r"""
            const wanted = String(arguments[0]);

            function compact(text) {
                return (text || "")
                    .replace(/\s+/g, "")
                    .trim();
            }

            function isResultTable(table) {
                const text = compact(table.textContent || "");
                return (
                    text.includes("모집단위") &&
                    text.includes("모집인원") &&
                    text.includes("경쟁률")
                );
            }

            function visible(el) {
                if (!el) return false;
                const style = getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function ancestorTabCode(block) {
                let node = block;
                for (let depth = 0; node && depth < 14; depth++) {
                    const attrs = [
                        node.id || "",
                        node.className || "",
                        node.getAttribute?.("data-tab") || "",
                        node.getAttribute?.("data-tab-code") || "",
                        node.getAttribute?.("data-target") || "",
                        node.getAttribute?.("data-bs-target") || "",
                        node.getAttribute?.("aria-labelledby") || "",
                    ].join(" ");

                    const match = String(attrs).match(
                        /(?:^|[^0-9])(20|30|40)(?:[^0-9]|$)/
                    );
                    if (match) {
                        const token = match[1];
                        // 숫자만 우연히 들어간 일반 class는 피하고,
                        // tab/panel/content/tsrd/slcn 계열 식별자가 있을 때만 채택한다.
                        if (
                            /tab|panel|content|tsrd|slcn|article|artcl/i.test(
                                String(attrs)
                            )
                        ) {
                            return token;
                        }
                    }
                    node = node.parentElement;
                }
                return null;
            }

            function semanticTabCode(block) {
                // 결과 블록 제목이 가장 직접적인 근거다.
                // 상위 wrapper에는 20/30/40과 무관한 숫자가 섞일 수 있으므로
                // 제목을 먼저 보고, 제목으로 결정할 수 없을 때만 조상 DOM을 본다.
                const titleEl = block.querySelector(
                    "h1,h2,h3,h4,h5,h6,strong,.tit"
                );
                const title = compact(
                    titleEl ? titleEl.textContent : ""
                );

                if (
                    title.includes("학생부종합") ||
                    title.includes("학교생활우수자") ||
                    title.includes("미래인재") ||
                    title.includes("활동우수")
                ) return "20";
                if (
                    title.includes("학생부교과") ||
                    title.includes("교과우수자") ||
                    title.includes("교과성적우수") ||
                    title.includes("교과추천") ||
                    title.includes("학교장추천")
                ) return "30";
                if (
                    title.includes("수능위주") ||
                    title.includes("수능전형") ||
                    title.startsWith("수능")
                ) {
                    return "40";
                }

                const ancestor = ancestorTabCode(block);
                if (ancestor) return ancestor;

                const tables = [
                    ...block.querySelectorAll("table.tblBase, table")
                ].filter(isResultTable);

                for (const table of tables) {
                    const text = compact(table.textContent || "");
                    // 학생부교과에도 '대학별환산'이 있으므로 그것만으로는
                    // 정시로 분류하지 않는다. 백분위/수능 표준점수 계열만 사용한다.
                    if (
                        text.includes("백분위") ||
                        text.includes("총점(수능)") ||
                        text.includes("수능표준점수") ||
                        text.includes("수학선택과목응시비율") ||
                        text.includes("과목별백분위")
                    ) {
                        return "40";
                    }
                }

                return null;
            }

            const result = [];
            const seen = new Set();

            for (const block of document.querySelectorAll("div.tbAdmRes")) {
                // ADIGA는 다른 탭의 결과 DOM도 문서에 남겨두는 경우가 있다.
                // 현재 클릭한 탭에서 실제로 보이는 블록만 수집해야
                // 학생부종합 표가 수능 탭으로 잘못 귀속되지 않는다.
                if (!visible(block)) continue;

                const tables = [
                    ...block.querySelectorAll("table.tblBase, table")
                ];
                if (!tables.some(isResultTable)) continue;

                if (semanticTabCode(block) !== wanted) continue;

                const signature = compact(block.textContent || "");
                if (!signature || seen.has(signature)) continue;
                seen.add(signature);
                result.push(block.outerHTML);
            }

            return result.join("\n");
            """,
            str(tab_code),
        ) or ""


    def adiga_result_blocks_by_tab_code(
        self,
        driver,
        tab_code,
    ):
        """Q2 문서 위치를 기준으로 tbAdmRes를 20/30/40에 배정한다.

        최신 ADIGA에서는 `fnUnvAnsDetailPopup` 버튼이 없는 상태에서도
        `tbAdmRes` 결과 DOM이 이미 존재할 수 있다.

        따라서 버튼 onclick을 필수 조건으로 사용하지 않는다.

        문서 순서:
        1번째 `YYYY학년도 전형 결과` -> 학생부종합(20)
        2번째 `YYYY학년도 전형 결과` -> 학생부교과(30)
        3번째 `YYYY학년도 전형 결과` -> 수능위주(40)

        각 tbAdmRes는 자신보다 앞에 있는 가장 가까운 Q2 anchor에 귀속된다.
        """
        return driver.execute_script(
            r"""
            const tabCode = String(arguments[0]);

            const TAB_CODES = ["20", "30", "40"];

            function normalize(text) {
                return (text || "")
                    .replace(/\s+/g, " ")
                    .trim();
            }

            function compact(text) {
                return (text || "")
                    .replace(/\s+/g, "");
            }

            function isResultTable(table) {
                const text = compact(
                    table.textContent || ""
                );

                return (
                    text.includes("모집단위") &&
                    text.includes("모집인원") &&
                    text.includes("경쟁률")
                );
            }

            function visible(el) {
                if (!el) return false;
                const style = getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function isLikelyJeongsiBlock(block) {
                const titleEl = block.querySelector(
                    "h1,h2,h3,h4,h5,h6,strong,.tit"
                );
                const title = compact(titleEl ? titleEl.textContent : "");
                const bodyText = compact(block.textContent || "");

                if (
                    title.includes("수능위주") ||
                    title.includes("수능전형") ||
                    title.startsWith("수능")
                ) return true;

                return (
                    bodyText.includes("백분위") ||
                    bodyText.includes("총점(수능)") ||
                    bodyText.includes("수능표준점수") ||
                    bodyText.includes("수학선택과목응시비율") ||
                    bodyText.includes("과목별백분위")
                );
            }

            function resultBlocks() {
                return [
                    ...document.querySelectorAll("div.tbAdmRes")
                ].filter(block => {
                    if (!visible(block)) return false;

                    const hasResultTable = [
                        ...block.querySelectorAll(
                            "table.tblBase, table"
                        )
                    ].some(isResultTable);
                    if (!hasResultTable) return false;

                    // body 끝으로 이동된 수시 상세블록을 Q2 위치만으로 정시로
                    // 오인하는 것을 막는다. 정시는 수능/백분위 단서가 필수다.
                    if (tabCode === "40" && !isLikelyJeongsiBlock(block)) {
                        return false;
                    }
                    return true;
                });
            }

            function q2LeafAnchors() {
                const yearPattern =
                    /Q?\s*20\d{2}학년도\s*전형\s*결과/;

                const candidates = [
                    ...document.querySelectorAll(
                        "button, a, [role='button'], summary, dt, " +
                        "h1, h2, h3, h4, h5, h6, div, li, span, p"
                    )
                ].filter(el =>
                    yearPattern.test(
                        normalize(
                            el.textContent || ""
                        )
                    )
                );

                // 부모/자식이 같은 Q 문구를 반복해서 9개처럼 잡히는 경우,
                // 같은 문구를 가진 더 작은 descendant가 있으면 부모는 제외한다.
                let leaves = candidates.filter(el => {
                    for (const child of el.querySelectorAll("*")) {
                        if (
                            yearPattern.test(
                                normalize(
                                    child.textContent || ""
                                )
                            )
                        ) {
                            return false;
                        }
                    }
                    return true;
                });

                leaves.sort((a, b) => {
                    if (a === b) return 0;

                    const position =
                        a.compareDocumentPosition(b);

                    if (
                        position &
                        Node.DOCUMENT_POSITION_FOLLOWING
                    ) {
                        return -1;
                    }

                    return 1;
                });

                // 같은 accordion 제목이 span/a 등 형제 구조로 중복될 경우,
                // 서로 매우 가까운 anchor는 하나로 합친다.
                const deduped = [];

                for (const anchor of leaves) {
                    if (!deduped.length) {
                        deduped.push(anchor);
                        continue;
                    }

                    const previous =
                        deduped[deduped.length - 1];

                    const common =
                        previous.parentElement ===
                        anchor.parentElement;

                    if (
                        common &&
                        normalize(previous.textContent) ===
                        normalize(anchor.textContent)
                    ) {
                        continue;
                    }

                    deduped.push(anchor);
                }

                return deduped;
            }

            function nearestPreviousAnchor(
                block,
                anchors
            ) {
                let result = null;

                for (const anchor of anchors) {
                    const position =
                        anchor.compareDocumentPosition(
                            block
                        );

                    if (
                        position &
                        Node.DOCUMENT_POSITION_FOLLOWING
                    ) {
                        result = anchor;
                        continue;
                    }

                    break;
                }

                return result;
            }

            const blocks = resultBlocks();
            const anchors = q2LeafAnchors();

            // 가장 신뢰도 높은 경로:
            // Q2 anchor가 정확히 3개 이상이고 결과 블록도 존재.
            if (
                anchors.length >= 3 &&
                blocks.length
            ) {
                const usableAnchors =
                    anchors.slice(0, 3);

                const wantedIndex =
                    TAB_CODES.indexOf(tabCode);

                if (wantedIndex >= 0) {
                    const wantedAnchor =
                        usableAnchors[wantedIndex];

                    const result = [];
                    const seen = new Set();

                    for (const block of blocks) {
                        const owner =
                            nearestPreviousAnchor(
                                block,
                                usableAnchors
                            );

                        if (owner !== wantedAnchor) {
                            continue;
                        }

                        const signature =
                            compact(
                                block.textContent || ""
                            );

                        if (
                            !signature ||
                            seen.has(signature)
                        ) {
                            continue;
                        }

                        seen.add(signature);
                        result.push(
                            block.outerHTML
                        );
                    }

                    if (result.length) {
                        return result.join("\n");
                    }
                }
            }

            // 보조 경로:
            // onclick이 실제로 존재하는 대학/브라우저에서는 기존 방식도 사용한다.
            function buttonTabCode(button) {
                const onclick =
                    button.getAttribute(
                        "onclick"
                    ) || "";

                if (
                    !onclick.includes(
                        "fnUnvAnsDetailPopup"
                    )
                ) {
                    return null;
                }

                const match =
                    onclick.match(
                        /fnUnvAnsDetailPopup\s*\(([\s\S]*?)\)/
                    );

                if (!match) {
                    return null;
                }

                const args = match[1]
                    .split(",")
                    .map(value =>
                        value
                            .trim()
                            .replace(
                                /^['"]|['"]$/g,
                                ""
                            )
                    );

                if (args.length < 3) {
                    return null;
                }

                return args[2];
            }

            const buttons = [
                ...document.querySelectorAll(
                    "[onclick]"
                )
            ].filter(element =>
                buttonTabCode(element) ===
                tabCode
            );

            const fallback = [];
            const seen = new Set();

            for (const button of buttons) {
                let container =
                    button.closest(
                        ".accordionConInner"
                    );

                if (!container) {
                    let node =
                        button.parentElement;

                    for (
                        let depth = 0;
                        node && depth < 10;
                        depth++
                    ) {
                        if (
                            node.querySelector(
                                "div.tbAdmRes"
                            )
                        ) {
                            container = node;
                            break;
                        }

                        node =
                            node.parentElement;
                    }
                }

                if (!container) {
                    continue;
                }

                for (
                    const block of
                    container.querySelectorAll(
                        "div.tbAdmRes"
                    )
                ) {
                    if (!visible(block)) {
                        continue;
                    }

                    if (
                        ![
                            ...block.querySelectorAll(
                                "table.tblBase, table"
                            )
                        ].some(isResultTable)
                    ) {
                        continue;
                    }

                    const signature =
                        compact(
                            block.textContent || ""
                        );

                    if (
                        !signature ||
                        seen.has(signature)
                    ) {
                        continue;
                    }

                    seen.add(signature);
                    fallback.push(
                        block.outerHTML
                    );
                }
            }

            return fallback.join("\n");
            """,
            str(tab_code),
        ) or ""



    def adiga_browser_debug_state(
        self,
        driver,
        admission_year,
    ):
        """실패 원인을 한 줄로 확인하기 위한 최소 DOM 상태."""
        return driver.execute_script(
            r"""
            const target = `${arguments[0]}학년도 전형 결과`;

            function normalize(text) {
                return (text || "")
                    .replace(/\s+/g, " ")
                    .trim();
            }

            let q2Count = 0;

            for (const el of document.querySelectorAll(
                "button, a, [role='button'], summary, dt, "
                + "h1, h2, h3, h4, h5, h6, div, li, span, p"
            )) {
                const text = normalize(
                    el.innerText || el.textContent || ""
                );

                if (
                    text === target ||
                    text === `Q ${target}` ||
                    (
                        text.includes(target) &&
                        text.length <= target.length + 18
                    )
                ) {
                    q2Count += 1;
                }
            }

            const detailCount = [
                ...document.querySelectorAll("[onclick]")
            ].filter(el =>
                (el.getAttribute("onclick") || "")
                    .includes("fnUnvAnsDetailPopup")
            ).length;

            const blocks = [
                ...document.querySelectorAll("div.tbAdmRes")
            ];

            const tables = [
                ...document.querySelectorAll("table.tblBase")
            ];

            const yearPattern =
                /Q?\s*20\d{2}학년도\s*전형\s*결과/;

            const q2Leaves = [
                ...document.querySelectorAll(
                    "button, a, [role='button'], summary, dt, "
                    + "h1, h2, h3, h4, h5, h6, div, li, span, p"
                )
            ].filter(el => {
                if (
                    !yearPattern.test(
                        normalize(
                            el.textContent || ""
                        )
                    )
                ) {
                    return false;
                }

                for (
                    const child of
                    el.querySelectorAll("*")
                ) {
                    if (
                        yearPattern.test(
                            normalize(
                                child.textContent || ""
                            )
                        )
                    ) {
                        return false;
                    }
                }

                return true;
            });

            return {
                q2_count: q2Count,
                q2_leaf_count: q2Leaves.length,
                detail_count: detailCount,
                block_count: blocks.length,
                table_count: tables.length,
            };
            """,
            int(admission_year),
        ) or {
            "q2_count": 0,
            "detail_count": 0,
            "block_count": 0,
            "table_count": 0,
        }


    def valid_result_rows(self, rows):
        """실제 입시결과 행인지 검증한다.

        ADIGA에는 모집인원/경쟁률이 0으로 공개되지만 환산점수/환산등급은
        정상 제공되는 대학이 있다(예: 최신 한국항공대 결과).
        따라서 0을 '데이터 없음'으로 취급하면 정상 결과표 전체가 탈락한다.

        parse_admission_results()를 이미 통과한 행만 들어오므로, 모집단위가 있고
        1) 공개 성적 지표가 하나 이상 있거나
        2) 모집/지원/등록/경쟁률 값이 명시되어 있으면
        유효한 결과 행으로 본다. 숫자 0도 ADIGA가 명시한 값이면 유효하다.
        """
        if not rows:
            return False

        valid = 0

        for row in rows:
            has_unit = bool((row.recruitment_unit or "").strip())
            has_metric = bool(row.metrics)
            has_explicit_count = any(
                value is not None
                for value in (
                    row.recruitment_count,
                    row.applicant_count,
                    row.registered_count,
                    row.competition_rate,
                )
            )

            if has_unit and (has_metric or has_explicit_count):
                valid += 1

        return valid >= max(
            1,
            (len(rows) + 1) // 2,
        )

    def wait_for_short_dom_settle(self, driver):
        import time
        time.sleep(0.7)


    def match_detail_university(self, detail, code, universities):
        existing = (
            UniversityExternalMapping.objects
            .select_related("university")
            .filter(source=ADIGA_SOURCE, external_code=code)
            .first()
        )
        if existing and existing.university.is_active:
            return existing.university

        rank_name = ranking_university_name(
            detail.name,
            campus_name=detail.campus_label,
            address=detail.address,
        )
        rank_key = normalize_university_name(rank_name)
        detail_base_key = normalize_university_name(
            self.base_name(detail.name)
        )

        candidates = []
        for university in universities:
            candidate_key = normalize_university_name(university.name)
            if candidate_key == rank_key:
                candidates.append((100 + self.address_score(detail.address, university), university))
                continue

            if (
                candidate_key.startswith(detail_base_key)
                or detail_base_key.startswith(candidate_key)
            ):
                score = 30 + self.address_score(detail.address, university)
                candidates.append((score, university))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score = candidates[0][0]
        best = [university for score, university in candidates if score == best_score]

        if len(best) == 1:
            return best[0]

        exact = [
            university
            for university in best
            if normalize_university_name(university.name) == rank_key
        ]
        if len(exact) == 1:
            return exact[0]

        return None

    def base_name(self, name):
        name = canonical_university_name(name)
        name = re.sub(r"\s+(?:[^\s]+캠퍼스|[^\s]+교정)$", "", name).strip()
        return name

    def address_score(self, detail_address, university):
        detail_address = normalize_address(detail_address)
        if not detail_address:
            return 0

        addresses = [normalize_address(university.address)]
        addresses.extend(
            normalize_address(campus.address)
            for campus in university.campuses.all()
        )

        return max(
            (self.single_address_score(detail_address, address) for address in addresses if address),
            default=0,
        )

    def single_address_score(self, left, right):
        left_parts = left.split()
        right_parts = right.split()
        score = 0

        if left == right:
            return 30

        if left_parts and right_parts and left_parts[0] == right_parts[0]:
            score += 5

        if len(left_parts) >= 2 and len(right_parts) >= 2:
            if left_parts[1] == right_parts[1]:
                score += 12

        if len(left_parts) >= 3 and len(right_parts) >= 3:
            if left_parts[2] == right_parts[2]:
                score += 6

        return score

    def matches_target(self, target_name, university, detail):
        target_key = normalize_university_name(target_name)
        return (
            target_name in university.name
            or target_name in detail.name
            or target_key in normalize_university_name(university.name)
            or target_key in normalize_university_name(detail.name)
        )

    def build_session(self):
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/150 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.6",
            }
        )
        return session

    def adiga_source_url(self, code, search_year):
        return (
            f"{ADIGA_RESULT_URL}?menuId=PCUVTINF2000"
            f"&searchSyr={search_year}&unvCd={code}"
        )

    def has_existing_adiga_results(self, code, search_year, admission_year):
        """정확히 같은 ADIGA 코드/조회연도에 저장된 결과가 있는지 확인한다.

        대학명만으로 검사하면 본교/캠퍼스가 여러 ADIGA 코드로 나뉜 대학에서
        한 코드의 저장 결과 때문에 다른 코드까지 잘못 skip될 수 있다. 따라서
        save_results()가 저장하는 source_url과 admission_year를 함께 비교한다.
        """
        source = (
            AdmissionSource.objects
            .filter(
                source_type=ADIGA_SOURCE,
                admission_year=admission_year,
                source_url=self.adiga_source_url(code, search_year),
            )
            .first()
        )
        return bool(source and source.results.exists())

    def fetch_result_page(self, session, code, search_year):
        return self.fetch(
            session,
            ADIGA_RESULT_URL,
            params={
                "menuId": "PCUVTINF2000",
                "searchSyr": search_year,
                "unvCd": code,
            },
        )

    def fetch(self, session, url, params):
        try:
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"ADIGA 요청 실패: {exc}") from exc

        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def save_mapping(self, detail: AdigaUniversityDetail, university):
        is_primary = not detail.campus_label
        campus_name = detail.campus_label or None

        campus, _ = UniversityCampus.objects.update_or_create(
            source=ADIGA_SOURCE,
            external_code=detail.code,
            defaults={
                "university": university,
                "campus_name": campus_name,
                "address": detail.address or university.address,
                "region": university.region,
                "is_primary": is_primary,
            },
        )

        UniversityExternalMapping.objects.update_or_create(
            source=ADIGA_SOURCE,
            external_code=detail.code,
            defaults={
                "university": university,
                "campus": campus,
                "external_name": detail.name,
            },
        )

        return campus

    def find_existing_adiga_campus(self, code):
        return (
            UniversityCampus.objects
            .filter(source=ADIGA_SOURCE, external_code=code)
            .first()
        )

    def save_results(
        self,
        university,
        campus,
        detail,
        search_year,
        admission_year,
        html,
        rows,
    ):
        source_url = self.adiga_source_url(detail.code, search_year)
        checksum = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()

        source, _ = AdmissionSource.objects.update_or_create(
            university=university,
            admission_year=admission_year,
            source_type="ADIGA",
            source_url=source_url,
            defaults={
                "document_title": (
                    f"대입정보포털 어디가 {admission_year}학년도 전형 결과 "
                    f"({detail.name})"
                ),
                "checksum": checksum,
            },
        )

        source.results.all().delete()
        saved = 0

        for row in rows:
            unit, _ = RecruitmentUnit.objects.get_or_create(
                university=university,
                campus=campus,
                name=row.recruitment_unit,
            )

            result = AdmissionResult.objects.create(
                source=source,
                university=university,
                recruitment_unit=unit,
                admission_year=admission_year,
                admission_phase=row.admission_phase,
                selection_category=row.selection_category,
                selection_name=row.selection_name,
                recruitment_group=row.recruitment_group,
                recruitment_count=row.recruitment_count,
                applicant_count=row.applicant_count,
                registered_count=row.registered_count,
                competition_rate=row.competition_rate,
            )

            for metric_code, value in row.metrics.items():
                if value is None:
                    continue
                AdmissionMetric.objects.create(
                    result=result,
                    metric_code=metric_code,
                    unit=self.metric_unit(metric_code),
                    value=value,
                )

            saved += 1

        return saved

    def metric_unit(self, metric_code):
        if "PERCENTILE" in metric_code:
            return "백분위"
        if "GRADE" in metric_code:
            return "등급"
        if "SCORE" in metric_code:
            return "점"
        return ""

    def print_row_samples(self, rows):
        jonghap_rows = [
            row for row in rows
            if row.admission_phase == "SUSI" and row.selection_category == "학생부종합"
        ]
        gyogwa_rows = [
            row for row in rows
            if row.admission_phase == "SUSI" and row.selection_category == "학생부교과"
        ]
        other_susi_rows = [
            row for row in rows
            if row.admission_phase == "SUSI"
            and row.selection_category not in {"학생부종합", "학생부교과"}
        ]
        jeongsi_rows = [row for row in rows if row.admission_phase == "JEONGSI"]

        samples = []
        samples.extend(jonghap_rows[:5])
        samples.extend(gyogwa_rows[:5])
        samples.extend(other_susi_rows[:3])
        samples.extend(jeongsi_rows[:8])

        self.stdout.write(
            "    파싱 분포: "
            f"학생부종합 {len(jonghap_rows)}건 / "
            f"학생부교과 {len(gyogwa_rows)}건 / "
            f"기타수시 {len(other_susi_rows)}건 / "
            f"정시 {len(jeongsi_rows)}건"
        )

        for row in samples:
            grade50 = row.metrics.get("STUDENT_GRADE_50_CUT")
            grade70 = row.metrics.get("STUDENT_GRADE_70_CUT")
            student_score50 = row.metrics.get("CONVERTED_SCORE_50_CUT")
            student_score70 = row.metrics.get("CONVERTED_SCORE_70_CUT")
            percentile50 = row.metrics.get("CSAT_PERCENTILE_MEAN_50_CUT")
            percentile70 = row.metrics.get("CSAT_PERCENTILE_MEAN_70_CUT")
            converted50 = row.metrics.get("CSAT_CONVERTED_SCORE_50_CUT")
            converted70 = row.metrics.get("CSAT_CONVERTED_SCORE_70_CUT")
            korean70 = row.metrics.get("CSAT_KOREAN_PERCENTILE_70_CUT")
            math70 = row.metrics.get("CSAT_MATH_PERCENTILE_70_CUT")
            inquiry_70 = row.metrics.get("CSAT_INQUIRY_PERCENTILE_70_CUT")
            inquiry1_70 = row.metrics.get("CSAT_INQUIRY1_PERCENTILE_70_CUT")
            inquiry2_70 = row.metrics.get("CSAT_INQUIRY2_PERCENTILE_70_CUT")

            metric_parts = []
            if student_score50 is not None:
                metric_parts.append(f"학생부환산점수50={student_score50}")
            if student_score70 is not None:
                metric_parts.append(f"학생부환산점수70={student_score70}")
            if grade50 is not None:
                metric_parts.append(f"학생부환산등급50={grade50}")
            if grade70 is not None:
                metric_parts.append(f"학생부환산등급70={grade70}")
            if converted50 is not None:
                metric_parts.append(f"수능환산50={converted50}")
            if converted70 is not None:
                metric_parts.append(f"수능환산70={converted70}")
            if percentile50 is not None:
                metric_parts.append(f"공식평백50={percentile50}")
            if percentile70 is not None:
                metric_parts.append(f"공식평백70={percentile70}")
            if any(value is not None for value in (korean70, math70, inquiry_70, inquiry1_70, inquiry2_70)):
                inquiry_text = (
                    str(inquiry_70)
                    if inquiry_70 is not None
                    else f"탐1 {str(inquiry1_70) if inquiry1_70 is not None else '-'} / 탐2 {str(inquiry2_70) if inquiry2_70 is not None else '-'}"
                )
                metric_parts.append(
                    "과목백분위70="
                    f"국 {str(korean70) if korean70 is not None else '-'} / "
                    f"수 {str(math70) if math70 is not None else '-'} / "
                    f"탐 {inquiry_text}"
                )

            metric_text = ", ".join(metric_parts) or "대표지표 없음"
            group_text = f" / {row.recruitment_group}" if row.recruitment_group else ""
            self.stdout.write(
                "    "
                f"{row.admission_phase}/{row.selection_category}{group_text} | "
                f"{row.selection_name or '-'} | {row.recruitment_unit} | "
                f"모집={row.recruitment_count if row.recruitment_count is not None else '-'} | "
                f"경쟁률={row.competition_rate if row.competition_rate is not None else '-'} | "
                f"{metric_text}"
            )

    def print_stats(self, stats):
        self.stdout.write("")
        self.stdout.write(f"상세 페이지 매칭: {stats['matched']}개")
        if stats["parsed"]:
            self.stdout.write(f"파싱 확인: {stats['parsed']}건")
        if stats["saved"]:
            self.stdout.write(self.style.SUCCESS(f"저장 완료: {stats['saved']}건"))
        if stats["empty"]:
            self.stdout.write(f"최신/보조 연도 모두 결과 없음: {stats['empty']}개")
        if stats["unmatched"]:
            self.stdout.write(self.style.WARNING(f"K-unirank 미매칭: {stats['unmatched']}개"))
        if stats["invalid_code"]:
            self.stdout.write(f"유효하지 않은 코드 후보 제거: {stats['invalid_code']}개")
        if stats["skipped_existing"]:
            self.stdout.write(
                f"기존 결과 건너뜀: {stats['skipped_existing']}개"
            )
        if stats["failed"]:
            self.stdout.write(self.style.WARNING(f"요청 실패: {stats['failed']}개"))

