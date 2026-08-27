"""
場所マスタ API ビュー
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse

from apps.locations.models import Location


@login_required(login_url="accounts:login")
def autocomplete(request):
    """場所マスタ オートコンプリート API

    GET /locations/api/autocomplete/?q=<検索文字列>

    name / furigana に対して部分一致検索し、最大10件を返す。
    クエリが2文字未満の場合は空リストを返す。
    """
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)

    qs = (
        Location.objects.filter(is_active=True)
        .filter(Q(name__icontains=q) | Q(furigana__icontains=q))
        .order_by("sort", "name")[:10]
    )
    data = [{"id": loc.id, "name": loc.name, "address": loc.address} for loc in qs]
    return JsonResponse(data, safe=False)
