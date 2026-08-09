from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup


PROCOLLEGE_URL = "https://www.procollege.kr/web/entrance/webEntrancePreResult.do"

PHASE_MAP = {
    "수시1차": "SUSI",
    "수시2차": "SUSI",
    "정시": "JEONGSI",
    "정시모집": "JEONGSI",
}


@dataclass
class ProcollegeAdmissionRow:
    region: str
    university_name: str
    university_code: str
    recruitment_period: str
    recruitment_unit: str
    recruitment_count: Optional[int]
    day_night: str
    selection_category: str
    selection_name: str
    csat_basis: str
    student_basis: str
    competition_rate: Optional[Decimal]
    metrics: dict[str, tuple[Decimal, str]] = field(default_factory=dict)

    @property
    def admission_phase(self) -> str:
        return PHASE_MAP.get(self.recruitment_period, "")

    @property
    def recruitment_group(self) -> str:
        values = [
            value
            for value in (self.recruitment_period, self.day_night)
            if value
        ]
        return " · ".join(values)


def clean_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def parse_int(value) -> Optional[int]:
    text = clean_text(value).replace(",", "")
    match = re.fullmatch(r"\d+", text)
    if not match:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_decimal(value) -> Optional[Decimal]:
    text = clean_text(value)
    if not text:
        return None

    text = text.replace(",", "")
    text = re.sub(r"\s*:\s*1\s*$", "", text)

    if text in {"-", "–", "—", "없음", "미제공", "해당없음"}:
        return None

    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return None

    try:
        return Decimal(text)
    except InvalidOperation:
        return None



def normalize_procollege_match_name(value: str) -> str:
    """전문대학포털 대학명과 K-unirank 대학명을 보수적으로 비교하는 키.

    '대학교'와 '대학'의 종결어미 차이만 통일한다.
    '경북전문대학교'와 '경북대학교'처럼 본체가 다른 이름은 절대 같아지지 않는다.
    """
    value = clean_text(value)
    if not value:
        return ""

    value = re.sub(r"^국립(?=[가-힣A-Za-z])", "", value)
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[()\[\]{}·ㆍ,._-]", "", value)

    if value.endswith("대학교"):
        value = value[:-3]
    elif value.endswith("대학"):
        value = value[:-2]

    return value.lower()


def sanitize_procollege_metric(value, unit: str):
    value = parse_decimal(value)
    if value is None:
        return None

    # Procollege는 일부 미제공 칸을 0/0.00으로 내려보내는 경우가 있다.
    # 합격자 평균/최저 0은 실제 입시 성적으로 사용하지 않는다.
    if value <= 0:
        return None

    normalized_unit = clean_text(unit)

    # 등급은 유효 범위를 벗어나면 잘못된 값/결측치로 본다.
    if "등급" in normalized_unit and not (Decimal("1") <= value <= Decimal("9")):
        return None

    # 백분위는 0 초과 100 이하만 사용한다.
    if "백분위" in normalized_unit and not (Decimal("0") < value <= Decimal("100")):
        return None

    return value


def infer_missing_score_basis(basis: str, raw_values, *, kind: str) -> str:
    """원문 점수산출기준이 비어 있는데 성적값은 존재할 때 최소한으로 보정한다.

    전문대학포털 일부 행은 수능/학생부 산출기준 칸이 비어 있으면서
    합격자 평균/최저 값은 제공한다.

    - 수능: 1~9 -> 등급, 9 초과~100 -> 백분위, 100 초과 -> 점수
    - 학생부: 1~9 -> 등급, 그 외 -> 점수

    원문에 산출기준이 있으면 절대 덮어쓰지 않는다.
    """
    basis = clean_text(basis)
    if basis:
        return basis

    values = []
    for raw in raw_values:
        parsed = parse_decimal(raw)
        if parsed is not None and parsed > 0:
            values.append(parsed)

    if not values:
        return ""

    max_value = max(values)

    if kind == "CSAT":
        if max_value <= Decimal("9"):
            return "등급"
        if max_value <= Decimal("100"):
            return "백분위"
        return "점수"

    if max_value <= Decimal("9"):
        return "등급"
    return "점수"

def extract_university_code(tr) -> str:
    link = tr.find("a", onclick=True)
    if not link:
        return ""

    onclick = link.get("onclick") or ""
    match = re.search(
        r"fn_goLink\(\s*2\s*,\s*['\"]([^'\"]+)['\"]",
        onclick,
    )
    return match.group(1).strip() if match else ""


def find_result_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        caption = table.find("caption")
        caption_text = clean_text(caption.get_text(" ", strip=True) if caption else "")
        if "전년도 입시결과" in caption_text:
            return table

        headers = " ".join(
            clean_text(th.get_text(" ", strip=True))
            for th in table.find_all("th")
        )
        if all(
            token in headers
            for token in ("대학명", "모집", "전공명", "경쟁률", "합격자평균", "합격자최저")
        ):
            return table

    return None


def parse_procollege_results(html: str) -> list[ProcollegeAdmissionRow]:
    soup = BeautifulSoup(html, "html.parser")
    table = find_result_table(soup)
    if table is None:
        return []

    tbody = table.find("tbody")
    if tbody is None:
        return []

    rows: list[ProcollegeAdmissionRow] = []

    for tr in tbody.find_all("tr", recursive=False):
        cells = [
            clean_text(td.get_text(" ", strip=True))
            for td in tr.find_all("td", recursive=False)
        ]

        # 현재 Procollege 전년도 입시결과 표는 데이터 행이 15열이다.
        # 구조가 바뀐 페이지를 억지로 해석하지 않고 건너뛴다.
        if len(cells) != 15:
            continue

        (
            region,
            university_name,
            recruitment_period,
            recruitment_unit,
            recruitment_count_raw,
            day_night,
            selection_category,
            selection_detail,
            csat_basis,
            student_basis,
            competition_rate_raw,
            avg_csat_raw,
            avg_student_raw,
            min_csat_raw,
            min_student_raw,
        ) = cells

        if not university_name or not recruitment_unit:
            continue

        phase = PHASE_MAP.get(recruitment_period)
        if not phase:
            continue

        # 두 전형구분 칸이 동일한 경우 화면에서 같은 문자열을 두 번
        # 보여주지 않도록 상세 전형명은 비운다.
        selection_name = (
            selection_detail
            if selection_detail and selection_detail != selection_category
            else ""
        )

        metrics: dict[str, tuple[Decimal, str]] = {}

        csat_basis = infer_missing_score_basis(
            csat_basis,
            (avg_csat_raw, min_csat_raw),
            kind="CSAT",
        )
        student_basis = infer_missing_score_basis(
            student_basis,
            (avg_student_raw, min_student_raw),
            kind="STUDENT",
        )

        metric_inputs = (
            ("COLLEGE_CSAT_AVERAGE", avg_csat_raw, csat_basis),
            ("COLLEGE_STUDENT_AVERAGE", avg_student_raw, student_basis),
            ("COLLEGE_CSAT_MINIMUM", min_csat_raw, csat_basis),
            ("COLLEGE_STUDENT_MINIMUM", min_student_raw, student_basis),
        )

        for code, raw_value, unit in metric_inputs:
            value = sanitize_procollege_metric(raw_value, unit)
            if value is None:
                continue
            metrics[code] = (value, clean_text(unit))

        rows.append(
            ProcollegeAdmissionRow(
                region=region,
                university_name=university_name,
                university_code=extract_university_code(tr),
                recruitment_period=recruitment_period,
                recruitment_unit=recruitment_unit,
                recruitment_count=parse_int(recruitment_count_raw),
                day_night=day_night,
                selection_category=selection_category,
                selection_name=selection_name,
                csat_basis=csat_basis,
                student_basis=student_basis,
                competition_rate=sanitize_competition_rate(competition_rate_raw),
                metrics=metrics,
            )
        )

    return rows



def sanitize_competition_rate(value):
    value = parse_decimal(value)
    if value is None or value <= 0:
        return None
    return value

def extract_selected_year(html: str) -> Optional[int]:
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", id="sel_1")
    if not select:
        return None

    selected = select.find("option", selected=True)
    if selected is None:
        selected = select.find("option", attrs={"selected": True})

    if selected is None:
        for option in select.find_all("option"):
            raw_selected = clean_text(option.get("selected"))
            if raw_selected:
                selected = option
                break

    if selected is None:
        return None

    return parse_int(selected.get("value"))


def extract_last_page(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    paging = soup.select_one(".pagingWrap")
    if paging is None:
        return 1

    pages = [1]
    for element in paging.find_all(["a", "button"]):
        onclick = element.get("onclick") or ""
        match = re.search(r"fn_linkPage\(\s*(\d+)\s*\)", onclick)
        if match:
            pages.append(int(match.group(1)))

    return max(pages)


def build_search_payload(
    *,
    year: int,
    page: int = 1,
    page_unit: int = 100,
    university_name: str = "",
    recruitment_period: str = "",
    selection_type: str = "",
    day_night: str = "",
) -> dict[str, str]:
    return {
        "schOrderField": "korname",
        "schOrderBy": "asc",
        "pageIndex": str(max(1, page)),
        "openyn": "",
        "chktot1": "",
        "chktot2": "",
        "codeyear": str(year),
        "pageUnit": str(page_unit),
        "cate": "1",
        "univName": university_name,
        "sel_1": str(year),
        "sel_2": recruitment_period,
        "sel_3": selection_type,
        "sel_4": day_night,
        "univregion": "",
        "foundtype": "",
    }
