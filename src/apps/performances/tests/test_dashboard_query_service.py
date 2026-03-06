"""
DashboardQueryService のユニットテスト（Week 4）

乖離分析・人員不足警告クエリを網羅的に検証する。

カバーするテストケース:
  - TC-GAP-01: 人員不足スロットが正しく検出されること
  - TC-GAP-02: 30分以上の時間乖離が正しく検出されること（正方向・負方向）
  - get_unlocked_past_slots: 日時超過・Lock 漏れスロットが正しく検出されること
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.performances.models import (
    Performance,
    Phase,
    PhaseSlot,
    VehicleOperation,
)
from apps.performances.services.assignment_service import AssignmentService
from apps.performances.services.dashboard_query_service import DashboardQueryService

# タイムゾーン付き datetime ヘルパー
JST = UTC  # テスト用は UTC で統一


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """aware datetime を返す"""
    return datetime(year, month, day, hour, minute, tzinfo=JST)


def today_plus(days: int) -> date:
    """今日からの相対日付を返す"""
    return timezone.now().date() + timedelta(days=days)


# ─── 共通フィクスチャ ──────────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return User.objects.create_user(username='staff-gap-01', email='gap1@example.com')


@pytest.fixture
def another_user(db):
    return User.objects.create_user(username='staff-gap-02', email='gap2@example.com')


@pytest.fixture
def performance(db, user):
    return Performance.objects.create(
        title='乖離テスト公演',
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        created_by=user,
    )


@pytest.fixture
def phase(db, performance):
    return Phase.objects.create(
        performance=performance,
        name='1. 機材作り',
        order=1,
        suggested_start_date=date(2026, 6, 1),
    )


@pytest.fixture
def past_phase(db, performance):
    """suggested_date が過去の工程（Lock 漏れ検出テスト用）"""
    return Phase.objects.create(
        performance=performance,
        name='2. 稽古場仕込み',
        order=2,
        suggested_start_date=today_plus(-10),  # 10日前
    )


@pytest.fixture
def future_phase(db, performance):
    """suggested_date が未来の工程"""
    return Phase.objects.create(
        performance=performance,
        name='3. 稽古',
        order=3,
        suggested_start_date=today_plus(10),  # 10日後
    )


# ─── TC-GAP-01: 人員不足スロット検出 ────────────────────────────────────────


@pytest.mark.django_db
class TestGetStaffingShortages:
    def test_tc_gap_01_understaffed_slot_is_detected(self, phase, user, another_user):
        """TC-GAP-01: 希望3名・アサイン2名のスロットが人員不足として検出されること"""
        # 希望3名のスロットを作成
        slot = PhaseSlot.objects.create(phase=phase, requested_staff_count=3)

        # 2名だけアサイン
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 10),
            occupied_end=dt(2026, 6, 1, 14),
        )
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=another_user,
            occupied_start=dt(2026, 6, 1, 10),
            occupied_end=dt(2026, 6, 1, 14),
        )

        shortages = list(DashboardQueryService.get_staffing_shortages())
        assert len(shortages) == 1
        assert shortages[0].id == slot.id
        assert shortages[0].actual_count == 2

    def test_fully_staffed_slot_is_not_detected(self, phase, user, another_user):
        """希望2名・アサイン2名のスロットは人員不足として検出されないこと"""
        slot = PhaseSlot.objects.create(phase=phase, requested_staff_count=2)

        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 10),
            occupied_end=dt(2026, 6, 1, 14),
        )
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=another_user,
            occupied_start=dt(2026, 6, 1, 10),
            occupied_end=dt(2026, 6, 1, 14),
        )

        shortages = list(DashboardQueryService.get_staffing_shortages())
        assert len(shortages) == 0

    def test_empty_slot_with_zero_request_is_not_detected(self, phase):
        """希望人数が 0 のスロットはアサインなしでも人員不足として検出されないこと"""
        PhaseSlot.objects.create(phase=phase, requested_staff_count=0)

        shortages = list(DashboardQueryService.get_staffing_shortages())
        assert len(shortages) == 0

    def test_multiple_slots_only_understaffed_returned(self, phase, user):
        """複数スロットのうち不足スロットのみ返されること"""
        # 不足スロット: 希望2名・アサイン0名
        short_slot = PhaseSlot.objects.create(phase=phase, requested_staff_count=2)
        # 充足スロット: 希望1名・アサイン1名
        full_slot = PhaseSlot.objects.create(phase=phase, requested_staff_count=1)
        AssignmentService.confirm_staff_assignment(
            slot=full_slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 8),
            occupied_end=dt(2026, 6, 1, 10),
        )

        shortages = list(DashboardQueryService.get_staffing_shortages())
        shortage_ids = [s.id for s in shortages]
        assert short_slot.id in shortage_ids
        assert full_slot.id not in shortage_ids


# ─── TC-GAP-02: 時間乖離検出 ────────────────────────────────────────────────


@pytest.mark.django_db
class TestGetScheduleDrifts:
    def test_tc_gap_02_120min_drift_is_detected(self, performance):
        """TC-GAP-02: 希望10:00・確定12:00（120分差）の工程が乖離として検出されること"""
        op = VehicleOperation.objects.create(
            performance=performance,
            title='大幅遅延搬入',
            requested_start=dt(2026, 6, 1, 10),
            requested_end=dt(2026, 6, 1, 12),
            route_from='倉庫',
            route_to='劇場',
            scheduled_start=dt(2026, 6, 1, 12),  # 120分遅れ
            scheduled_end=dt(2026, 6, 1, 14),
        )

        drifts = list(DashboardQueryService.get_schedule_drifts())
        assert len(drifts) == 1
        assert drifts[0].id == op.id

    def test_29min_drift_is_not_detected(self, performance):
        """29分差の工程は 30 分閾値に達しないため検出されないこと"""
        VehicleOperation.objects.create(
            performance=performance,
            title='小幅遅延搬入',
            requested_start=dt(2026, 6, 1, 10),
            requested_end=dt(2026, 6, 1, 12),
            route_from='倉庫',
            route_to='劇場',
            scheduled_start=dt(2026, 6, 1, 10, 29),  # 29分遅れ
            scheduled_end=dt(2026, 6, 1, 12, 29),
        )

        drifts = list(DashboardQueryService.get_schedule_drifts())
        assert len(drifts) == 0

    def test_exact_30min_drift_is_detected(self, performance):
        """ちょうど 30 分差の工程は検出されること"""
        op = VehicleOperation.objects.create(
            performance=performance,
            title='ちょうど閾値搬入',
            requested_start=dt(2026, 6, 1, 10),
            requested_end=dt(2026, 6, 1, 12),
            route_from='倉庫',
            route_to='劇場',
            scheduled_start=dt(2026, 6, 1, 10, 30),  # ちょうど 30 分遅れ
            scheduled_end=dt(2026, 6, 1, 12, 30),
        )

        drifts = list(DashboardQueryService.get_schedule_drifts())
        assert len(drifts) == 1
        assert drifts[0].id == op.id

    def test_negative_drift_is_detected(self, performance):
        """希望より早まった場合（負方向の乖離）も検出されること"""
        op = VehicleOperation.objects.create(
            performance=performance,
            title='早まった搬入',
            requested_start=dt(2026, 6, 1, 12),
            requested_end=dt(2026, 6, 1, 14),
            route_from='倉庫',
            route_to='劇場',
            scheduled_start=dt(2026, 6, 1, 10),  # 120分早まり
            scheduled_end=dt(2026, 6, 1, 12),
        )

        drifts = list(DashboardQueryService.get_schedule_drifts())
        assert len(drifts) == 1
        assert drifts[0].id == op.id

    def test_operation_without_schedule_is_excluded(self, performance):
        """確定時間が未設定の工程は除外されること"""
        VehicleOperation.objects.create(
            performance=performance,
            title='未確定搬入',
            requested_start=dt(2026, 6, 1, 10),
            requested_end=dt(2026, 6, 1, 12),
            route_from='倉庫',
            route_to='劇場',
            # scheduled_start/end は未設定
        )

        drifts = list(DashboardQueryService.get_schedule_drifts())
        assert len(drifts) == 0

    def test_custom_threshold_minutes(self, performance):
        """カスタム閾値（60 分）で 30 分差の工程が検出されないこと"""
        VehicleOperation.objects.create(
            performance=performance,
            title='30分遅延搬入',
            requested_start=dt(2026, 6, 1, 10),
            requested_end=dt(2026, 6, 1, 12),
            route_from='倉庫',
            route_to='劇場',
            scheduled_start=dt(2026, 6, 1, 10, 30),  # 30分遅れ
            scheduled_end=dt(2026, 6, 1, 12, 30),
        )

        # 閾値 60 分では検出されない
        drifts_60 = list(DashboardQueryService.get_schedule_drifts(threshold_minutes=60))
        assert len(drifts_60) == 0

        # 閾値 30 分では検出される
        drifts_30 = list(DashboardQueryService.get_schedule_drifts(threshold_minutes=30))
        assert len(drifts_30) == 1


# ─── get_unlocked_past_slots テスト ─────────────────────────────────────────


@pytest.mark.django_db
class TestGetUnlockedPastSlots:
    def test_past_unlocked_slot_is_detected(self, past_phase):
        """過去の suggested_date を持つ未 Lock スロットが検出されること"""
        slot = PhaseSlot.objects.create(
            phase=past_phase,
            requested_staff_count=2,
            status=PhaseSlot.Status.DRAFT,
        )

        result = list(DashboardQueryService.get_unlocked_past_slots())
        assert len(result) == 1
        assert result[0].id == slot.id

    def test_past_locked_slot_is_excluded(self, past_phase):
        """過去の suggested_date を持つ Lock 済みスロットは除外されること"""
        PhaseSlot.objects.create(
            phase=past_phase,
            requested_staff_count=2,
            status=PhaseSlot.Status.LOCKED,
        )

        result = list(DashboardQueryService.get_unlocked_past_slots())
        assert len(result) == 0

    def test_future_unlocked_slot_is_excluded(self, future_phase):
        """未来の suggested_date を持つスロットは未 Lock でも除外されること"""
        PhaseSlot.objects.create(
            phase=future_phase,
            requested_staff_count=2,
            status=PhaseSlot.Status.DRAFT,
        )

        result = list(DashboardQueryService.get_unlocked_past_slots())
        assert len(result) == 0

    def test_past_assigned_slot_is_detected(self, past_phase):
        """ASSIGNED ステータスの過去スロットも検出されること"""
        slot = PhaseSlot.objects.create(
            phase=past_phase,
            requested_staff_count=1,
            status=PhaseSlot.Status.ASSIGNED,
        )

        result = list(DashboardQueryService.get_unlocked_past_slots())
        assert len(result) == 1
        assert result[0].id == slot.id
