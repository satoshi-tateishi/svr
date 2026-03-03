"""
AssignmentService のユニットテスト（Week 3 最重要）

ダブルブッキング防止ロジックを網羅的に検証する。

カバーするテストケース:
  - TC-ST-01: 人員割当（重複なし） → 正常に割当できること
  - TC-ST-02: 人員割当（時間重複） → ConflictError になること
  - TC-ST-03: 人員割当（隣接・境界） → 重複なしで割当できること
  - TC-VH-01: 車輌割当（重複なし） → 正常に割当できること
  - TC-VH-03: 車輌割当（時間重複） → ConflictError になること（設計書のメインケース）
  - TC-VH-04: 外注車輌（時間重複） → ConflictError にならず割当できること
  - TC-VH-05: 車輌割当（確定時間未設定） → 重複チェックなしで割当できること
"""

from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User

from apps.performances.exceptions import ConflictError
from apps.performances.models import (
    Performance,
    Phase,
    PhaseSlot,
    StaffAssignment,
    Vehicle,
    VehicleAssignment,
    VehicleOperation,
)
from apps.performances.services.assignment_service import AssignmentService

# タイムゾーン付き datetime ヘルパー
JST = UTC  # テスト用は UTC で統一（USE_TZ=True のため aware が必要）


def dt(hour: int, minute: int = 0) -> datetime:
    """2026-06-01 の任意時刻の aware datetime を返す"""
    return datetime(2026, 6, 1, hour, minute, tzinfo=JST)


# ─── フィクスチャ ───────────────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return User.objects.create_user(username='staff-uuid-1', email='staff1@example.com')


@pytest.fixture
def another_user(db):
    return User.objects.create_user(username='staff-uuid-2', email='staff2@example.com')


@pytest.fixture
def performance(db, user):
    return Performance.objects.create(
        title='テスト公演',
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        created_by=user,
    )


@pytest.fixture
def phase(db, performance):
    return Phase.objects.create(performance=performance, name='1. 機材作り', order=0)


@pytest.fixture
def slot(db, phase):
    return PhaseSlot.objects.create(phase=phase, requested_staff_count=3)


@pytest.fixture
def another_slot(db, phase):
    return PhaseSlot.objects.create(phase=phase, requested_staff_count=2)


@pytest.fixture
def company_vehicle(db):
    return Vehicle.objects.create(
        name='2tトラックA',
        vehicle_type=Vehicle.VehicleType.TRUCK_2T,
        ownership_type=Vehicle.OwnershipType.COMPANY,
    )


@pytest.fixture
def external_vehicle(db):
    return Vehicle.objects.create(
        name='外注トラックX',
        vehicle_type=Vehicle.VehicleType.TRUCK_2T,
        ownership_type=Vehicle.OwnershipType.EXTERNAL,
    )


@pytest.fixture
def operation_morning(db, performance):
    """午前の運行工程（10:00〜12:00）"""
    op = VehicleOperation.objects.create(
        performance=performance,
        title='午前搬入',
        requested_start=dt(10),
        requested_end=dt(12),
        route_from='倉庫',
        route_to='劇場',
    )
    op.scheduled_start = dt(10)
    op.scheduled_end = dt(12)
    op.save()
    return op


@pytest.fixture
def operation_afternoon(db, performance):
    """午後の運行工程（14:00〜16:00）"""
    op = VehicleOperation.objects.create(
        performance=performance,
        title='午後搬入',
        requested_start=dt(14),
        requested_end=dt(16),
        route_from='倉庫',
        route_to='劇場',
    )
    op.scheduled_start = dt(14)
    op.scheduled_end = dt(16)
    op.save()
    return op


@pytest.fixture
def operation_overlapping(db, performance):
    """午前と重複する運行工程（11:00〜13:00）"""
    op = VehicleOperation.objects.create(
        performance=performance,
        title='重複搬入',
        requested_start=dt(11),
        requested_end=dt(13),
        route_from='倉庫',
        route_to='劇場',
    )
    op.scheduled_start = dt(11)
    op.scheduled_end = dt(13)
    op.save()
    return op


@pytest.fixture
def operation_no_schedule(db, performance):
    """確定時間が未設定の運行工程"""
    return VehicleOperation.objects.create(
        performance=performance,
        title='未確定搬入',
        requested_start=dt(10),
        requested_end=dt(12),
        route_from='倉庫',
        route_to='劇場',
    )


# ─── 人員割当テスト ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestConfirmStaffAssignment:
    def test_tc_st_01_no_conflict_creates_assignment(self, slot, user):
        """TC-ST-01: 重複なしの場合、StaffAssignment が作成されること"""
        assignment = AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(10),
            occupied_end=dt(14),
        )
        assert isinstance(assignment, StaffAssignment)
        assert assignment.user == user
        assert assignment.phase_slot == slot
        assert assignment.occupied_start == dt(10)
        assert assignment.occupied_end == dt(14)

    def test_tc_st_02_time_overlap_raises_conflict_error(self, slot, another_slot, user):
        """TC-ST-02: 同一スタッフの時間が重複する場合、ConflictError になること"""
        # 先に 10:00〜14:00 で割当
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(10),
            occupied_end=dt(14),
        )
        # 12:00〜16:00 は上記と重複 → ConflictError
        with pytest.raises(ConflictError):
            AssignmentService.confirm_staff_assignment(
                slot=another_slot,
                user=user,
                occupied_start=dt(12),
                occupied_end=dt(16),
            )

    def test_tc_st_03_adjacent_times_do_not_conflict(self, slot, another_slot, user):
        """TC-ST-03: 終了時刻 = 開始時刻（境界接触）は重複しないこと"""
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(10),
            occupied_end=dt(14),
        )
        # 14:00〜18:00 は 10:00〜14:00 と接触しているが重複ではない
        assignment = AssignmentService.confirm_staff_assignment(
            slot=another_slot,
            user=user,
            occupied_start=dt(14),
            occupied_end=dt(18),
        )
        assert isinstance(assignment, StaffAssignment)

    def test_different_users_same_time_no_conflict(self, slot, another_slot, user, another_user):
        """別スタッフは同じ時間帯でも ConflictError にならないこと"""
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(10),
            occupied_end=dt(14),
        )
        # 別ユーザーは同じ時間帯でも割当可能
        assignment = AssignmentService.confirm_staff_assignment(
            slot=another_slot,
            user=another_user,
            occupied_start=dt(10),
            occupied_end=dt(14),
        )
        assert isinstance(assignment, StaffAssignment)

    def test_overlap_exact_match_raises_conflict_error(self, slot, another_slot, user):
        """完全一致の時間帯に割当しようとすると ConflictError になること"""
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(10),
            occupied_end=dt(14),
        )
        with pytest.raises(ConflictError):
            AssignmentService.confirm_staff_assignment(
                slot=another_slot,
                user=user,
                occupied_start=dt(10),
                occupied_end=dt(14),
            )

    def test_overlap_contained_raises_conflict_error(self, slot, another_slot, user):
        """既存割当の内側に収まる時間帯でも ConflictError になること"""
        AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(10),
            occupied_end=dt(18),
        )
        with pytest.raises(ConflictError):
            AssignmentService.confirm_staff_assignment(
                slot=another_slot,
                user=user,
                occupied_start=dt(12),
                occupied_end=dt(14),
            )


# ─── 配車割当テスト ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestConfirmVehicleAssignment:
    def test_tc_vh_01_no_conflict_creates_assignment(self, operation_morning, company_vehicle):
        """TC-VH-01: 重複なしの場合、VehicleAssignment が作成されること"""
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation_morning,
            vehicle=company_vehicle,
        )
        assert isinstance(assignment, VehicleAssignment)
        assert assignment.vehicle == company_vehicle
        assert assignment.vehicle_operation == operation_morning

    def test_tc_vh_03_time_overlap_raises_conflict_error(
        self, operation_morning, operation_overlapping, company_vehicle
    ):
        """TC-VH-03: 同一車輌の確定時間が重複する場合、ConflictError になること"""
        # 午前（10:00〜12:00）に車輌を割当
        AssignmentService.confirm_vehicle_assignment(
            operation=operation_morning,
            vehicle=company_vehicle,
        )
        # 11:00〜13:00 は重複 → ConflictError
        with pytest.raises(ConflictError):
            AssignmentService.confirm_vehicle_assignment(
                operation=operation_overlapping,
                vehicle=company_vehicle,
            )

    def test_tc_vh_04_external_vehicle_allows_overlap(
        self, operation_morning, operation_overlapping, external_vehicle
    ):
        """TC-VH-04: 外注車輌は時間が重複しても ConflictError にならないこと"""
        # 外注車輌は複数工程への割当が前提
        AssignmentService.confirm_vehicle_assignment(
            operation=operation_morning,
            vehicle=external_vehicle,
        )
        # 同じ外注車輌を重複時間帯に割当しても許可される
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation_overlapping,
            vehicle=external_vehicle,
        )
        assert isinstance(assignment, VehicleAssignment)

    def test_tc_vh_05_no_schedule_skips_conflict_check(
        self, operation_morning, operation_no_schedule, company_vehicle
    ):
        """TC-VH-05: 確定時間が未設定の工程は重複チェックをスキップして割当できること"""
        AssignmentService.confirm_vehicle_assignment(
            operation=operation_morning,
            vehicle=company_vehicle,
        )
        # 確定時間未設定の工程は重複チェックなしで割当可能
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation_no_schedule,
            vehicle=company_vehicle,
        )
        assert isinstance(assignment, VehicleAssignment)

    def test_non_overlapping_operations_no_conflict(
        self, operation_morning, operation_afternoon, company_vehicle
    ):
        """時間が重複しない2つの工程に同一車輌を割当できること"""
        AssignmentService.confirm_vehicle_assignment(
            operation=operation_morning,
            vehicle=company_vehicle,
        )
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation_afternoon,
            vehicle=company_vehicle,
        )
        assert isinstance(assignment, VehicleAssignment)

    def test_different_vehicles_same_time_no_conflict(
        self, operation_morning, operation_overlapping, company_vehicle, external_vehicle
    ):
        """異なる車輌は同じ時間帯でも ConflictError にならないこと"""
        AssignmentService.confirm_vehicle_assignment(
            operation=operation_morning,
            vehicle=company_vehicle,
        )
        # 別車輌（外注）は同じ時間帯でも割当可能
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation_overlapping,
            vehicle=external_vehicle,
        )
        assert isinstance(assignment, VehicleAssignment)
