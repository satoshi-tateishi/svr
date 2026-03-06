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
        created_by=user,
    )


@pytest.fixture
def phase_data_list():
    from datetime import date, timedelta

    start = date(2026, 6, 1)
    # 開始日と終了日を同じにする
    return [(start + timedelta(days=i), start + timedelta(days=i), "12:00", "21:00") for i in range(len(TEMPLATE_STEPS))]


@pytest.mark.django_db
class TestApplyProductionTemplate:
    def test_creates_10_phases(self, performance, phase_data_list):
        """テンプレート展開で 10 工程が生成されること"""
        PhaseService.apply_production_template(performance, phase_data_list)
        assert Phase.objects.filter(performance=performance).count() == 10

    def test_phases_are_in_correct_order(self, performance, phase_data_list):
        """工程が正しい順序（order 0〜9）で生成されること"""
        PhaseService.apply_production_template(performance, phase_data_list)
        phases = list(Phase.objects.filter(performance=performance).order_by('order'))
        for i, phase in enumerate(phases):
            assert phase.order == i

    def test_phase_names_match_template(self, performance, phase_data_list):
        """工程名が TEMPLATE_STEPS と一致すること"""
        PhaseService.apply_production_template(performance, phase_data_list)
        phases = list(Phase.objects.filter(performance=performance).order_by('order'))
        for i, (phase, step_name) in enumerate(zip(phases, TEMPLATE_STEPS, strict=False)):
            assert phase.name == step_name

    def test_creates_slot_for_each_phase(self, performance, phase_data_list):
        """各 Phase に PhaseSlot が 1 つずつ作成されること"""
        PhaseService.apply_production_template(performance, phase_data_list)
        phases = Phase.objects.filter(performance=performance)
        for phase in phases:
            assert PhaseSlot.objects.filter(phase=phase).count() == 1

    def test_slot_initial_staff_count_is_zero(self, performance, phase_data_list):
        """作成された PhaseSlot の希望人数が 0 であること"""
        PhaseService.apply_production_template(performance, phase_data_list)
        slots = PhaseSlot.objects.filter(phase__performance=performance)
        for slot in slots:
            assert slot.requested_staff_count == 0

    def test_suggested_dates_match_input(self, performance, phase_data_list):
        """各工程の開始日・終了日が入力データと一致すること"""
        PhaseService.apply_production_template(performance, phase_data_list)
        phases = list(Phase.objects.filter(performance=performance).order_by('order'))
        for i, phase in enumerate(phases):
            assert phase.suggested_start_date == phase_data_list[i][0]
            assert phase.suggested_end_date == phase_data_list[i][1]

    def test_suggested_time_is_saved(self, performance):
        """予定時間が正しく保存されること"""
        from datetime import date

        data = [(date(2026, 6, 1), date(2026, 6, 2), "10:00", "18:00")] + [
            (date(2026, 6, i + 3), date(2026, 6, i + 3), None, None) for i in range(len(TEMPLATE_STEPS) - 1)
        ]
        PhaseService.apply_production_template(performance, data)
        first_phase = Phase.objects.filter(performance=performance).order_by('order').first()
        assert first_phase.suggested_start_time.strftime("%H:%M") == "10:00"
        assert first_phase.suggested_end_time.strftime("%H:%M") == "18:00"

    def test_returns_list_of_phases(self, performance, phase_data_list):
        """返り値が Phase のリストであること"""
        result = PhaseService.apply_production_template(performance, phase_data_list)
        assert isinstance(result, list)
        assert len(result) == 10
        assert all(isinstance(p, Phase) for p in result)

    def test_idempotency_guard_raises_on_second_call(self, performance, phase_data_list):
        """2 回目の展開は ValidationError になること（冪等性ガード）"""
        PhaseService.apply_production_template(performance, phase_data_list)
        with pytest.raises(ValidationError):
            PhaseService.apply_production_template(performance, phase_data_list)

    def test_raises_validation_error_if_start_after_end(self, performance):
        """開始日が終了日より後の場合、ValidationError が発生すること"""
        from datetime import date

        data = [(date(2026, 6, 2), date(2026, 6, 1), None, None)] + [
            (date(2026, 6, i + 3), date(2026, 6, i + 3), None, None) for i in range(len(TEMPLATE_STEPS) - 1)
        ]
        with pytest.raises(ValidationError) as excinfo:
            PhaseService.apply_production_template(performance, data)
        assert "開始日" in str(excinfo.value)
        assert "終了日" in str(excinfo.value)

    def test_different_performances_are_independent(self, db, user):
        """異なる公演への展開は互いに影響しないこと"""
        from datetime import date, timedelta

        p1 = Performance.objects.create(title='公演A', created_by=user)
        p2 = Performance.objects.create(title='公演B', created_by=user)
        data1 = [(date(2026, 6, 1) + timedelta(days=i), date(2026, 6, 1) + timedelta(days=i), None, None) for i in range(len(TEMPLATE_STEPS))]
        data2 = [(date(2026, 7, 1) + timedelta(days=i), date(2026, 7, 1) + timedelta(days=i), None, None) for i in range(len(TEMPLATE_STEPS))]

        PhaseService.apply_production_template(p1, data1)
        PhaseService.apply_production_template(p2, data2)

        assert Phase.objects.filter(performance=p1).count() == 10
        assert Phase.objects.filter(performance=p2).count() == 10
