from django.test import SimpleTestCase

from admissions.services.adiga import (
    parse_admission_results,
    parse_university_detail,
    parse_university_entries,
)


class AdigaParserTests(SimpleTestCase):
    def test_list_parser_uses_explicit_university_code(self):
        html = """
        <div data-id="1234567">가야대학교 [본교]</div>
        <a href="/ucp/uvt/uni/univDetailSelection.do?unvCd=0000078">
            국민대학교 [본교]
        </a>
        """
        entries = parse_university_entries(html)

        self.assertEqual([entry.code for entry in entries], ["0000078"])
        self.assertEqual(entries[0].name, "국민대학교")

    def test_detail_parser_reads_name_and_address(self):
        html = """
        <html><body>
        <h4>단국대학교</h4>
        <ul>
            <li>주소 경기도 용인시 수지구 죽전로 152</li>
            <li>전화 031-000-0000</li>
        </ul>
        </body></html>
        """
        detail = parse_university_detail(html, "0000123")

        self.assertIsNotNone(detail)
        self.assertEqual(detail.name, "단국대학교")
        self.assertTrue(detail.address.startswith("경기도 용인시"))

    def test_result_parser_ignores_current_year_non_result_table(self):
        html = """
        <div>Q 1. 2026학년도 전형별 주요사항</div>
        <table>
            <tr><th>모집단위</th><th>모집인원</th><th>경쟁률</th></tr>
            <tr><td>가짜학과</td><td>10</td><td>2.0</td></tr>
        </table>

        <div>Ⅲ [수시] 학생부교과전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th>모집단위</th><th>학생부교과전형</th></tr>
            <tr>
                <th>모집인원</th><th>경쟁률</th><th>충원 합격 순위</th>
                <th>최종등록자 교과성적 학생부등급 50% cut</th>
                <th>최종등록자 교과성적 학생부등급 70% cut</th>
            </tr>
            <tr><td>컴퓨터공학과</td><td>10</td><td>5.5 : 1</td><td>2</td><td>2.1</td><td>2.4</td></tr>
        </table>
        """
        rows = parse_admission_results(html, 2025)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].recruitment_unit, "컴퓨터공학과")
        self.assertEqual(str(rows[0].competition_rate), "5.5")
        self.assertEqual(str(rows[0].metrics["STUDENT_GRADE_70_CUT"]), "2.4")

    def test_korea_university_comprehensive_is_not_misclassified_as_coursework(self):
        html = """
        <div>Ⅱ [수시] 학생부종합전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th rowspan="3">모집단위</th><th colspan="6">계열적합</th></tr>
            <tr>
                <th rowspan="2">모집인원</th><th rowspan="2">경쟁률</th>
                <th rowspan="2">충원 합격 순위</th>
                <th colspan="2">최종등록자 교과성적 학생부등급</th>
                <th rowspan="2">평가에 반영된 교과목</th>
            </tr>
            <tr><th>50% cut</th><th>70% cut</th></tr>
            <tr><td>수학과</td><td>6</td><td>15.67</td><td>18</td><td>3.09</td><td>4.06</td><td>전체교과</td></tr>
            <tr><td>철학과</td><td>3</td><td>27.00</td><td></td><td></td><td></td><td>전체교과</td></tr>
        </table>
        """
        rows = parse_admission_results(html, 2025)

        math = next(row for row in rows if row.recruitment_unit == "수학과")
        philosophy = next(row for row in rows if row.recruitment_unit == "철학과")

        self.assertEqual(math.selection_category, "학생부종합")
        self.assertEqual(math.selection_name, "계열적합")
        self.assertEqual(math.recruitment_count, 6)
        self.assertEqual(str(math.competition_rate), "15.67")
        self.assertEqual(str(math.metrics["STUDENT_GRADE_70_CUT"]), "4.06")
        self.assertNotIn("STUDENT_GRADE_70_CUT", philosophy.metrics)

    def test_korea_university_school_recommendation_reads_nested_headers(self):
        html = """
        <div>Ⅲ [수시] 학생부교과전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th rowspan="3">모집단위</th><th colspan="8">학교추천전형</th></tr>
            <tr>
                <th rowspan="2">모집 인원</th><th rowspan="2">경쟁률</th>
                <th rowspan="2">충원 합격 순위</th><th colspan="3">대학별환산</th>
                <th colspan="2">최종등록자 교과성적 학생부등급</th>
            </tr>
            <tr>
                <th>최종등록자 환산점수 50% cut</th>
                <th>최종등록자 환산점수 70% cut</th>
                <th>총점(학생부)</th><th>50% cut</th><th>7 0% cut</th>
            </tr>
            <tr><td>수학과</td><td>8</td><td>8.50</td><td>20</td><td>79.38</td><td>79.36</td><td>80</td><td>1.39</td><td>1.40</td></tr>
        </table>
        """
        row = parse_admission_results(html, 2025)[0]

        self.assertEqual(row.selection_category, "학생부교과")
        self.assertEqual(row.selection_name, "학교추천전형")
        self.assertEqual(row.recruitment_count, 8)
        self.assertEqual(str(row.competition_rate), "8.50")
        self.assertEqual(str(row.metrics["CONVERTED_SCORE_70_CUT"]), "79.36")
        self.assertEqual(str(row.metrics["STUDENT_GRADE_70_CUT"]), "1.40")

    def test_kyungpook_style_table_uses_named_columns_and_85_percent_does_not_shift_70(self):
        html = """
        <div>Ⅲ [수시] 학생부교과전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <div>◇ 교과 우수자 전형 ※ 그 외 성적은 입학 홈페이지 참고</div>
        <table>
            <tr>
                <th rowspan="2">단과대학</th><th rowspan="2">모집단위</th>
                <th colspan="4">지원 및 등록 현황</th><th colspan="2">등록기준</th>
                <th colspan="2">최저기준통과</th><th colspan="5">입학자 학생부 등급</th>
            </tr>
            <tr>
                <th>모집인원</th><th>지원인원</th><th>경쟁률</th><th>입학인원</th>
                <th>추합최종번호</th><th>추합인원</th><th>인원수</th><th>실질경쟁률</th>
                <th>평균</th><th>표준편차</th><th>50%</th><th>70%</th><th>85%</th>
            </tr>
            <tr>
                <td rowspan="2">인문대학</td><td>사학과</td><td>9</td><td>86</td><td>9.6</td>
                <td>9</td><td>15</td><td>7</td><td>56</td><td>6.20</td><td>2.74</td><td>0.28</td>
                <td>2.87</td><td>2.91</td><td>2.93</td>
            </tr>
            <tr>
                <td>철학과</td><td>6</td><td>70</td><td>11.7</td><td>6</td><td>20</td><td>5</td>
                <td>43</td><td>7.20</td><td>3.14</td><td>0.31</td><td>3.01</td><td>3.31</td><td>3.52</td>
            </tr>
        </table>
        """
        row = parse_admission_results(html, 2025)[0]

        self.assertEqual(row.selection_name, "교과 우수자 전형")
        self.assertEqual(row.recruitment_count, 9)
        self.assertEqual(row.applicant_count, 86)
        self.assertEqual(row.registered_count, 9)
        self.assertEqual(str(row.competition_rate), "9.6")
        self.assertEqual(str(row.metrics["STUDENT_GRADE_50_CUT"]), "2.87")
        self.assertEqual(str(row.metrics["STUDENT_GRADE_70_CUT"]), "2.91")
        self.assertEqual(str(row.metrics["STUDENT_GRADE_85_CUT"]), "2.93")

    def test_final_recruitment_count_is_used_when_initial_and_transfer_columns_exist(self):
        html = """
        <div>Ⅲ [수시] 학생부교과전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr>
                <th rowspan="2">모집단위</th><th colspan="3">모집인원</th>
                <th rowspan="2">경쟁률</th><th colspan="2">최종등록자 교과성적 학생부등급</th>
            </tr>
            <tr><th>최초(A)</th><th>이월(B)</th><th>최종(A+B)</th><th>50% cut</th><th>70% cut</th></tr>
            <tr><td>컴퓨터공학과</td><td>10</td><td>2</td><td>12</td><td>8.5</td><td>1.9</td><td>2.1</td></tr>
        </table>
        """
        row = parse_admission_results(html, 2025)[0]
        self.assertEqual(row.recruitment_count, 12)

    def test_jeongsi_reads_group_converted_score_and_average_percentile(self):
        html = """
        <div>Ⅳ [정시] 수능위주전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr>
                <th rowspan="2">구분</th><th rowspan="2">모집단위</th>
                <th rowspan="2">모집 인원</th><th rowspan="2">경쟁률</th>
                <th rowspan="2">충원 합격 순위</th><th colspan="2">대학별 환산</th>
                <th rowspan="2">최종등록자 70% cut 평균(백분위)</th>
            </tr>
            <tr><th>최종등록자 70% cut</th><th>총점(수능)</th></tr>
            <tr><td rowspan="2">가군 일반</td><td>경영학과</td><td>16</td><td>4.3</td><td>17</td><td>696.67</td><td>1000</td><td>83.16</td></tr>
            <tr><td>회계학과</td><td>11</td><td>3.7</td><td>13</td><td>720</td><td>1000</td><td>84.00</td></tr>
        </table>
        """
        row = parse_admission_results(html, 2025)[0]

        self.assertEqual(row.admission_phase, "JEONGSI")
        self.assertEqual(row.recruitment_group, "가군")
        self.assertEqual(row.selection_name, "일반")
        self.assertEqual(str(row.metrics["CSAT_CONVERTED_SCORE_70_CUT"]), "696.67")
        self.assertEqual(str(row.metrics["CSAT_PERCENTILE_MEAN_70_CUT"]), "83.16")

    def test_invalid_grade_value_is_rejected_instead_of_silently_saved(self):
        html = """
        <div>Ⅲ [수시] 학생부교과전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th rowspan="2">모집단위</th><th rowspan="2">모집인원</th><th rowspan="2">경쟁률</th><th colspan="2">입학자 학생부 등급</th></tr>
            <tr><th>50%</th><th>70%</th></tr>
            <tr><td>철학과</td><td>3</td><td>27.00</td><td>3.00</td><td>27.00</td></tr>
        </table>
        """
        row = parse_admission_results(html, 2025)[0]

        self.assertEqual(str(row.metrics["STUDENT_GRADE_50_CUT"]), "3.00")
        self.assertNotIn("STUDENT_GRADE_70_CUT", row.metrics)

    def test_korea_aerospace_style_subject_percentiles_are_parsed_and_reference_mean_is_separate(self):
        html = """
        <div>Ⅳ [정시] 수능위주전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <div>[2025학년도] [일반학생전형]</div>
        <table>
            <tr>
                <th rowspan="4">구분</th>
                <th rowspan="4">모집단위</th>
                <th colspan="3">모집인원</th>
                <th rowspan="4">경쟁률</th>
                <th rowspan="4">충원합격순위</th>
                <th colspan="3">대학별환산점수</th>
                <th colspan="12">백분위</th>
            </tr>
            <tr>
                <th rowspan="3">최초(A)</th><th rowspan="3">이월(B)</th><th rowspan="3">최종(A+B)</th>
                <th rowspan="3">최종등록자 50% cut</th>
                <th rowspan="3">최종등록자 70% cut</th>
                <th rowspan="3">합격자 평균</th>
                <th colspan="6">최종등록자 50% 학생 성적 과목별 백분위 (영어, 한국사는 등급 표기)</th>
                <th colspan="6">최종등록자 70% 학생 성적 과목별 백분위 (영어, 한국사는 등급 표기)</th>
            </tr>
            <tr>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
            </tr>
            <tr></tr>
            <tr>
                <td>가군</td><td>공과대학</td><td>37</td><td>2</td><td>39</td><td>5.46</td><td>88</td>
                <td>630.44</td><td>628.56</td><td>631.28</td>
                <td>86.5</td><td>86.5</td><td>74.5</td><td>70.5</td><td>2.5</td><td>1.5</td>
                <td>83</td><td>86</td><td>79</td><td>72</td><td>3.5</td><td>2.5</td>
            </tr>
        </table>
        """

        row = parse_admission_results(html, 2025)[0]

        self.assertEqual(row.admission_phase, "JEONGSI")
        self.assertEqual(row.recruitment_group, "가군")
        self.assertEqual(row.recruitment_count, 39)
        self.assertEqual(str(row.competition_rate), "5.46")
        self.assertEqual(str(row.metrics["CSAT_KOREAN_PERCENTILE_70_CUT"]), "83")
        self.assertEqual(str(row.metrics["CSAT_MATH_PERCENTILE_70_CUT"]), "86")
        self.assertEqual(str(row.metrics["CSAT_INQUIRY1_PERCENTILE_70_CUT"]), "79")
        self.assertEqual(str(row.metrics["CSAT_INQUIRY2_PERCENTILE_70_CUT"]), "72")
        self.assertEqual(str(row.metrics["CSAT_ENGLISH_GRADE_70_CUT"]), "3.5")
        self.assertEqual(str(row.metrics["CSAT_KOREAN_HISTORY_GRADE_70_CUT"]), "2.5")
        self.assertNotIn("CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT", row.metrics)
        self.assertNotIn("CSAT_PERCENTILE_MEAN_70_CUT", row.metrics)

    def test_single_inquiry_percentile_is_kept_without_reference_mean(self):
        html = """
        <div>Ⅳ [정시] 수능위주전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th rowspan="2">모집단위</th><th rowspan="2">모집인원</th><th rowspan="2">경쟁률</th><th colspan="3">최종등록자 70% cut 과목별 백분위</th></tr>
            <tr><th>국어</th><th>수학</th><th>탐구</th></tr>
            <tr><td>컴퓨터학과</td><td>10</td><td>5.0</td><td>88</td><td>91</td><td>85</td></tr>
        </table>
        """

        row = parse_admission_results(html, 2025)[0]

        self.assertEqual(str(row.metrics["CSAT_INQUIRY_PERCENTILE_70_CUT"]), "85")
        self.assertNotIn("CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT", row.metrics)

    def test_tab_is_source_of_truth_even_when_selection_name_contains_other_keywords(self):
        html = """
        <div>Ⅱ-1 『2026 학년도 전형별 주요사항』</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr>
                <th rowspan="2">모집단위</th>
                <th colspan="4">교과성적우수자 전형</th>
            </tr>
            <tr>
                <th>모집인원</th><th>경쟁률</th><th>학생부등급 50% cut</th><th>학생부등급 70% cut</th>
            </tr>
            <tr><td>공과대학</td><td>25</td><td>7.16</td><td>2.30</td><td>2.50</td></tr>
        </table>
        """

        row = parse_admission_results(html, 2025)[0]
        self.assertEqual(row.admission_phase, "SUSI")
        self.assertEqual(row.selection_category, "학생부종합")
        self.assertIn("교과성적우수자", row.selection_name)

    def test_aerospace_regular_table_uses_csat_tab_as_source_of_truth(self):
        html = """
        <div>Ⅳ-1 『2026 학년도 전형별 주요사항』</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <div>[2025학년도] [일반학생전형]</div>
        <table>
            <tr>
                <th rowspan="4">구분</th>
                <th rowspan="4">모집단위</th>
                <th colspan="3">모집인원</th>
                <th rowspan="4">경쟁률</th>
                <th rowspan="4">충원합격순위</th>
                <th colspan="3">대학별환산점수</th>
                <th colspan="12">백분위</th>
                <th colspan="3">최종등록자 수학 선택 과목 응시비율(%)</th>
            </tr>
            <tr>
                <th rowspan="3">최초(A)</th><th rowspan="3">이월(B)</th><th rowspan="3">최종(A+B)</th>
                <th rowspan="3">최종등록자 50% cut</th>
                <th rowspan="3">최종등록자 70% cut</th>
                <th rowspan="3">합격자 평균</th>
                <th colspan="6">최종등록자 50% 학생 성적 과목별 백분위 (영어, 한국사는 등급 표기)</th>
                <th colspan="6">최종등록자 70% 학생 성적 과목별 백분위 (영어, 한국사는 등급 표기)</th>
                <th rowspan="3">확률과통계</th><th rowspan="3">미적분</th><th rowspan="3">기하</th>
            </tr>
            <tr>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
            </tr>
            <tr></tr>
            <tr>
                <td>가군</td><td>공과대학</td><td>37</td><td>2</td><td>39</td><td>5.46</td><td>88</td>
                <td>630.44</td><td>628.56</td><td>631.28</td>
                <td>86.5</td><td>86.5</td><td>74.5</td><td>70.5</td><td>2.5</td><td>1.5</td>
                <td>83</td><td>86</td><td>79</td><td>72</td><td>3.5</td><td>2.5</td>
                <td>0</td><td>97.5</td><td>2.5</td>
            </tr>
        </table>
        """

        row = parse_admission_results(html, 2025)[0]

        self.assertEqual(row.admission_phase, "JEONGSI")
        self.assertEqual(row.selection_category, "수능")
        self.assertEqual(row.selection_name, "일반학생전형")
        self.assertEqual(row.recruitment_group, "가군")
        self.assertEqual(row.recruitment_count, 39)
        self.assertEqual(str(row.metrics["CSAT_CONVERTED_SCORE_70_CUT"]), "628.56")
        self.assertNotIn("CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT", row.metrics)

    def test_table_without_adiga_tab_context_is_not_classified(self):
        html = """
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th>모집단위</th><th>모집인원</th><th>경쟁률</th></tr>
            <tr><td>컴퓨터공학과</td><td>10</td><td>5.0</td></tr>
        </table>
        """

        rows = parse_admission_results(html, 2025)
        self.assertEqual(rows, [])

    def test_three_adiga_tabs_keep_their_own_categories(self):
        html = """
        <div>Ⅱ-1 『2026 학년도 전형별 주요사항』</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th>모집단위</th><th>미래인재전형</th></tr>
            <tr><th>모집인원</th><th>경쟁률</th></tr>
            <tr><td>A학과</td><td>10</td><td>4.0</td></tr>
        </table>

        <div>Ⅲ-1 『2026 학년도 전형별 주요사항』</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th>모집단위</th><th>학교추천전형</th></tr>
            <tr><th>모집인원</th><th>경쟁률</th></tr>
            <tr><td>B학과</td><td>8</td><td>5.0</td></tr>
        </table>

        <div>Ⅳ-1 『2026 학년도 전형별 주요사항』</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <table>
            <tr><th>구분</th><th>모집단위</th><th>모집인원</th><th>경쟁률</th></tr>
            <tr><td>가군</td><td>C학과</td><td>7</td><td>6.0</td></tr>
        </table>
        """

        rows = parse_admission_results(html, 2025)

        by_unit = {row.recruitment_unit: row for row in rows}
        self.assertEqual(by_unit["A학과"].selection_category, "학생부종합")
        self.assertEqual(by_unit["A학과"].admission_phase, "SUSI")
        self.assertEqual(by_unit["B학과"].selection_category, "학생부교과")
        self.assertEqual(by_unit["B학과"].admission_phase, "SUSI")
        self.assertEqual(by_unit["C학과"].selection_category, "수능")
        self.assertEqual(by_unit["C학과"].admission_phase, "JEONGSI")


class AdigaSelectionNamePriorityTests(SimpleTestCase):
    def test_table_header_selection_name_has_priority_over_previous_dom_text(self):
        html = """
        <div>Ⅱ-1 『2026 학년도 전형별 주요사항』</div>
        <div>미래인재전형 고른기회전형</div>
        <div>Q 2. 2025학년도 전형 결과</div>

        <table>
            <tr>
                <th rowspan="2">모집단위</th>
                <th colspan="5">미래인재전형</th>
            </tr>
            <tr>
                <th>모집인원</th><th>경쟁률</th>
                <th>충원 합격 순위</th><th>50% cut</th><th>70% cut</th>
            </tr>
            <tr>
                <td>공과대학</td><td>43</td><td>10.23</td><td>57</td><td>3.71</td><td>3.14</td>
            </tr>
        </table>

        <div>고른기회전형</div>
        <table>
            <tr>
                <th rowspan="2">모집단위</th>
                <th colspan="5">고른기회전형</th>
            </tr>
            <tr>
                <th>모집인원</th><th>경쟁률</th>
                <th>충원 합격 순위</th><th>50% cut</th><th>70% cut</th>
            </tr>
            <tr>
                <td>공과대학</td><td>12</td><td>5.17</td><td>16</td><td>2.57</td><td>4.32</td>
            </tr>
        </table>
        """

        rows = parse_admission_results(html, 2025)
        self.assertEqual(len(rows), 2)

        by_count = {row.recruitment_count: row for row in rows}
        self.assertEqual(by_count[43].selection_name, "미래인재전형")
        self.assertEqual(by_count[12].selection_name, "고른기회전형")
        self.assertEqual(by_count[43].selection_category, "학생부종합")
        self.assertEqual(by_count[12].selection_category, "학생부종합")

    def test_external_selection_name_is_used_when_table_has_no_name(self):
        html = """
        <div>Ⅳ-1 『2026 학년도 전형별 주요사항』</div>
        <div>Q 2. 2025학년도 전형 결과</div>
        <div>[2025학년도] [일반학생전형]</div>
        <table>
            <tr>
                <th>구분</th><th>모집단위</th><th>모집인원</th><th>경쟁률</th>
            </tr>
            <tr>
                <td>가군</td><td>공과대학</td><td>39</td><td>5.46</td>
            </tr>
        </table>
        """

        row = parse_admission_results(html, 2025)[0]
        self.assertEqual(row.selection_name, "일반학생전형")
        self.assertEqual(row.admission_phase, "JEONGSI")
        self.assertEqual(row.selection_category, "수능")



class AdigaTabOrderFallbackTests(SimpleTestCase):
    def test_tab_menu_without_repeated_roman_headings_uses_q1_pane_order(self):
        html = """
        <div class="modTabWrap">
            <ul class="tabMenu">
                <li><button id="tab_10">Ⅰ. 공통</button></li>
                <li><button id="tab_20">Ⅱ. 학생부종합전형</button></li>
                <li><button id="tab_30">Ⅲ. 학생부교과전형</button></li>
                <li><button id="tab_40">Ⅳ. 수능위주전형</button></li>
            </ul>

            <div class="pane">
                <h3>Q 1. 2026학년도 전형별 주요사항</h3>
                <h3>Q 2. 2025학년도 전형 결과</h3>
                <table>
                    <tr>
                        <th rowspan="2">모집단위</th>
                        <th colspan="4">학생부종합(네오르네상스전형)</th>
                    </tr>
                    <tr>
                        <th>모집인원</th><th>경쟁률</th>
                        <th>50% cut</th><th>70% cut</th>
                    </tr>
                    <tr>
                        <td>국어국문학과</td><td>20</td><td>13.0</td>
                        <td>2.34</td><td>3.89</td>
                    </tr>
                </table>
            </div>

            <div class="pane">
                <h3>Q 1. 2026학년도 전형별 주요사항</h3>
                <h3>Q 2. 2025학년도 전형 결과</h3>
                <table>
                    <tr>
                        <th rowspan="2">모집단위</th>
                        <th colspan="4">학생부교과(지역균형전형)</th>
                    </tr>
                    <tr>
                        <th>모집인원</th><th>경쟁률</th>
                        <th>학생부등급 50% cut</th>
                        <th>학생부등급 70% cut</th>
                    </tr>
                    <tr>
                        <td>사학과</td><td>5</td><td>11.6</td>
                        <td>1.80</td><td>1.82</td>
                    </tr>
                </table>
            </div>

            <div class="pane">
                <h3>Q 1. 2026학년도 전형별 주요사항</h3>
                <h3>Q 2. 2025학년도 전형 결과</h3>
                <div>[2025학년도] [일반학생전형]</div>
                <table>
                    <tr>
                        <th>구분</th><th>모집단위</th><th>모집인원</th>
                        <th>경쟁률</th>
                        <th>대학별환산 최종등록자 70% cut</th>
                        <th>총점(수능)</th>
                        <th>최종등록자 70% cut 국어</th>
                        <th>최종등록자 70% cut 수학</th>
                        <th>최종등록자 70% cut 탐구1</th>
                        <th>최종등록자 70% cut 탐구2</th>
                        <th>최종등록자 70% cut 평균(백분위)</th>
                    </tr>
                    <tr>
                        <td>가군 일반</td><td>경영대학</td><td>84</td>
                        <td>2.85</td><td>654.12</td><td>1000</td>
                        <td>94</td><td>95</td><td>90</td><td>88</td><td>92.72</td>
                    </tr>
                </table>
            </div>
        </div>
        """

        rows = parse_admission_results(html, 2025)
        by_unit = {row.recruitment_unit: row for row in rows}

        self.assertEqual(
            by_unit["국어국문학과"].selection_category,
            "학생부종합",
        )
        self.assertEqual(
            by_unit["사학과"].selection_category,
            "학생부교과",
        )
        self.assertEqual(
            str(by_unit["사학과"].metrics["STUDENT_GRADE_70_CUT"]),
            "1.82",
        )
        self.assertEqual(
            by_unit["경영대학"].admission_phase,
            "JEONGSI",
        )
        self.assertEqual(
            by_unit["경영대학"].selection_category,
            "수능",
        )
        self.assertEqual(
            str(
                by_unit["경영대학"].metrics[
                    "CSAT_PERCENTILE_MEAN_70_CUT"
                ]
            ),
            "92.72",
        )



class AdigaSkkuSogangRegressionTests(SimpleTestCase):
    def test_skku_three_tabs_and_bare_group_are_parsed(self):
        html = """
        <div>Ⅱ-2 『2025 학년도 전형 결과』</div>
        <table>
            <tr>
                <th rowspan="2">모집단위</th>
                <th colspan="5">학생부종합(융합형)</th>
            </tr>
            <tr>
                <th>모집인원</th><th>경쟁률</th><th>충원 합격 순위</th>
                <th>50% cut</th><th>70% cut</th>
            </tr>
            <tr>
                <td>경영학과</td><td>53</td><td>15.26</td><td>119</td>
                <td>2.81</td><td>3.08</td>
            </tr>
        </table>

        <div>Ⅲ-2 『2025 학년도 전형 결과』</div>
        <table>
            <tr>
                <th rowspan="2">모집단위</th>
                <th colspan="7">학생부교과(학교장추천)</th>
            </tr>
            <tr>
                <th>모집인원</th><th>경쟁률</th><th>충원 합격 순위</th>
                <th>대학별 환산 50% cut</th>
                <th>대학별 환산 70% cut</th>
                <th>학생부 교과성적 50% cut</th>
                <th>학생부 교과성적 70% cut</th>
            </tr>
            <tr>
                <td>건축학과(5년제)</td><td>18</td><td>8.61</td><td>22</td>
                <td>98.6</td><td>98.56</td><td>1.78</td><td>1.79</td>
            </tr>
        </table>

        <div>Ⅳ-2 『2025 학년도 전형 결과』</div>
        <div>[2025 학년도]</div>
        <table>
            <tr>
                <th rowspan="4">구분</th>
                <th rowspan="4">모집단위</th>
                <th colspan="3">모집인원</th>
                <th rowspan="4">경쟁률</th>
                <th rowspan="4">충원 합격 순위</th>
                <th colspan="3">대학별 환산점수</th>
                <th colspan="12">백분위</th>
            </tr>
            <tr>
                <th rowspan="3">최초(A)</th>
                <th rowspan="3">이월(B)</th>
                <th rowspan="3">최종(A+B)</th>
                <th rowspan="3">최종 등록자 50% cut</th>
                <th rowspan="3">최종 등록자 70% cut</th>
                <th rowspan="3">총점(수능)</th>
                <th colspan="6">최종등록자 50% 학생 성적 과목별 백분위</th>
                <th colspan="6">최종등록자 70% 학생 성적 과목별 백분위</th>
            </tr>
            <tr>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
            </tr>
            <tr></tr>
            <tr>
                <td>가</td><td>교육학과</td>
                <td>15</td><td>0</td><td>15</td><td>3.33</td><td>6</td>
                <td>644.83</td><td>644.15</td><td>1000</td>
                <td>98</td><td>92</td><td>88</td><td>91</td><td>3</td><td>2</td>
                <td>98</td><td>78</td><td>88</td><td>99</td><td>2</td><td>1</td>
            </tr>
        </table>
        """

        rows = parse_admission_results(html, 2025)
        by_unit = {row.recruitment_unit: row for row in rows}

        self.assertEqual(
            by_unit["경영학과"].selection_category,
            "학생부종합",
        )
        self.assertEqual(
            by_unit["경영학과"].selection_name,
            "학생부종합(융합형)",
        )

        self.assertEqual(
            by_unit["건축학과(5년제)"].selection_category,
            "학생부교과",
        )
        self.assertEqual(
            str(
                by_unit["건축학과(5년제)"].metrics[
                    "STUDENT_GRADE_70_CUT"
                ]
            ),
            "1.79",
        )

        jeongsi = by_unit["교육학과"]
        self.assertEqual(jeongsi.admission_phase, "JEONGSI")
        self.assertEqual(jeongsi.selection_category, "수능")
        self.assertEqual(jeongsi.recruitment_group, "가군")
        self.assertEqual(jeongsi.selection_name, "일반")
        self.assertEqual(jeongsi.recruitment_count, 15)
        self.assertEqual(
            str(jeongsi.metrics["CSAT_CONVERTED_SCORE_70_CUT"]),
            "644.15",
        )
        self.assertEqual(
            str(jeongsi.metrics["CSAT_KOREAN_PERCENTILE_70_CUT"]),
            "98",
        )
        self.assertEqual(
            str(jeongsi.metrics["CSAT_MATH_PERCENTILE_70_CUT"]),
            "78",
        )

    def test_sogang_group_carries_selection_name_and_subject_percentiles(self):
        html = """
        <div>Ⅳ-2 『2025 학년도 전형 결과』</div>
        <table>
            <tr>
                <th rowspan="4">구분</th>
                <th rowspan="4">모집 단위</th>
                <th colspan="3">모집인원</th>
                <th rowspan="4">경쟁률</th>
                <th rowspan="4">충원합격순위</th>
                <th colspan="3">대학별 환산점수</th>
                <th colspan="12">백분위</th>
            </tr>
            <tr>
                <th rowspan="3">최초(A)</th>
                <th rowspan="3">이월(B)</th>
                <th rowspan="3">최종(A+B)</th>
                <th rowspan="3">최종 등록자 50% cut</th>
                <th rowspan="3">최종 등록자 70% cut</th>
                <th rowspan="3">총점(수능)</th>
                <th colspan="6">최종등록자 50% 학생 성적 과목별 백분위</th>
                <th colspan="6">최종등록자 70% 학생 성적 과목별 백분위</th>
            </tr>
            <tr>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
                <th>국</th><th>수</th><th>탐1</th><th>탐2</th><th>영</th><th>한</th>
            </tr>
            <tr></tr>
            <tr>
                <td>나군 일반</td><td>인공지능학과</td>
                <td>10</td><td>0</td><td>10</td><td>7.70</td><td>10</td>
                <td>500.42</td><td>499.69</td><td>529.36</td>
                <td>88</td><td>98</td><td>99</td><td>88</td><td>3</td><td>1</td>
                <td>98</td><td>93</td><td>81</td><td>98</td><td>3</td><td>1</td>
            </tr>
        </table>
        """

        row = parse_admission_results(html, 2025)[0]
        self.assertEqual(row.admission_phase, "JEONGSI")
        self.assertEqual(row.recruitment_group, "나군")
        self.assertEqual(row.selection_name, "일반")
        self.assertEqual(
            str(row.metrics["CSAT_CONVERTED_SCORE_70_CUT"]),
            "499.69",
        )
        self.assertNotIn(
            "CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT",
            row.metrics,
        )



class AdigaLatestDynamicResultTests(SimpleTestCase):
    def test_latest_result_heading_is_detected_without_table(self):
        html = """
        <div>2027학년도 전형평가기준 및 결과공개 자료입니다.</div>
        <button>Q 2026학년도 전형 결과</button>
        """

        self.assertTrue(has_result_section(html, 2026))
        self.assertFalse(has_result_section(html, 2025))

    def test_browser_rendered_sections_are_parsed_by_tab_id(self):
        html = """
        <!-- KUNIRANK_BROWSER_RENDERED -->
        <section id="tab_20">
            <div>Q 2026학년도 전형 결과</div>
            <table>
                <tr>
                    <th rowspan="2">모집단위</th>
                    <th colspan="4">미래인재전형</th>
                </tr>
                <tr>
                    <th>모집인원</th><th>경쟁률</th>
                    <th>50% cut</th><th>70% cut</th>
                </tr>
                <tr>
                    <td>공과대학</td><td>40</td><td>9.1</td>
                    <td>2.9</td><td>3.1</td>
                </tr>
            </table>
        </section>

        <section id="tab_30">
            <div>Q 2026학년도 전형 결과</div>
            <table>
                <tr>
                    <th rowspan="2">모집단위</th>
                    <th colspan="4">교과성적우수자전형</th>
                </tr>
                <tr>
                    <th>모집인원</th><th>경쟁률</th>
                    <th>학생부등급 50% cut</th>
                    <th>학생부등급 70% cut</th>
                </tr>
                <tr>
                    <td>AI융합대학</td><td>25</td><td>6.2</td>
                    <td>2.1</td><td>2.3</td>
                </tr>
            </table>
        </section>

        <section id="tab_40">
            <div>Q 2026학년도 전형 결과</div>
            <div>[2026학년도] [일반학생전형]</div>
            <table>
                <tr>
                    <th>구분</th><th>모집단위</th>
                    <th>모집인원</th><th>경쟁률</th>
                    <th>최종등록자 70% cut 국어</th>
                    <th>최종등록자 70% cut 수학</th>
                    <th>최종등록자 70% cut 탐구1</th>
                    <th>최종등록자 70% cut 탐구2</th>
                </tr>
                <tr>
                    <td>가군</td><td>항공운항학과</td>
                    <td>10</td><td>8.5</td>
                    <td>93</td><td>95</td><td>90</td><td>88</td>
                </tr>
            </table>
        </section>
        """

        rows = parse_admission_results(html, 2026)
        by_unit = {row.recruitment_unit: row for row in rows}

        self.assertEqual(
            by_unit["공과대학"].selection_category,
            "학생부종합",
        )
        self.assertEqual(
            by_unit["AI융합대학"].selection_category,
            "학생부교과",
        )
        self.assertEqual(
            by_unit["항공운항학과"].admission_phase,
            "JEONGSI",
        )



class AdigaRenderedResultOnlyRegressionTests(SimpleTestCase):
    def test_q1_like_table_is_not_a_valid_admission_result_table(self):
        html = """
        <section id="tab_20">
            <div>Q 2026학년도 전형 결과</div>

            <table>
                <tr>
                    <th>모집단위</th>
                    <th>학생부 반영교과</th>
                </tr>
                <tr>
                    <td>공과대학</td>
                    <td>국어 영어 수학 과학</td>
                </tr>
            </table>

            <table>
                <tr>
                    <th>모집단위</th>
                    <th>모집인원</th>
                    <th>경쟁률</th>
                    <th>학생부등급 70% cut</th>
                </tr>
                <tr>
                    <td>공과대학</td>
                    <td>40</td>
                    <td>9.1</td>
                    <td>3.10</td>
                </tr>
            </table>
        </section>
        """

        rows = parse_admission_results(html, 2026)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].recruitment_count, 40)
        self.assertEqual(str(rows[0].competition_rate), "9.1")



class AdigaLatestCommonDomTests(SimpleTestCase):
    def test_tb_adm_res_title_and_final_recruitment_count(self):
        html = """
        <section id="tab_20">
            <div>Q 2026학년도 전형 결과</div>

            <div class="tbAdmRes">
                <div class="tblBase">
                    <h5 class="tit h5">
                        학생부 종합 (미래인재 전형)
                    </h5>
                </div>

                <table class="tblBase">
                    <thead>
                        <tr>
                            <th rowspan="2">구분</th>
                            <th rowspan="2">모집단위</th>
                            <th colspan="3">모집인원</th>
                            <th rowspan="2">경쟁률</th>
                            <th rowspan="2">충원인원</th>
                            <th colspan="2">학생부</th>
                        </tr>
                        <tr>
                            <th>최초(A)</th>
                            <th>이월(B)</th>
                            <th>최종(A+B)</th>
                            <th>50% cut</th>
                            <th>70% cut</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>수시</td>
                            <td>공과대학</td>
                            <td>0</td>
                            <td>0</td>
                            <td>43</td>
                            <td>10.23</td>
                            <td>20</td>
                            <td>2.81</td>
                            <td>3.14</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>
        """

        row = parse_admission_results(html, 2026)[0]

        self.assertEqual(row.selection_name, "미래인재 전형")
        self.assertEqual(row.recruitment_count, 43)
        self.assertEqual(str(row.competition_rate), "10.23")
        self.assertEqual(
            str(row.metrics["STUDENT_GRADE_70_CUT"]),
            "3.14",
        )

    def test_tb_adm_res_coursework_title(self):
        html = """
        <section id="tab_30">
            <div>Q 2026학년도 전형 결과</div>

            <div class="tbAdmRes">
                <div class="tblBase">
                    <h5 class="tit h5">
                        학생부 교과 (교과성적우수자 전형)
                    </h5>
                </div>

                <table class="tblBase">
                    <tr>
                        <th>구분</th>
                        <th>모집단위</th>
                        <th>모집인원</th>
                        <th>경쟁률</th>
                        <th>학생부 등급 70% cut</th>
                    </tr>
                    <tr>
                        <td>수시</td>
                        <td>AI융합대학</td>
                        <td>20</td>
                        <td>8.5</td>
                        <td>2.14</td>
                    </tr>
                </table>
            </div>
        </section>
        """

        row = parse_admission_results(html, 2026)[0]

        self.assertEqual(
            row.selection_name,
            "교과성적우수자 전형",
        )
        self.assertEqual(
            row.selection_category,
            "학생부교과",
        )

class AdigaFutureCampusRegressionTests(SimpleTestCase):
    def test_csat_detail_keeps_only_official_subject_metrics(self):
        html = """
        <section id="tab_40">
          <div>Q 2026학년도 전형 결과</div>
          <div class="tbAdmRes">
            <h5 class="tit h5">수능(일반전형)</h5>
            <table>
              <tr>
                <th rowspan="3">구분</th><th rowspan="3">모집단위</th>
                <th colspan="3">모집인원</th><th rowspan="3">경쟁률</th>
                <th rowspan="3">충원인원</th><th colspan="2">환산점수</th>
                <th colspan="8">백분위 50%</th><th colspan="8">백분위 70%</th>
              </tr>
              <tr>
                <th rowspan="2">최초(A)</th><th rowspan="2">이월(B)</th><th rowspan="2">최종(A)+(B)</th>
                <th rowspan="2">50%</th><th rowspan="2">70%</th>
                <th rowspan="2">국어</th><th rowspan="2">수학</th><th colspan="3">탐구1</th>
                <th rowspan="2">평균백분위</th><th rowspan="2">한국사(등급)</th><th rowspan="2">영어등급</th>
                <th rowspan="2">국어</th><th rowspan="2">수학</th><th colspan="3">탐구1</th>
                <th rowspan="2">평균백분위</th><th rowspan="2">한국사(등급)</th><th rowspan="2">영어등급</th>
              </tr>
              <tr><th>사탐</th><th>과탐</th><th>직탐</th><th>사탐</th><th>과탐</th><th>직탐</th></tr>
              <tr>
                <td>정시(가)</td><td>데이터사이언스학부</td><td>13</td><td>0</td><td>13</td><td>10.15</td><td>23</td>
                <td>627.5</td><td>623.6</td>
                <td>72</td><td>81</td><td>75</td><td>-</td><td>-</td><td>76</td><td>3</td><td>3</td>
                <td>67</td><td>69</td><td>66</td><td>-</td><td>-</td><td>67</td><td>3</td><td>4</td>
              </tr>
            </table>
          </div>
        </section>
        """
        row = parse_admission_results(html, 2026)[0]
        self.assertEqual(row.admission_phase, "JEONGSI")
        self.assertEqual(row.selection_category, "수능")
        self.assertEqual(row.selection_name, "일반전형")
        self.assertEqual(row.recruitment_group, "가군")
        self.assertEqual(str(row.metrics["CSAT_PERCENTILE_MEAN_70_CUT"]), "67")
        self.assertEqual(str(row.metrics["CSAT_KOREAN_HISTORY_GRADE_70_CUT"]), "3")
        self.assertEqual(str(row.metrics["CSAT_ENGLISH_GRADE_70_CUT"]), "4")
        self.assertNotIn("STUDENT_GRADE_70_CUT", row.metrics)
        self.assertNotIn("CSAT_PERCENTILE_REFERENCE_MEAN_50_CUT", row.metrics)
        self.assertNotIn("CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT", row.metrics)

    def test_school_life_result_miswrapped_as_jeongsi_is_corrected_to_jonghap(self):
        html = """
        <section id="tab_40">
          <div>Q 2026학년도 전형 결과</div>
          <div class="tbAdmRes">
            <h5 class="tit h5">학교생활우수자전형</h5>
            <table>
              <tr>
                <th rowspan="2">모집단위</th>
                <th rowspan="2">모집 인원</th>
                <th rowspan="2">경쟁률</th>
                <th colspan="2">최종등록자 교과성적 학생부등급</th>
              </tr>
              <tr><th>50% cut</th><th>70% cut</th></tr>
              <tr><td>의예과</td><td>15</td><td>22.93</td><td>1.42</td><td>1.46</td></tr>
            </table>
          </div>
        </section>
        """
        row = parse_admission_results(html, 2026)[0]
        self.assertEqual(row.admission_phase, "SUSI")
        self.assertEqual(row.selection_category, "학생부종합")
        self.assertEqual(row.selection_name, "학교생활우수자전형")
        self.assertEqual(str(row.metrics["STUDENT_GRADE_70_CUT"]), "1.46")


class AdigaMiraeJeongsiSummaryRegressionTests(SimpleTestCase):
    def test_grouped_csat_summary_miswrapped_as_jonghap_is_forced_to_jeongsi(self):
        html = """
        <section id="tab_20">
          <div>Q 2026학년도 전형 결과</div>
          <div>디자인예술학부 실기전형</div>
          <table>
            <tr>
              <th>구분</th><th>모집단위</th><th>모집 인원</th>
              <th>경쟁률</th><th colspan="2">대학별 환산점수</th>
            </tr>
            <tr><th></th><th></th><th></th><th></th><th>50%</th><th>70%</th></tr>
            <tr><td>가군</td><td>데이터사이언스학부</td><td>19</td><td>6.95</td><td>627.50</td><td>623.60</td></tr>
            <tr><td>가군</td><td>소프트웨어학부</td><td>39</td><td>3.38</td><td>624.05</td><td>620.78</td></tr>
          </table>
        </section>
        """

        rows = parse_admission_results(html, 2026)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row.admission_phase, "JEONGSI")
            self.assertEqual(row.selection_category, "수능")
            self.assertEqual(row.recruitment_group, "가군")
            self.assertEqual(row.selection_name, "")
            self.assertIn("CSAT_CONVERTED_SCORE_70_CUT", row.metrics)
            self.assertNotIn("CONVERTED_SCORE_70_CUT", row.metrics)

    def test_nearest_title_inside_one_result_block_is_used_per_table(self):
        html = """
        <section id="tab_40">
          <div>Q 2026학년도 전형 결과</div>
          <div class="tbAdmRes">
            <h5 class="tit h5">학생부 종합 (학교생활우수자전형)</h5>
            <table>
              <tr><th>모집단위</th><th>모집인원</th><th>경쟁률</th><th>학생부등급 70% cut</th></tr>
              <tr><td>의예과</td><td>15</td><td>22.93</td><td>1.46</td></tr>
            </table>

            <h5 class="tit h5">수능(일반전형)</h5>
            <table>
              <tr><th>구분</th><th>모집단위</th><th>모집인원</th><th>경쟁률</th><th>환산점수 70%</th><th>백분위 70% 평균백분위</th></tr>
              <tr><td>가군</td><td>데이터사이언스학부</td><td>19</td><td>6.95</td><td>623.60</td><td>67</td></tr>
            </table>
          </div>
        </section>
        """

        rows = parse_admission_results(html, 2026)
        by_unit = {row.recruitment_unit: row for row in rows}

        self.assertEqual(by_unit["의예과"].admission_phase, "SUSI")
        self.assertEqual(by_unit["의예과"].selection_category, "학생부종합")
        self.assertEqual(by_unit["의예과"].selection_name, "학교생활우수자전형")

        self.assertEqual(by_unit["데이터사이언스학부"].admission_phase, "JEONGSI")
        self.assertEqual(by_unit["데이터사이언스학부"].selection_category, "수능")
        self.assertEqual(by_unit["데이터사이언스학부"].selection_name, "일반전형")
        self.assertEqual(by_unit["데이터사이언스학부"].recruitment_group, "가군")
