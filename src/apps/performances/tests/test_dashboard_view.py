"""
ダッシュボードビュー + 公演詳細ページ改善のテスト（Week 7）

カバーするテストケース:
  - TC-DASH-01: 未認証ユーザーはログインページへリダイレクトされること
  - TC-DASH-02: 認証済みユーザーはダッシュボードにアクセスできること
  - TC-DASH-03: ダッシュボードに 3 種のクエリ結果が含まれること
  - TC-DASH-04: 人員不足スロットがダッシュボードに表示されること
  - TC-DETAIL-01: 公演詳細ページに PDF ダウンロードリンクが表示されること
  - TC-DETAIL-02: PhaseSlot.locked_assignment_count が正しく返ること
  - TC-DETAIL-03: PhaseSlot.locked_total_amount が Lock 済みアサインの合計を返すこと
  - TC-DETAIL-04: Lock 未実施のアサインは locked_total_amount に含まれないこと
"""

from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.performances.models import Performance, Phase, PhaseSlot
from apps.performances.models.staff import StaffAssignment

# ─── ヘルパー ────────────────────────────────────────────────────────────────


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """aware datetime を返す"""
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ─── 共通フィクスチャ ──────────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='dash-view-user',
        email='dash@example.com',
        password='testpass',
    )


@pytest.fixture
def performance(db, user):
    return Performance.objects.create(
        title='テスト公演',
        start_date=date(2025, 10, 1),
        end_date=date(2025, 10, 10),
        created_by=user,
    )


@pytest.fixture
def phase(db, performance):
    return Phase.objects.create(
        performance=performance,
        name='1. 機材作り',
        order=0,
        suggested_start_date=date(2025, 10, 1),
    )


@pytest.fixture
def slot(db, phase):
    return PhaseSlot.objects.create(
        phase=phase,
        requested_staff_count=3,
        status=PhaseSlot.Status.ASSIGNED,
    )


@pytest.fixture
def client_logged_in(user):
    c = Client()
    c.login(username='dash-view-user', password='testpass')
    return c


# ─── TC-DASH-01: 未認証 → リダイレクト ──────────────────────────────────────


@pytest.mark.django_db
def test_dashboard_requires_login():
    """未認証ユーザーはログインページへリダイレクトされること"""
    c = Client()
    response = c.get('/performances/dashboard/')
    assert response.status_code == 302
    assert '/auth/login/' in response['Location']


# ─── TC-DASH-02: 認証済みユーザーはアクセスできる ────────────────────────────


@pytest.mark.django_db
def test_dashboard_accessible_when_authenticated(client_logged_in):
    """認証済みユーザーはダッシュボードにアクセスできること"""
    response = client_logged_in.get('/performances/dashboard/')
    assert response.status_code == 200


# ─── TC-DASH-03: コンテキストに 3 種のクエリ結果が含まれる ───────────────────


@pytest.mark.django_db
def test_dashboard_context_keys(client_logged_in):
    """ダッシュボードのコンテキストに必須キーが含まれること"""
    response = client_logged_in.get('/performances/dashboard/')
    assert 'staffing_shortages' in response.context
    assert 'schedule_drifts' in response.context
    assert 'unlocked_past_slots' in response.context


# ─── TC-DASH-04: 人員不足スロットがダッシュボードに表示される ────────────────


@pytest.mark.django_db
def test_dashboard_shows_staffing_shortages(client_logged_in, slot, user):
    """人員不足スロットがダッシュボードコンテキストに含まれること"""
    # slot の requested_staff_count=3 に対してアサインは 0 → 不足
    response = client_logged_in.get('/performances/dashboard/')
    shortages = response.context['staffing_shortages']
    assert shortages.filter(pk=slot.pk).exists()


# ─── TC-DETAIL-01: 公演詳細ページに PDF リンクが表示される ───────────────────


@pytest.mark.django_db
def test_detail_shows_pdf_buttons(client_logged_in, performance, phase, slot):
    """公演詳細ページに PDF ダウンロードリンクが表示されること"""
    response = client_logged_in.get(f'/performances/{performance.pk}/')
    assert response.status_code == 200
    content = response.content.decode()
    assert f'/performances/{performance.pk}/report/performance/' in content
    assert f'/performances/{performance.pk}/report/financial/' in content


# ─── TC-DETAIL-02: PhaseSlot.locked_assignment_count ────────────────────────


@pytest.mark.django_db
def test_locked_assignment_count_zero_when_no_assignments(slot):
    """アサインがない場合 locked_assignment_count は 0"""
    assert slot.locked_assignment_count == 0


@pytest.mark.django_db
def test_locked_assignment_count_counts_only_locked(slot, user):
    """Lock 済みアサインのみをカウントすること"""
    # 未 Lock アサイン
    StaffAssignment.objects.create(
        phase_slot=slot,
        user=user,
        occupied_start=dt(2025, 10, 1, 9, 0),
        occupied_end=dt(2025, 10, 1, 18, 0),
        locked_at=None,
    )
    # Lock 済みアサイン
    another_user = User.objects.create_user(username='locked-user', email='locked@example.com')
    StaffAssignment.objects.create(
        phase_slot=slot,
        user=another_user,
        occupied_start=dt(2025, 10, 1, 9, 0),
        occupied_end=dt(2025, 10, 1, 18, 0),
        locked_at=dt(2025, 10, 2, 12, 0),
        applied_unit_price=10000,
        applied_total_amount=10000,
    )
    slot.refresh_from_db()
    assert slot.locked_assignment_count == 1


# ─── TC-DETAIL-03: PhaseSlot.locked_total_amount ────────────────────────────


@pytest.mark.django_db
def test_locked_total_amount_sums_locked_assignments(slot, user):
    """Lock 済みアサインの applied_total_amount 合計が返ること"""
    another_user = User.objects.create_user(username='amt-user-2', email='amt2@example.com')
    StaffAssignment.objects.create(
        phase_slot=slot,
        user=user,
        occupied_start=dt(2025, 10, 1, 9, 0),
        occupied_end=dt(2025, 10, 1, 18, 0),
        locked_at=dt(2025, 10, 2, 12, 0),
        applied_unit_price=10000,
        applied_total_amount=10000,
    )
    StaffAssignment.objects.create(
        phase_slot=slot,
        user=another_user,
        occupied_start=dt(2025, 10, 1, 9, 0),
        occupied_end=dt(2025, 10, 1, 18, 0),
        locked_at=dt(2025, 10, 2, 12, 0),
        applied_unit_price=8000,
        applied_total_amount=9000,
    )
    slot.refresh_from_db()
    assert slot.locked_total_amount == 19000


# ─── TC-DETAIL-04: 未 Lock アサインは合計に含まれない ──────────────────────────


@pytest.mark.django_db
def test_locked_total_amount_excludes_unlocked(slot, user):
    """Lock 未実施のアサインは locked_total_amount に含まれないこと"""
    StaffAssignment.objects.create(
        phase_slot=slot,
        user=user,
        occupied_start=dt(2025, 10, 1, 9, 0),
        occupied_end=dt(2025, 10, 1, 18, 0),
        locked_at=None,
        applied_total_amount=None,
    )
    slot.refresh_from_db()
    assert slot.locked_total_amount == 0
