"""
LockService のユニットテスト（Week 5 最重要）

スナップショット確定ロジックを網羅的に検証する。

カバーするテストケース:
  - TC-SNAP-06: 人員・配車同時 Lock → applied_* フィールドに値が入ること
  - TC-SNAP-07: 外注原価 0 円の警告検知 → ZeroCostWarning が raise されること
  - 追加ケース: 既 Lock 済みへの再 Lock 試行、ポジション未設定、単価未登録など
"""

from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from apps.performances.exceptions import ZeroCostWarning
from apps.performances.models import (
    Performance,
    PerformancePosition,
    Phase,
    PhaseSlot,
    Vehicle,
    VehicleOperation,
)
from apps.performances.services.assignment_service import AssignmentService
from apps.performances.services.freelance_rate_service import FreelanceRateService
from apps.performances.services.lock_service import LockService
from apps.performances.services.vehicle_service import VehicleService

# タイムゾーン付き datetime ヘルパー
JST = UTC  # テスト用は UTC で統一


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """aware datetime を返す"""
    return datetime(year, month, day, hour, minute, tzinfo=JST)


# ─── 共通フィクスチャ ──────────────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return User.objects.create_user(username='lock-staff-01', email='lock1@example.com')


@pytest.fixture
def another_user(db):
    return User.objects.create_user(username='lock-staff-02', email='lock2@example.com')


@pytest.fixture
def performance(db, user):
    return Performance.objects.create(
        title='Lock テスト公演',
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        created_by=user,
    )


@pytest.fixture
def position(db, performance):
    return PerformancePosition.objects.create(performance=performance, name='照明')


@pytest.fixture
def phase(db, performance):
    return Phase.objects.create(
        performance=performance,
        name='1. 機材作り',
        order=1,
        suggested_start_date=date(2026, 6, 1),
    )


@pytest.fixture
def slot(db, phase):
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
def operation(db, performance):
    """確定時間付きの運行工程"""
    op = VehicleOperation.objects.create(
        performance=performance,
        title='劇場搬入',
        requested_start=dt(2026, 6, 1, 9),
        requested_end=dt(2026, 6, 1, 12),
        route_from='倉庫',
        route_to='劇場',
    )
    op.scheduled_start = dt(2026, 6, 1, 9)
    op.scheduled_end = dt(2026, 6, 1, 12)
    op.status = VehicleOperation.Status.ASSIGNED
    op.save()
    return op


# ─── TC-SNAP-06: 人員・配車同時 Lock ─────────────────────────────────────────


@pytest.mark.django_db
class TestLockPhaseSlot:
    def test_tc_snap_06_staff_applied_fields_are_set(self, slot, user, position, performance):
        """TC-SNAP-06: Lock 後、StaffAssignment の applied_* フィールドに値が入ること"""
        # 単価を登録
        FreelanceRateService.create_rate(
            performance=performance,
            user=user,
            position=position,
            unit_price=15000,
            allowance=500,
            valid_from=date(2026, 1, 1),
        )

        # スタッフをアサイン（ポジション付き）
        assignment = AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 9),
            occupied_end=dt(2026, 6, 1, 18),
            position=position,
        )

        # Lock 実行
        locked_slot = LockService.lock_phase_slot(slot)

        # PhaseSlot のステータス確認
        assert locked_slot.status == PhaseSlot.Status.LOCKED

        # StaffAssignment のスナップショット確認
        assignment.refresh_from_db()
        assert assignment.applied_unit_price == 15000
        assert assignment.applied_allowance_total == 500
        assert assignment.applied_total_amount == 15500
        assert assignment.applied_position_name == '照明'
        assert assignment.locked_at is not None

    def test_staff_without_position_gets_zero_snapshot(self, slot, user):
        """ポジション未設定のスタッフは 0 円スナップショットが保存されること"""
        assignment = AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 9),
            occupied_end=dt(2026, 6, 1, 18),
            position=None,
        )

        LockService.lock_phase_slot(slot)

        assignment.refresh_from_db()
        assert assignment.applied_unit_price == 0
        assert assignment.applied_allowance_total == 0
        assert assignment.applied_total_amount == 0
        assert assignment.applied_position_name == ''
        assert assignment.locked_at is not None

    def test_staff_without_rate_gets_zero_snapshot(self, slot, user, position):
        """単価未登録のスタッフは 0 円スナップショットが保存されること"""
        # 単価を登録しない状態でアサイン
        assignment = AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 9),
            occupied_end=dt(2026, 6, 1, 18),
            position=position,
        )

        LockService.lock_phase_slot(slot)

        assignment.refresh_from_db()
        assert assignment.applied_unit_price == 0
        assert assignment.applied_total_amount == 0
        assert assignment.locked_at is not None

    def test_slot_status_becomes_locked(self, slot):
        """Lock 後、PhaseSlot.status が LOCKED になること"""
        LockService.lock_phase_slot(slot)

        slot.refresh_from_db()
        assert slot.status == PhaseSlot.Status.LOCKED

    def test_already_locked_slot_raises_validation_error(self, slot):
        """既に Locked 済みの Slot に再 Lock しようとすると ValidationError になること"""
        LockService.lock_phase_slot(slot)

        with pytest.raises(ValidationError):
            LockService.lock_phase_slot(slot)

    def test_multiple_staff_all_get_snapshots(
        self, slot, user, another_user, position, performance
    ):
        """複数スタッフが割当されている場合、全員に applied_* が保存されること"""
        FreelanceRateService.create_rate(
            performance=performance,
            user=user,
            position=position,
            unit_price=12000,
            allowance=0,
            valid_from=date(2026, 1, 1),
        )
        FreelanceRateService.create_rate(
            performance=performance,
            user=another_user,
            position=position,
            unit_price=18000,
            allowance=1000,
            valid_from=date(2026, 1, 1),
        )

        a1 = AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 9),
            occupied_end=dt(2026, 6, 1, 14),
            position=position,
        )
        a2 = AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=another_user,
            occupied_start=dt(2026, 6, 1, 9),
            occupied_end=dt(2026, 6, 1, 14),
            position=position,
        )

        LockService.lock_phase_slot(slot)

        a1.refresh_from_db()
        a2.refresh_from_db()

        assert a1.applied_unit_price == 12000
        assert a1.applied_total_amount == 12000

        assert a2.applied_unit_price == 18000
        assert a2.applied_total_amount == 19000


# ─── TC-SNAP-06: 配車 Lock ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestLockVehicleOperation:
    def test_tc_snap_06_vehicle_applied_fields_are_set(self, operation, company_vehicle):
        """TC-SNAP-06: Lock 後、VehicleAssignment の applied_cost_amount に値が入ること"""
        # 配車割当を作成し、原価を確定
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=company_vehicle,
        )
        VehicleService.finalize_vehicle_cost(assignment, amount=25000)

        # Lock 実行
        locked_op = LockService.lock_vehicle_operation(operation)

        # VehicleOperation のステータス確認
        assert locked_op.status == VehicleOperation.Status.LOCKED

        # VehicleAssignment のスナップショット確認
        assignment.refresh_from_db()
        assert assignment.applied_cost_amount == 25000
        assert assignment.locked_at is not None

    def test_operation_status_becomes_locked(self, operation, company_vehicle):
        """Lock 後、VehicleOperation.status が LOCKED になること"""
        AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=company_vehicle,
        )
        LockService.lock_vehicle_operation(operation)

        operation.refresh_from_db()
        assert operation.status == VehicleOperation.Status.LOCKED

    def test_already_locked_operation_raises_validation_error(self, operation):
        """既に Locked 済みの Operation に再 Lock しようとすると ValidationError になること"""
        LockService.lock_vehicle_operation(operation)

        with pytest.raises(ValidationError):
            LockService.lock_vehicle_operation(operation)

    def test_null_cost_is_saved_as_zero(self, operation, company_vehicle):
        """applied_cost_amount が null の割当は 0 円で確定保存されること"""
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=company_vehicle,
        )
        # applied_cost_amount を設定しないまま Lock

        LockService.lock_vehicle_operation(operation)

        assignment.refresh_from_db()
        assert assignment.applied_cost_amount == 0
        assert assignment.locked_at is not None


# ─── TC-SNAP-07: 外注原価 0 円の警告検知 ─────────────────────────────────────


@pytest.mark.django_db
class TestZeroCostWarning:
    def test_tc_snap_07_external_zero_cost_raises_warning(self, operation, external_vehicle):
        """TC-SNAP-07: 外注車輌の原価が 0 円の場合、ZeroCostWarning が raise されること"""
        AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=external_vehicle,
        )
        # applied_cost_amount を 0 のまま（デフォルト None → 0 扱い）

        with pytest.raises(ZeroCostWarning):
            LockService.lock_vehicle_operation(operation)

        # Locked になっていないことを確認
        operation.refresh_from_db()
        assert operation.status != VehicleOperation.Status.LOCKED

    def test_tc_snap_07_force_true_locks_with_zero_cost(self, operation, external_vehicle):
        """TC-SNAP-07: force=True を指定すれば外注原価 0 円でも Lock できること"""
        AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=external_vehicle,
        )

        # force=True で Lock 実行 → ZeroCostWarning が出ず Lock される
        locked_op = LockService.lock_vehicle_operation(operation, force=True)

        assert locked_op.status == VehicleOperation.Status.LOCKED

    def test_external_vehicle_with_cost_set_does_not_warn(self, operation, external_vehicle):
        """外注車輌でも原価が設定済みなら ZeroCostWarning は発生しないこと"""
        assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=external_vehicle,
        )
        VehicleService.finalize_vehicle_cost(assignment, amount=30000)

        # 原価設定済みなので ZeroCostWarning は発生しない
        locked_op = LockService.lock_vehicle_operation(operation)

        assert locked_op.status == VehicleOperation.Status.LOCKED

    def test_company_vehicle_zero_cost_does_not_warn(self, operation, company_vehicle):
        """自社車輌の原価が 0 でも ZeroCostWarning は発生しないこと（外注のみ対象）"""
        AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=company_vehicle,
        )

        # 自社車輌は ZeroCostWarning の対象外
        locked_op = LockService.lock_vehicle_operation(operation)

        assert locked_op.status == VehicleOperation.Status.LOCKED


# ─── TC-SNAP-06: 人員・配車同時 Lock（統合テスト）─────────────────────────────


@pytest.mark.django_db
class TestIntegratedLock:
    def test_tc_snap_06_simultaneous_staff_and_vehicle_lock(
        self, slot, user, position, performance, operation, company_vehicle
    ):
        """
        TC-SNAP-06: 人員 Lock と配車 Lock を同一テスト内で実行し、
        両方の applied_* フィールドに値が入ることを確認する。
        """
        # 人員: 単価登録 → アサイン → Lock
        FreelanceRateService.create_rate(
            performance=performance,
            user=user,
            position=position,
            unit_price=20000,
            allowance=1000,
            valid_from=date(2026, 1, 1),
        )
        staff_assignment = AssignmentService.confirm_staff_assignment(
            slot=slot,
            user=user,
            occupied_start=dt(2026, 6, 1, 9),
            occupied_end=dt(2026, 6, 1, 18),
            position=position,
        )
        LockService.lock_phase_slot(slot)

        # 配車: アサイン → 原価確定 → Lock
        vehicle_assignment = AssignmentService.confirm_vehicle_assignment(
            operation=operation,
            vehicle=company_vehicle,
        )
        VehicleService.finalize_vehicle_cost(vehicle_assignment, amount=35000)
        LockService.lock_vehicle_operation(operation)

        # 人員スナップショット確認
        staff_assignment.refresh_from_db()
        assert staff_assignment.applied_unit_price == 20000
        assert staff_assignment.applied_allowance_total == 1000
        assert staff_assignment.applied_total_amount == 21000
        assert staff_assignment.locked_at is not None

        # 配車スナップショット確認
        vehicle_assignment.refresh_from_db()
        assert vehicle_assignment.applied_cost_amount == 35000
        assert vehicle_assignment.locked_at is not None

        # ステータス確認
        slot.refresh_from_db()
        operation.refresh_from_db()
        assert slot.status == PhaseSlot.Status.LOCKED
        assert operation.status == VehicleOperation.Status.LOCKED
