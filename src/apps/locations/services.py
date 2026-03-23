"""
場所マスタ同期サービス

shin-on_db の内部API から場所マスタを取得し、ローカルDBに同期する。
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

import requests
from django.conf import settings

from apps.locations.models import Location


class SyncResult(TypedDict):
    created: int
    updated: int
    deactivated: int


def sync_locations_from_shin_on_db(portal_jwt: str) -> SyncResult:
    """shin-on_db の内部API から場所マスタを同期する。

    portal_jwt: Portal SSO の JWT（Bearer トークンとして使用）

    Returns:
        SyncResult: 作成・更新・無効化の件数

    Raises:
        requests.HTTPError: API が 4xx / 5xx を返した場合
        requests.ConnectionError: API への接続に失敗した場合
    """
    api_url = settings.SHIN_ON_DB_API_URL.rstrip("/") + "/api/v1/locations"

    response = requests.get(
        api_url,
        headers={"Authorization": f"Bearer {portal_jwt}"},
        timeout=10,
    )
    response.raise_for_status()

    items = response.json()["data"]

    created = 0
    updated = 0
    api_shin_on_db_ids: list[int] = []

    for item in items:
        shin_on_db_id: int = item["id"]
        api_shin_on_db_ids.append(shin_on_db_id)

        _, is_created = Location.objects.update_or_create(
            shin_on_db_id=shin_on_db_id,
            defaults={
                "sort": item["sort"],
                "name": item["name"],
                "furigana": item.get("furigana") or "",
                "postal_code": item.get("postal_code") or "",
                "address": item.get("address") or "",
                "note": item.get("note") or "",
                "is_active": item["is_active"],
                "created_at": datetime.fromisoformat(item["created_at"]),
                "updated_at": datetime.fromisoformat(item["updated_at"]),
            },
        )
        if is_created:
            created += 1
        else:
            updated += 1

    # API に含まれなくなった同期済みレコードを無効化
    deactivated = (
        Location.objects.filter(shin_on_db_id__isnull=False)
        .exclude(shin_on_db_id__in=api_shin_on_db_ids)
        .update(is_active=False)
    )

    return {"created": created, "updated": updated, "deactivated": deactivated}
