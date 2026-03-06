"""
パフォーマンスモデルのユニットテスト
"""

from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User

from apps.performances.models import (
    Performance,
    PerformancePosition,
    Phase,
    PhaseSlot,
    StaffAssignment,
    Vehicle,
    VehicleOperation,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(username='test-uuid', email='test@example.com', password=None)


@pytest.fixture
def performance(db, user):
    return Performance.objects.create(
        title='テスト公演',
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        created_by=user,
    )


@pytest.fixture
def phase(db, performance):
    return Phase.objects.create(
        performance=performance,
        name='1. 機材作り',
        order=0,
        suggested_start_date=date(2026, 6, 1),
    )


@pytest.fixture
def phase_slot(db, phase):
    return PhaseSlot.objects.create(phase=phase, requested_staff_count=3)


# ============================================================
# PhaseSlot テスト
# ============================================================


@pytest.mark.django_db
class TestPhaseSlot:
    def test_actual_staff_count_is_zero_initially(self, phase_slot):
        """初期状態では actual_staff_count が 0 であること"""
        assert phase_slot.actual_staff_count == 0

    def test_actual_staff_count_increments_with_assignment(self, db, phase_slot, user):
        """StaffAssignment が増えると actual_staff_count が増えること"""
        performance = phase_slot.phase.performance
        position = PerformancePosition.objects.create(performance=performance, name='テック')

        now = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)

        StaffAssignment.objects.create(
            phase_slot=phase_slot,
            user=user,
            position=position,
            occupied_start=now,
            occupied_end=end,
        )
        assert phase_slot.actual_staff_count == 1

    def test_is_understaffed_when_actual_less_than_requested(self, phase_slot):
        """希望人数よりアサインが少ない場合は is_understaffed が True であること"""
        assert phase_slot.is_understaffed is True

    def test_default_status_is_draft(self, phase_slot):
        """デフォルトのステータスが 'draft' であること"""
        assert phase_slot.status == PhaseSlot.Status.DRAFT


# ============================================================
# Performance テスト
# ============================================================


@pytest.mark.django_db
class TestPerformance:
    def test_has_phases_false_initially(self, performance):
        """テンプレート展開前は has_phases が False であること"""
        assert performance.has_phases is False

    def test_has_phases_true_after_phase_created(self, performance, phase):
        """Phase が存在すると has_phases が True であること"""
        assert performance.has_phases is True

    def test_str_returns_title(self, performance):
        assert str(performance) == 'テスト公演'


# ============================================================
# Vehicle テスト
# ============================================================


@pytest.mark.django_db
class TestVehicle:
    def test_is_external_for_external_ownership(self, db):
        vehicle = Vehicle.objects.create(
            name='外注トラック',
            vehicle_type=Vehicle.VehicleType.TRUCK_2T,
            ownership_type=Vehicle.OwnershipType.EXTERNAL,
        )
        assert vehicle.is_external is True

    def test_is_not_external_for_company_ownership(self, db):
        vehicle = Vehicle.objects.create(
            name='自社トラック',
            vehicle_type=Vehicle.VehicleType.TRUCK_2T,
            ownership_type=Vehicle.OwnershipType.COMPANY,
        )
        assert vehicle.is_external is False


# ============================================================
# VehicleOperation テスト
# ============================================================


@pytest.mark.django_db
class TestVehicleOperation:
    def test_schedule_drift_minutes_none_before_confirm(self, db, performance):
        """確定前は schedule_drift_minutes が None であること"""
        op = VehicleOperation.objects.create(
            performance=performance,
            title='搬入',
            requested_start=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
            requested_end=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            route_from='倉庫',
            route_to='劇場',
        )
        assert op.schedule_drift_minutes is None

    def test_schedule_drift_minutes_positive_when_delayed(self, db, performance):
        """1時間遅れの確定で drift が 60 分になること"""
        op = VehicleOperation.objects.create(
            performance=performance,
            title='搬入',
            requested_start=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
            requested_end=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            scheduled_start=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
            scheduled_end=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
            route_from='倉庫',
            route_to='劇場',
        )
        assert op.schedule_drift_minutes == 60
