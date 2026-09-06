import json

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from admissions.models import AdmissionResult
from universities.models import University, UniversityIndicator
from universities.services.indicators import CORE_UNIVERSITY_INDICATORS

from .admission_hover import attach_admission_hover, build_admission_hover
from .baseline import ranking_university_queryset
from .models import ComparisonVote, PersonalResult, RankingBoard, RankingSnapshot, UniversityRating
from .services import build_personal_result, ensure_default_boards, get_vote_session, record_vote, select_pair


def _active_board(slug):
    ensure_default_boards()
    return get_object_or_404(RankingBoard, slug=slug, is_active=True)


def ranking_hub(request):
    indicator_codes = [item["code"] for item in CORE_UNIVERSITY_INDICATORS]
    summaries = (
        UniversityIndicator.objects.filter(
            indicator_code__in=indicator_codes,
            source="ACADEMYINFO",
            university__is_active=True,
            value__gt=0,
        )
        .values("indicator_code", "year")
        .annotate(university_count=Count("university_id", distinct=True))
        .order_by("indicator_code", "-year")
    )

    latest_by_code = {}
    for row in summaries:
        latest_by_code.setdefault(row["indicator_code"], row)

    indicator_cards = []
    for spec in CORE_UNIVERSITY_INDICATORS:
        summary = latest_by_code.get(spec["code"])
        indicator_cards.append(
            {
                **spec,
                "year": summary["year"] if summary else None,
                "university_count": summary["university_count"] if summary else 0,
            }
        )

    return render(
        request,
        "rankings/ranking_hub.html",
        {
            "indicator_cards": indicator_cards,
        },
    )


def home(request):
    boards = ensure_default_boards()
    overall = next((board for board in boards if board.slug == "overall"), boards[0])
    eligible_ids = ranking_university_queryset().values_list("university_id", flat=True)

    top_ratings = list(
        UniversityRating.objects.filter(
            board=overall,
            university_id__in=eligible_ids,
            match_count__gte=0,
        )
        .select_related("university", "board")
        .order_by("-rating", "university__name")[:10]
    )

    total_match_count = (
        UniversityRating.objects
        .filter(board=overall)
        .aggregate(total=Sum("match_count"))["total"]
        or 0
    )

    total_votes = total_match_count // 2
    university_count = ranking_university_queryset().count()
    admission_coverage = AdmissionResult.objects.values("university_id").distinct().count()

    return render(
        request,
        "rankings/home.html",
        {
            "boards": boards,
            "overall": overall,
            "top_ratings": top_ratings,
            "total_votes": total_votes,
            "university_count": university_count,
            "admission_coverage": admission_coverage,
        },
    )


def vote_page(request, slug="overall"):
    board = _active_board(slug)
    vote_session = get_vote_session(request)
    pair = select_pair(board, vote_session)
    if pair:
        attach_admission_hover(pair)

    return render(
        request,
        "rankings/vote.html",
        {
            "board": board,
            "pair": pair,
            "vote_session": vote_session,
            "personal_result_ready": vote_session.votes.filter(board=board, skipped=False).count() >= 20,
        },
    )


@require_POST
def submit_vote(request, slug):
    board = _active_board(slug)
    vote_session = get_vote_session(request)

    try:
        university_a = University.objects.get(pk=int(request.POST.get("university_a")))
        university_b = University.objects.get(pk=int(request.POST.get("university_b")))
    except (TypeError, ValueError, University.DoesNotExist):
        messages.error(request, "비교 대학 정보를 다시 확인해주세요.")
        return redirect("rankings:vote", slug=board.slug)

    action = request.POST.get("action", "")

    if action == "skip":
        record_vote(board, vote_session, university_a, university_b, skipped=True)
    else:
        try:
            selected_id = int(action)
            selected = University.objects.get(pk=selected_id)
            record_vote(board, vote_session, university_a, university_b, selected_university=selected)
        except (TypeError, ValueError, University.DoesNotExist):
            messages.error(request, "선택한 대학을 확인해주세요.")

    return redirect("rankings:vote", slug=board.slug)


def ranking_page(request, slug="overall"):
    board = _active_board(slug)
    min_matches = max(0, int(request.GET.get("min_matches", 0)))

    eligible_ids = ranking_university_queryset().values_list("university_id", flat=True)
    ratings = list(
        UniversityRating.objects.filter(
            board=board,
            university_id__in=eligible_ids,
            match_count__gte=min_matches,
        )
        .select_related("university", "board")
        .order_by("-rating", "university__name")
    )

    previous_rank = {}
    snapshots = list(RankingSnapshot.objects.filter(board=board).order_by("-snapshot_date")[:2])
    if len(snapshots) >= 2:
        previous_rank = {
            item.university_id: item.rank
            for item in snapshots[1].items.all()
        }

    rows = []
    for rank, rating in enumerate(ratings, start=1):
        old_rank = previous_rank.get(rating.university_id)
        change = old_rank - rank if old_rank else None
        rows.append({
            "rank": rank,
            "rating": rating,
            "change": change,
        })

    return render(request, "rankings/ranking.html", {
        "board": board,
        "rows": rows,
        "min_matches": min_matches,
    })


@require_POST
def create_personal_result(request, slug):
    board = _active_board(slug)
    vote_session = get_vote_session(request)
    count = vote_session.votes.filter(board=board, skipped=False).count()

    if count < 5:
        messages.warning(request, "개인 결과를 만들려면 최소 5번 이상 선택해주세요.")
        return redirect("rankings:vote", slug=slug)

    result = build_personal_result(vote_session, board)
    return redirect("rankings:personal_result", result_id=result.result_id)


def personal_result(request, result_id):
    result = get_object_or_404(PersonalResult.objects.select_related("board"), result_id=result_id)
    return render(request, "rankings/personal_result.html", {"result": result, "payload": result.result_json})


@require_GET
def api_next_pair(request, slug):
    board = _active_board(slug)
    vote_session = get_vote_session(request)
    pair = select_pair(board, vote_session)

    if pair is None:
        return JsonResponse({"detail": "비교할 대학이 부족합니다."}, status=404)

    return JsonResponse(
        {
            "board": {"slug": board.slug, "name": board.name},
            "pair": [
                {
                    "id": university.pk,
                    "name": university.name,
                    "logo_path": university.logo_path,
                    "region": university.location_label,
                    "admission_hover": build_admission_hover(university),
                }
                for university in pair
            ],
        }
    )


@require_POST
def api_vote(request, slug):
    board = _active_board(slug)
    vote_session = get_vote_session(request)

    try:
        data = json.loads(request.body or b"{}")
        university_a = University.objects.get(pk=int(data["university_a"]))
        university_b = University.objects.get(pk=int(data["university_b"]))
        skipped = bool(data.get("skipped", False))
        selected = None
        if not skipped:
            selected = University.objects.get(pk=int(data["selected_university"]))
        vote = record_vote(
            board,
            vote_session,
            university_a,
            university_b,
            selected_university=selected,
            skipped=skipped,
        )
    except (KeyError, TypeError, ValueError, University.DoesNotExist) as exc:
        return JsonResponse({"detail": str(exc) or "잘못된 요청입니다."}, status=400)

    return JsonResponse({"vote_id": vote.vote_id, "vote_count": vote_session.vote_count}, status=201)


@require_GET
def api_ranking(request, slug):
    board = _active_board(slug)
    limit = min(max(int(request.GET.get("limit", 50)), 1), 200)
    eligible_ids = ranking_university_queryset().values_list("university_id", flat=True)
    ratings = list(
        UniversityRating.objects.filter(
            board=board,
            university_id__in=eligible_ids,
            match_count__gte=0,
        )
        .select_related("university", "board")
        .order_by("-rating", "university__name")[:limit]
    )

    return JsonResponse(
        {
            "board": {"slug": board.slug, "name": board.name},
            "ranking": [
                {
                    "rank": index,
                    "university_id": rating.university_id,
                    "name": rating.university.name,
                    "rating": round(rating.rating, 2),
                    "match_count": rating.match_count,
                    "win_count": rating.win_count,
                    "loss_count": rating.loss_count,
                }
                for index, rating in enumerate(ratings, start=1)
            ],
        }
    )


def health(request):
    return JsonResponse({"status": "ok"})