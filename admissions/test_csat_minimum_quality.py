from django.test import SimpleTestCase

from admissions.services.csat_minimum import ParsedCsatMinimumRule
from admissions.services.csat_minimum_quality import normalize_safe_csat_minimum_rule


class CsatMinimumQualityTests(SimpleTestCase):
    def make_rule(self, selection_name, text):
        return ParsedCsatMinimumRule(
            admission_year=2027,
            selection_name=selection_name,
            requirement_text=text,
        )

    def test_rejects_csat_track_from_jeongsi_q1(self):
        rule = self.make_rule(
            "수능 ( 일반전형 )",
            "수능최저학력기준 영어 3등급 이내, 한국사 4등급 이내",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_rejects_explicit_jeongsi_selection(self):
        rule = self.make_rule(
            "정시 기회균형특별전형 ( 농어촌 · 저소득 )",
            "수능최저학력기준 4개 영역 중 3개 영역 등급 합이 7등급 이내",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_rejects_description_misread_as_selection_name(self):
        rule = self.make_rule(
            "- 고등학교 졸업자 또는 법령에 의하여 졸업 이상의 학력이 있다고 인정되는 자 누구나 지원가능한 전형",
            "수능최저학력기준 있음 ( 상주캠퍼스는 미적용 )",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_rejects_generic_table_heading(self):
        rule = self.make_rule(
            "전형요소 및 반영비율 ( 배점 )",
            "수능최저학력기준 없음",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_rejects_generic_jeongsi_method_with_csat_100_percent(self):
        rule = self.make_rule(
            "일반전형",
            "수능최저학력기준 적용 1 단계 : 수능 100% (1.5 배수 선발)",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_preserves_conditional_susi_rule(self):
        rule = self.make_rule(
            "학생부교과 ( 일반전형 )",
            "수능최저학력기준 없음 단, 간호학과는 2개 영역 등급의 합이 9 이내",
        )
        normalized = normalize_safe_csat_minimum_rule(rule)

        self.assertIsNotNone(normalized)
        self.assertIsNone(normalized.applied)
        self.assertIn("간호학과", normalized.requirement_text)
