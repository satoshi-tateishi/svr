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
    'ツアー・最終荷降ろし',
]


class PhaseService:
    @staticmethod
    @transaction.atomic
    def apply_production_template(performance: Performance, start_date: date) -> list[Phase]:
        """
        9工程を一括生成する。

        Args:
            performance: 対象の公演
            start_date: 工程の基準日（各工程の予定日はここから1日ずつずらして設定）

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

        created_phases = []
        for i, step_name in enumerate(TEMPLATE_STEPS):
            phase = Phase.objects.create(
                performance=performance,
                name=f'{i + 1}. {step_name}',
                order=i,
                suggested_date=start_date + timedelta(days=i),
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
