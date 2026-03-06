"""
PhaseService — 工程テンプレート展開サービス

【最重要サービス】
公演に対して標準の 1〜9 工程を一括生成する。
テンプレート展開は冪等性ガード付き（既に Phase が存在する場合は ValidationError）。
"""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.performances.models.base import Performance, Phase, PhaseSlot

# 演劇制作の標準工程（順序は変更しないこと）
TEMPLATE_STEPS = [
    '機材作り',
    '稽古場仕込み',
    '稽古',
    '稽古場バラシ',
    '劇場仕込み',
    '舞台稽古',
    '本番',
    '劇場バラシ',
    'ツアー',
    '最終荷降ろし',
]


class PhaseService:
    @staticmethod
    @transaction.atomic
    def apply_production_template(
        performance: Performance, phase_data_list: list[tuple[date | None, date | None, str | None, str | None]]
    ) -> list[Phase]:
        """
        10工程を一括生成する。

        Args:
            performance: 対象の公演
            phase_data_list: (start_date, end_date, start_time_str, end_time_str) のリスト

        Returns:
            生成された Phase のリスト（order 順）

        Raises:
            ValidationError: 既に Phase が存在する場合（冪等性ガード）
        """
        if Phase.objects.filter(performance=performance).exists():
            raise ValidationError(
                f'公演「{performance.title}」には既に工程が存在します。'
                '二重展開を防ぐため、この操作は実行できません。'
            )

        if len(phase_data_list) != len(TEMPLATE_STEPS):
            raise ValidationError(
                f'工程データが {len(TEMPLATE_STEPS)} 件必要です（{len(phase_data_list)} 件受信）。'
            )

        created_phases = []
        for i, (p_start_date, p_end_date, p_start_time_str, p_end_time_str) in enumerate(phase_data_list):
            if p_start_date and p_end_date and p_start_date > p_end_date:
                raise ValidationError(
                    f'工程 {i + 1} ({TEMPLATE_STEPS[i]}) の開始日({p_start_date})が終了日({p_end_date})より後の日付になっています。'
                )

            step_name = TEMPLATE_STEPS[i]
            phase = Phase.objects.create(
                performance=performance,
                name=step_name,
                order=i,
                suggested_start_date=p_start_date,
                suggested_end_date=p_end_date,
                suggested_start_time=p_start_time_str if p_start_time_str else None,
                suggested_end_time=p_end_time_str if p_end_time_str else None,
            )
            # 各工程にデフォルトの人員枠を1つ作成（希望人数は後で編集）
            PhaseSlot.objects.create(phase=phase, requested_staff_count=0)
            created_phases.append(phase)

        return created_phases

    @staticmethod
    def get_phases_with_slots(performance: Performance) -> list[Phase]:
        """工程と人員枠を一括取得する（N+1 対策）"""
        return list(
            Phase.objects.filter(performance=performance)
            .prefetch_related('slots', 'slots__assignments')
            .order_by('order')
        )
