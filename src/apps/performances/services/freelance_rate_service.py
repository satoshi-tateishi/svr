"""
FreelanceRateService — フリーランス単価履歴サービス

【設計原則】
- 単価は上書き禁止。修正が必要な場合は既存の valid_until を設定して新規作成。
- 同一 user × position × performance で期間が重複する登録は ValidationError。
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.performances.models.base import Performance, PerformancePosition
from apps.performances.models.staff import PerformanceFreelanceRate


class FreelanceRateService:
    @staticmethod
    @transaction.atomic
    def create_rate(
        performance: Performance,
        user: User,
        position: PerformancePosition,
        unit_price: int,
        valid_from: date,
        allowance: int = 0,
        valid_until: date | None = None,
    ) -> PerformanceFreelanceRate:
        """
        単価を新規登録する（期間重複チェック付き）。

        Args:
            unit_price: 単価（円）
            valid_from: 適用開始日
            allowance: 手当（円）、省略可
            valid_until: 適用終了日（省略時は無期限）

        Raises:
            ValidationError: 期間が重複する単価が既に存在する場合
        """
        if valid_until and valid_until < valid_from:
            raise ValidationError('適用終了日は適用開始日以降に設定してください。')

        FreelanceRateService._check_overlap(
            performance=performance,
            user=user,
            position=position,
            valid_from=valid_from,
            valid_until=valid_until,
        )

        return PerformanceFreelanceRate.objects.create(
            performance=performance,
            user=user,
            position=position,
            unit_price=unit_price,
            allowance=allowance,
            valid_from=valid_from,
            valid_until=valid_until,
        )

    @staticmethod
    def get_active_rate(
        performance: Performance,
        user: User,
        position: PerformancePosition,
        target_date: date,
    ) -> PerformanceFreelanceRate | None:
        """指定日時点で有効な単価を取得する（Lock 時のスナップショット確定に使用）"""
        return (
            PerformanceFreelanceRate.objects.filter(
                performance=performance,
                user=user,
                position=position,
                valid_from__lte=target_date,
            )
            .filter(models.Q(valid_until__gte=target_date) | models.Q(valid_until__isnull=True))
            .order_by('-valid_from')
            .first()
        )

    @staticmethod
    def _check_overlap(
        performance: Performance,
        user: User,
        position: PerformancePosition,
        valid_from: date,
        valid_until: date | None,
    ) -> None:
        """期間重複チェック（重複があれば ValidationError を raise）"""
        qs = PerformanceFreelanceRate.objects.filter(
            performance=performance,
            user=user,
            position=position,
        )

        for rate in qs:
            # 既存単価の期間と新規期間が重複するか判定
            existing_end = rate.valid_until  # None = 無期限
            new_end = valid_until  # None = 無期限

            # 終了日が None（無期限）は「遠い将来」として扱う
            # 重複条件: new_start <= existing_end AND existing_start <= new_end
            overlap = (
                (existing_end is None or valid_from <= existing_end)
                and (new_end is None or rate.valid_from <= new_end)
            )
            if overlap:
                raise ValidationError(
                    f'単価の期間が既存の登録（{rate.valid_from}〜{existing_end or "無期限"}）と重複しています。'
                    '既存の単価に適用終了日を設定してから再登録してください。'
                )
