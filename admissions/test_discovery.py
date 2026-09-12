from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase, override_settings
from django.urls import reverse

from universities.models import University
from .models import AdmissionMetric, AdmissionResult, AdmissionSource, RecruitmentUnit


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AdmissionsDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = University.objects.create(name="테스트 가온대학교", region="서울")
        cls.unit = RecruitmentUnit.objects.create(university=cls.university, name="컴퓨터공학과")
        cls.source = AdmissionSource.objects.create(
            university=cls.university, admission_year=2026, source_type="ADIGA",
            source_url="https://example.com/admissions",
        )
        cls.result = cls.add_result(cls.unit, cls.source, "3.4")

    @classmethod
    def add_result(cls, unit, source, cut, code="STUDENT_GRADE_70_CUT", **kwargs):
        result = AdmissionResult.objects.create(
            university=cls.university, recruitment_unit=unit, source=source,
            admission_year=source.admission_year, admission_phase="SUSI",
            selection_category="학생부교과", selection_name="일반전형", **kwargs,
        )
        AdmissionMetric.objects.create(result=result, metric_code=code, value=Decimal(cut), unit="등급")
        return result

    def test_home_prioritizes_search_and_exposes_comparison_without_javascript(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertLess(html.index('id="admission-explorer"'), html.index('class="representative-section"'))
        self.assertContains(response, 'action="/admissions/compare/"')
        self.assertContains(response, 'name="grade"')
        self.assertContains(response, self.unit.name)
        self.assertContains(response, 'data-filter="track"')

    def test_filter_links_preserve_query_and_reset_pagination(self):
        response = self.client.get(reverse("home"), {"q": "컴퓨터", "kind": "four", "page": 2})
        phase_group = next(g for g in response.context["filter_groups"] if g["name"] == "phase")
        params = parse_qs(urlsplit(phase_group["options"][1]["url"]).query)
        self.assertEqual(params["q"], ["컴퓨터"])
        self.assertEqual(params["kind"], ["four"])
        self.assertEqual(params["phase"], ["SUSI"])
        self.assertNotIn("page", params)

    def test_changing_phase_clears_incompatible_track_in_native_links(self):
        response = self.client.get(reverse("home"), {"track": "student"})
        group = next(g for g in response.context["filter_groups"] if g["name"] == "phase")
        for value in ("", "JEONGSI"):
            option = next(o for o in group["options"] if o["value"] == value)
            self.assertNotIn("track", parse_qs(urlsplit(option["url"]).query))

    def test_selecting_track_updates_phase_in_native_link(self):
        response = self.client.get(reverse("home"), {"phase": "JEONGSI"})
        group = next(g for g in response.context["filter_groups"] if g["name"] == "track")
        option = next(o for o in group["options"] if o["value"] == "student")
        self.assertEqual(parse_qs(urlsplit(option["url"]).query)["phase"], ["SUSI"])

    def test_partial_returns_canonical_filters_and_actual_page(self):
        response = self.client.get(reverse("admissions:overview_results"), {
            "q": "컴퓨터", "track": "student", "year": "invalid", "page": 999,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-year="2026"')
        self.assertContains(response, 'data-page="1"')
        self.assertContains(response, 'data-phase="SUSI"')
        self.assertContains(response, 'data-count="1"')
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_query_is_escaped_in_partial_metadata(self):
        response = self.client.get(reverse("admissions:overview_results"), {"q": '\"><script>alert(1)</script>'})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")
        self.assertContains(response, "data-reset-search")

    def test_full_and_partial_search_have_same_results(self):
        params = {"q": "컴퓨터", "kind": "four", "phase": "SUSI", "track": "student"}
        full = self.client.get(reverse("home"), params)
        partial = self.client.get(reverse("admissions:overview_results"), params)
        self.assertEqual(full.context["recent_results"], partial.context["recent_results"])

    def test_non_finite_or_invalid_grades_show_error_instead_of_500(self):
        for grade in ("NaN", "sNaN", "Infinity", "-Infinity", "1e999999", "0.9", "9.01", "text"):
            with self.subTest(grade=grade):
                response = self.client.get(reverse("admissions:compare"), {"grade": grade})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["grade_error"])
                self.assertContains(response, 'aria-invalid="true"')

    def test_university_source_wins_before_nearby_range_filter(self):
        official = AdmissionSource.objects.create(
            university=self.university, admission_year=2026, source_type="UNIVERSITY",
            source_url="https://example.com/official",
        )
        self.add_result(self.unit, official, "2.0")
        response = self.client.get(reverse("admissions:compare"), {"grade": "3.5"})
        self.assertEqual(response.context["filtered_count"], 0)
        response = self.client.get(reverse("admissions:compare"), {"grade": "3.5", "scope": "all"})
        self.assertEqual(response.context["filtered_count"], 1)
        self.assertEqual(response.context["rows"][0]["source_type"], "UNIVERSITY")
        self.assertEqual(response.context["rows"][0]["reference_cut"], Decimal("2.0"))

    def test_chart_does_not_average_50_and_70_percent_cutoffs_together(self):
        other_unit = RecruitmentUnit.objects.create(university=self.university, name="기계공학과")
        self.add_result(other_unit, self.source, "3.0", code="STUDENT_GRADE_50_CUT")
        response = self.client.get(reverse("admissions:compare"), {"grade": "3.5"})
        self.assertEqual(response.context["filtered_count"], 2)
        chart = response.context["chart_rows"][0]
        self.assertEqual(chart["average_cut"], Decimal("3.4"))
        self.assertEqual(chart["result_count"], 1)
        self.assertEqual(chart["reference_label"], "70% 컷")
        self.assertContains(response, "50% 컷 기준")

    def test_chart_falls_back_to_50_percent_with_explicit_label(self):
        AdmissionMetric.objects.filter(result=self.result).update(metric_code="STUDENT_GRADE_50_CUT")
        response = self.client.get(reverse("admissions:compare"), {"grade": "3.5"})
        self.assertEqual(response.context["chart_rows"][0]["reference_label"], "50% 컷")
        self.assertContains(response, "50% 컷 평균")

    def test_exact_nearby_boundaries_are_included(self):
        for cut in ("3.0", "4.0"):
            with self.subTest(cut=cut):
                AdmissionMetric.objects.filter(result=self.result).update(value=cut)
                response = self.client.get(reverse("admissions:compare"), {"grade": "3.5"})
                self.assertEqual(response.context["filtered_count"], 1)

    def test_empty_database_shows_user_facing_next_step(self):
        AdmissionResult.objects.all().delete()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "입시 데이터를 준비하고 있어요.")
        self.assertContains(response, "대학 둘러보기")
