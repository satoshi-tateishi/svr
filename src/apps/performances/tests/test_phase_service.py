"""
PhaseService のユニットテスト（最重要）

テンプレート展開の正確性・冪等性を検証する。
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from apps.performances.models import Performance, Phase, PhaseSlot
from apps.performances.services.phase_service import TEMPLATE_STEPS, PhaseService


@pytest.fixture
def user(db):
    return User.objects.create_user(username='test-uuid', email='test@example.com', password=None)


@pytest.fixture
def performance(db, user):
    return Performance.objects.create(
        title='テスト公演',
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        created_by=user,
    )


@pytest.mark.django_db
class TestApplyProductionTemplate:
    def test_creates_9_phases(self, performance):
        """テンプレート展開で 9 工程が生成されること"""
        PhaseService.apply_production_template(performance, date(2026, 6, 1))
        assert Phase.objects.filter(performance=performance).count() == 9

    def test_phases_are_in_correct_order(self, performance):
        """工程が正しい順序（order 0〜8）で生成されること"""
        PhaseService.apply_production_template(performance, date(2026, 6, 1))
        phases = list(Phase.objects.filter(performance=performance).order_by('order'))
        for i, phase in enumerate(phases):
            assert phase.order == i

    def test_phase_names_match_template(self, performance):
        """工程名が TEMPLATE_STEPS と一致すること"""
        PhaseService.apply_production_template(performance, date(2026, 6, 1))
        phases = list(Phase.objects.filter(performance=performance).order_by('order'))
        for i, (phase, step_name) in enumerate(zip(phases, TEMPLATE_STEPS)):
            assert phase.name == f'{i + 1}. {step_name}'

    def test_creates_slot_for_each_phase(self, performance):
        """各 Phase に PhaseSlot が 1 つずつ作成されること"""
        PhaseService.apply_production_template(performance, date(2026, 6, 1))
        phases = Phase.objects.filter(performance=performance)
        for phase in phases:
            assert PhaseSlot.objects.filter(phase=phase).count() == 1

    def test_slot_initial_staff_count_is_zero(self, performance):
        """作成された PhaseSlot の希望人数が 0 であること"""
        PhaseService.apply_production_template(performance, date(2026, 6, 1))
        slots = PhaseSlot.objects.filter(phase__performance=performance)
        for slot in slots:
            assert slot.requested_staff_count == 0

    def test_suggested_dates_increment_by_one_day(self, performance):
        """各工程の suggested_date が基準日から 1 日ずつ増加すること"""
        start = date(2026, 6, 1)
        PhaseService.apply_production_template(performance, start)
        phases = list(Phase.objects.filter(performance=performance).order_by('order'))
        for i, phase in enumerate(phases):
            from datetime import timedelta
            assert phase.suggested_date == start + timedelta(days=i)

    def test_returns_list_of_phases(self, performance):
        """返り値が Phase のリストであること"""
        result = PhaseService.apply_production_template(performance, date(2026, 6, 1))
        assert isinstance(result, list)
        assert len(result) == 9
        assert all(isinstance(p, Phase) for p in result)

    def test_idempotency_guard_raises_on_second_call(self, performance):
        """2 回目の展開は ValidationError になること（冪等性ガード）"""
        PhaseService.apply_production_template(performance, date(2026, 6, 1))
        with pytest.raises(ValidationError):
            PhaseService.apply_production_template(performance, date(2026, 6, 1))

    def test_different_performances_are_independent(self, db, user):
        """異なる公演への展開は互いに影響しないこと"""
        p1 = Performance.objects.create(
            title='公演A', start_date=date(2026, 6, 1), end_date=date(2026, 6, 10), created_by=user
        )
        p2 = Performance.objects.create(
            title='公演B', start_date=date(2026, 7, 1), end_date=date(2026, 7, 10), created_by=user
        )
        PhaseService.apply_production_template(p1, date(2026, 6, 1))
        PhaseService.apply_production_template(p2, date(2026, 7, 1))

        assert Phase.objects.filter(performance=p1).count() == 9
        assert Phase.objects.filter(performance=p2).count() == 9
