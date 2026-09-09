from django.test import SimpleTestCase

from admissions.services.csat_minimum import (
    ParsedCsatMinimumRule,
    parse_csat_minimum_rules,
)
from admissions.services.csat_minimum_quality import (
    normalize_safe_csat_minimum_rule,
    rule_matches_university_scope,
)


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

    def test_rejects_jeongsi_recruitment_group_selection(self):
        rule = self.make_rule(
            "항공시스템공학 특별전형 ( 가군 )",
            "수능최저학력기준 3개 영역 등급 합이 10 이내",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_rejects_snu_jeongsi_art_residual_without_jeongsi_label(self):
        rule = self.make_rule(
            "기회균형특별전형 ( 농어촌 · 저소득 ) 미술대학",
            "수능최저학력기준 4개 영역 중 3개 영역 등급 합이 7등급 이내",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_rejects_snu_jeongsi_music_residual_without_jeongsi_label(self):
        rule = self.make_rule(
            "기회균형특별전형 ( 농어촌 · 저소득 ) 음악대학 성악과",
            "수능최저학력기준 4개 영역 중 3개 영역 등급 합이 7등급 이내",
        )
        self.assertIsNone(normalize_safe_csat_minimum_rule(rule))

    def test_preserves_snu_susi_social_integration(self):
        rule = self.make_rule(
            "수시 기회균형특별전형 ( 사회통합 )",
            "수능최저학력기준 없음",
        )
        normalized = normalize_safe_csat_minimum_rule(rule)
        self.assertIsNotNone(normalized)
        self.assertFalse(normalized.applied)

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

    def test_hongik_main_rejects_explicit_sejong_rule(self):
        rule = self.make_rule(
            "교과우수자전형 ( 세종 )",
            "수능최저학력기준 1개 영역 4등급 이내",
        )
        normalized = normalize_safe_csat_minimum_rule(rule)
        self.assertIsNotNone(normalized)
        self.assertFalse(rule_matches_university_scope(normalized, "홍익대학교"))

    def test_hongik_main_accepts_explicit_seoul_rule(self):
        rule = self.make_rule(
            "학교장추천자전형 ( 서울 )",
            "수능최저학력기준 2개 영역 등급 합 5 이내",
        )
        normalized = normalize_safe_csat_minimum_rule(rule)
        self.assertIsNotNone(normalized)
        self.assertTrue(rule_matches_university_scope(normalized, "홍익대학교"))

    def test_hongik_sejong_rejects_explicit_seoul_rule(self):
        rule = self.make_rule(
            "학교장추천자전형 ( 서울 )",
            "수능최저학력기준 2개 영역 등급 합 5 이내",
        )
        normalized = normalize_safe_csat_minimum_rule(rule)
        self.assertIsNotNone(normalized)
        self.assertFalse(
            rule_matches_university_scope(normalized, "홍익대학교 세종캠퍼스")
        )

    def test_common_rule_is_preserved_for_hongik_scope(self):
        rule = self.make_rule(
            "고른기회 I 전형",
            "수능최저학력기준 없음",
        )
        normalized = normalize_safe_csat_minimum_rule(rule)
        self.assertIsNotNone(normalized)
        self.assertTrue(rule_matches_university_scope(normalized, "홍익대학교"))
        self.assertTrue(
            rule_matches_university_scope(normalized, "홍익대학교 세종캠퍼스")
        )


class CsatMinimumParserPhaseTests(SimpleTestCase):
    def test_tab_40_jeongsi_table_is_excluded_structurally(self):
        html = """
        <section id="tab_30">
            <h3>Q 1. 2027학년도 전형별 주요사항</h3>
            <table>
                <tr>
                    <td>학생부교과 ( 지역균형전형 )</td>
                    <td>수능최저학력기준 2개 영역 등급 합이 7 이내</td>
                </tr>
            </table>
        </section>
        <section id="tab_40">
            <h3>Q 1. 2027학년도 전형별 주요사항</h3>
            <table>
                <tr>
                    <td>기회균형특별전형 ( 농어촌 · 저소득 ) 미술대학</td>
                    <td>수능최저학력기준 4개 영역 중 3개 영역 등급 합이 7 이내</td>
                </tr>
            </table>
        </section>
        """

        rules = parse_csat_minimum_rules(html, 2027)
        normalized = [
            rule
            for rule in (normalize_safe_csat_minimum_rule(item) for item in rules)
            if rule is not None
        ]

        self.assertEqual(len(normalized), 1)
        self.assertIn("지역균형전형", normalized[0].selection_name)