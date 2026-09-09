from types import SimpleNamespace

from django.test import SimpleTestCase

from admissions.services.csat_minimum import (
    format_csat_minimum_display,
    match_csat_minimum_rule,
    parse_csat_minimum_rules,
)


class CsatMinimumParserTests(SimpleTestCase):
    def test_parses_selection_level_rules_from_q1_only(self):
        html = """
        <div>Q 1. 2026학년도 전형별 주요사항</div>
        <table>
            <tr><th>전형별 주요사항</th><th>내용</th></tr>
            <tr>
                <td>학생부교과(고교추천전형)</td>
                <td>&lt;수능최저학력기준&gt; 2개 영역 등급 합 7 이내 학생부 100%</td>
            </tr>
            <tr>
                <td>학생부종합(미래인재전형)</td>
                <td>수능최저학력기준 없음 서류 100%</td>
            </tr>
        </table>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th>전형</th><th>수능최저학력기준</th></tr>
            <tr><td>과거전형</td><td>3개 합 5</td></tr>
        </table>
        """

        rules = parse_csat_minimum_rules(html, 2026)

        self.assertEqual(len(rules), 2)
        by_name = {rule.selection_name: rule for rule in rules}
        self.assertTrue(by_name["학생부교과(고교추천전형)"].applied)
        self.assertFalse(by_name["학생부종합(미래인재전형)"].applied)
        self.assertIn("2개 영역 등급 합 7", by_name["학생부교과(고교추천전형)"].requirement_text)

    def test_parses_unit_specific_table(self):
        html = """
        <div>2026학년도 전형별 주요사항</div>
        <h3>고교추천전형</h3>
        <table>
            <tr><th>모집단위</th><th>수능최저학력기준</th></tr>
            <tr>
                <td>글로벌융합대학, 과학기술대학</td>
                <td>국어, 영어, 수학, 탐구 중 2개 영역 등급 합 7 이내</td>
            </tr>
            <tr>
                <td>약학대학</td>
                <td>수학 포함 3개 영역 등급 합 5 이내</td>
            </tr>
        </table>
        """

        rules = parse_csat_minimum_rules(html, 2026)

        self.assertEqual(len(rules), 2)
        pharmacy = next(rule for rule in rules if rule.recruitment_unit_name == "약학대학")
        self.assertEqual(pharmacy.selection_name, "고교추천전형")
        self.assertTrue(pharmacy.applied)
        self.assertEqual(
            format_csat_minimum_display(pharmacy),
            "수능최저 수학 포함 3개 영역 등급 합 5 이내",
        )

    def test_match_requires_same_adiga_code_and_confident_name(self):
        result = SimpleNamespace(
            selection_name="고교추천전형",
            recruitment_unit=SimpleNamespace(name="약학대학"),
            source=SimpleNamespace(
                source_url=(
                    "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"
                    "?menuId=PCUVTINF2000&searchSyr=2027&unvCd=0000099"
                )
            ),
        )
        correct = SimpleNamespace(
            selection_name="학생부교과(고교추천전형)",
            recruitment_unit_name="약학대학",
            applied=True,
            requirement_text="수능최저학력기준 수학 포함 3개 영역 합 5 이내",
            source_code="0000099",
        )
        wrong_campus = SimpleNamespace(
            selection_name="학생부교과(고교추천전형)",
            recruitment_unit_name="약학대학",
            applied=True,
            requirement_text="수능최저학력기준 2개 영역 합 7 이내",
            source_code="0000999",
        )

        matched = match_csat_minimum_rule(result, [wrong_campus, correct])

        self.assertIs(matched, correct)

    def test_ambiguous_equal_score_rules_are_not_attached(self):
        result = SimpleNamespace(
            selection_name="지역인재전형",
            recruitment_unit=SimpleNamespace(name="간호학과"),
            source=SimpleNamespace(source_url="?unvCd=0000172"),
        )
        rules = [
            SimpleNamespace(
                selection_name="학생부교과(지역인재전형)",
                recruitment_unit_name="",
                applied=True,
                requirement_text="수능최저학력기준 2개 합 6",
                source_code="0000172",
            ),
            SimpleNamespace(
                selection_name="지역인재전형",
                recruitment_unit_name="",
                applied=True,
                requirement_text="수능최저학력기준 2개 합 7",
                source_code="0000172",
            ),
        ]

        self.assertIsNone(match_csat_minimum_rule(result, rules))
