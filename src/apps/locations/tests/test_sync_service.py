"""
場所マスタ同期サービスのテスト
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.locations.models import Location
from apps.locations.services import sync_locations_from_shin_on_db

# テスト用の API レスポンスデータ
SAMPLE_API_RESPONSE = {
    "data": [
        {
            "id": 1,
            "sort": 1,
            "type": "劇場",
            "name": "テスト劇場",
            "furigana": "てすとげきじょう",
            "tel1_name": "代表",
            "tel1": "03-0000-0001",
            "tel2_name": None,
            "tel2": None,
            "fax": None,
            "email1_name": None,
            "email1": None,
            "email2_name": None,
            "email2": None,
            "postal_code": "100-0001",
            "address": "東京都千代田区1-1",
            "note": "",
            "is_active": True,
            "is_inventory_visible": True,
            "is_transfer_visible": False,
            "is_main_warehouse": False,
            "created_at": "2025-09-26T15:20:04+09:00",
            "updated_at": "2025-09-26T15:20:04+09:00",
        },
        {
            "id": 2,
            "sort": 2,
            "type": "倉庫",
            "name": "テスト倉庫",
            "furigana": "てすとそうこ",
            "tel1_name": None,
            "tel1": None,
            "tel2_name": None,
            "tel2": None,
            "fax": None,
            "email1_name": None,
            "email1": None,
            "email2_name": None,
            "email2": None,
            "postal_code": "130-0001",
            "address": "東京都墨田区1-1",
            "note": "",
            "is_active": True,
            "is_inventory_visible": True,
            "is_transfer_visible": True,
            "is_main_warehouse": True,
            "created_at": "2025-09-26T15:20:05+09:00",
            "updated_at": "2025-09-26T15:20:05+09:00",
        },
    ]
}


def _make_mock_response(data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    if status_code >= 400:
        from requests import HTTPError

        mock.raise_for_status.side_effect = HTTPError(response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


@pytest.mark.django_db
class TestSyncLocationsFromShinOnDb:
    @patch("apps.locations.services.requests.get")
    def test_sync_creates_new_locations(self, mock_get):
        """API から取得したデータが新規作成される。"""
        mock_get.return_value = _make_mock_response(SAMPLE_API_RESPONSE)

        result = sync_locations_from_shin_on_db("test-jwt")

        assert result["created"] == 2
        assert result["updated"] == 0
        assert result["deactivated"] == 0
        assert Location.objects.count() == 2

        loc = Location.objects.get(shin_on_db_id=1)
        assert loc.name == "テスト劇場"
        assert loc.furigana == "てすとげきじょう"
        assert loc.postal_code == "100-0001"
        assert loc.is_active is True

    @patch("apps.locations.services.requests.get")
    def test_sync_updates_existing_locations(self, mock_get):
        """既存の shin_on_db_id 付きレコードが更新される。"""
        Location.objects.create(
            shin_on_db_id=1,
            name="古い劇場名",
            sort=99,
            is_active=True,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_get.return_value = _make_mock_response(SAMPLE_API_RESPONSE)

        result = sync_locations_from_shin_on_db("test-jwt")

        assert result["created"] == 1
        assert result["updated"] == 1
        assert Location.objects.count() == 2

        loc = Location.objects.get(shin_on_db_id=1)
        assert loc.name == "テスト劇場"
        assert loc.sort == 1

    @patch("apps.locations.services.requests.get")
    def test_sync_deactivates_removed_locations(self, mock_get):
        """API に存在しなくなった同期済みレコードが無効化される。"""
        Location.objects.create(
            shin_on_db_id=999,
            name="削除済み場所",
            sort=1,
            is_active=True,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_get.return_value = _make_mock_response(SAMPLE_API_RESPONSE)

        result = sync_locations_from_shin_on_db("test-jwt")

        assert result["deactivated"] == 1
        removed = Location.objects.get(shin_on_db_id=999)
        assert removed.is_active is False

    @patch("apps.locations.services.requests.get")
    def test_sync_does_not_affect_manual_records(self, mock_get):
        """shin_on_db_id が空の手動登録レコードは無効化されない。"""
        Location.objects.create(
            shin_on_db_id=None,
            name="手動登録場所",
            sort=1,
            is_active=True,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_get.return_value = _make_mock_response(SAMPLE_API_RESPONSE)

        result = sync_locations_from_shin_on_db("test-jwt")

        assert result["deactivated"] == 0
        manual = Location.objects.get(shin_on_db_id=None)
        assert manual.is_active is True

    @patch("apps.locations.services.requests.get")
    def test_sync_raises_on_api_error(self, mock_get):
        """API が 401 を返した場合に HTTPError が発生する。"""
        import requests as req

        mock_get.return_value = _make_mock_response({}, status_code=401)

        with pytest.raises(req.HTTPError):
            sync_locations_from_shin_on_db("invalid-jwt")

    @patch("apps.locations.services.requests.get")
    def test_sync_sends_bearer_token(self, mock_get):
        """リクエストに Authorization: Bearer ヘッダーが含まれる。"""
        mock_get.return_value = _make_mock_response({"data": []})

        sync_locations_from_shin_on_db("my-portal-jwt")

        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer my-portal-jwt"


def _make_staff_client(client):
    """
    svr の UserProfile.save() は system_role != ADMIN のとき is_staff を False にリセットする。
    シグナルをバイパスして is_staff=True のユーザーを作成するヘルパー。
    """
    user = User.objects.create_user(username="staff_user", password="password")
    # UserProfile.save() を経由せず直接更新（既存テストと同じパターン）
    User.objects.filter(pk=user.pk).update(is_staff=True)
    UserProfile.objects.filter(user=user).update(
        system_role=UserProfile.SystemRole.ADMIN
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestSyncView:
    def test_sync_view_requires_login(self, client):
        """未認証でアクセスすると管理サイトのログイン画面へリダイレクト。"""
        url = reverse("admin:locations_location_sync")
        response = client.get(url)
        assert response.status_code == 302
        assert "/admin/login/" in response["Location"]

    def test_sync_view_get_shows_confirmation(self, client):
        """管理スタッフが GET すると確認画面が表示される。"""
        staff_client = _make_staff_client(client)
        url = reverse("admin:locations_location_sync")
        response = staff_client.get(url)

        assert response.status_code == 200
        assert "場所マスタ同期" in response.content.decode()

    def test_sync_view_post_without_jwt_shows_error(self, client):
        """portal_jwt Cookie なしで POST するとエラーメッセージが表示される。"""
        staff_client = _make_staff_client(client)
        url = reverse("admin:locations_location_sync")
        response = staff_client.post(url)

        assert response.status_code == 200
        assert "Portal JWT が見つかりません" in response.content.decode()

    @patch("apps.locations.admin.sync_locations_from_shin_on_db")
    def test_sync_view_post_with_jwt_shows_result(self, mock_sync, client):
        """portal_jwt Cookie あり・同期成功時に結果が表示される。"""
        mock_sync.return_value = {"created": 5, "updated": 3, "deactivated": 1}
        staff_client = _make_staff_client(client)
        staff_client.cookies["portal_jwt"] = "test-jwt-value"

        url = reverse("admin:locations_location_sync")
        response = staff_client.post(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "5" in content
        assert "3" in content
        assert "1" in content
        mock_sync.assert_called_once_with("test-jwt-value")
