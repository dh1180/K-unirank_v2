from django.test import RequestFactory, TestCase

from universities.models import University

from .models import RankingBoard, UniversityRating, VoteSession
from .services import build_personal_result, record_vote


class VotingTests(TestCase):
    def setUp(self):
        self.board = RankingBoard.objects.create(slug="overall", name="종합")
        self.a = University.objects.create(name="A대학교")
        self.b = University.objects.create(name="B대학교")
        self.session = VoteSession.objects.create(session_key="test")

    def test_vote_updates_both_ratings(self):
        record_vote(self.board, self.session, self.a, self.b, selected_university=self.a)
        a_rating = UniversityRating.objects.get(board=self.board, university=self.a)
        b_rating = UniversityRating.objects.get(board=self.board, university=self.b)
        self.assertGreater(a_rating.rating, 1500)
        self.assertLess(b_rating.rating, 1500)
        self.assertEqual(a_rating.win_count, 1)
        self.assertEqual(b_rating.loss_count, 1)

    def test_skip_does_not_create_rating(self):
        record_vote(self.board, self.session, self.a, self.b, skipped=True)
        self.assertEqual(UniversityRating.objects.count(), 0)

    def test_personal_result(self):
        record_vote(self.board, self.session, self.a, self.b, selected_university=self.a)
        result = build_personal_result(self.session, self.board)
        self.assertEqual(result.result_json["top10"][0]["name"], "A대학교")
