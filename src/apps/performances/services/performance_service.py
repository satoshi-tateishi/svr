"""
PerformanceService — 公演 CRUD サービス
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.performances.models.base import Performance


class PerformanceService:
    @staticmethod
    @transaction.atomic
    def create_performance(
        title: str,
        start_date: date,
        end_date: date,
        created_by: User,
        description: str = '',
    ) -> Performance:
        """
        公演を新規作成する。

        Args:
            title: 公演タイトル
            start_date: 開始日
            end_date: 終了日
            created_by: 作成者
            description: 備考（省略可）

        Returns:
            作成した Performance インスタンス

        Raises:
            ValidationError: 終了日が開始日より前の場合
        """
        if end_date < start_date:
            raise ValidationError('終了日は開始日以降に設定してください。')

        return Performance.objects.create(
            title=title,
            start_date=start_date,
            end_date=end_date,
            created_by=created_by,
            description=description,
        )

    @staticmethod
    def get_performance_list(user: User):
        """公演一覧を取得する（Phase の有無も含めて一括取得）"""
        return Performance.objects.prefetch_related('phases').order_by('-start_date')
