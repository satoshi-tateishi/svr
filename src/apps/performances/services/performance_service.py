"""
PerformanceService — 公演 CRUD サービス
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.performances.models.base import Performance, PerformanceResponsibleStaff, PerformancePosition
from .phase_service import PhaseService


class PerformanceService:
    @staticmethod
    @transaction.atomic
    def create_performance(
        title: str,
        created_by: User,
        responsible_staff_data: list[dict] = None,
        description: str = '',
    ) -> Performance:
        """
        公演を新規作成する。

        Args:
            title: 公演名
            created_by: 作成者
            responsible_staff_data: 担当者リスト [{'user_id': int, 'position_id': int}, ...]
            description: 備考（省略可）

        Returns:
            作成した Performance インスタンス
        """
        # 公演の作成
        performance = Performance.objects.create(
            title=title,
            created_by=created_by,
            description=description,
        )

        # 担当者の登録
        if responsible_staff_data:
            for item in responsible_staff_data:
                user = User.objects.get(pk=item['user_id'])
                position = PerformancePosition.objects.get(pk=item['position_id'])
                PerformanceResponsibleStaff.objects.create(
                    performance=performance,
                    user=user,
                    position=position
                )

        return performance

    @staticmethod
    def get_performance_list(user: User):
        """公演一覧を取得する（工程の最小日（開始日）の降順）"""
        from django.db.models import Min

        return (
            Performance.objects.annotate(
                db_start_date=Min('phases__suggested_date')
            )
            .prefetch_related('phases')
            .order_by('-db_start_date', '-created_at')
        )

    @staticmethod
    def get_master_data():
        """公演作成に必要なマスタデータを取得する"""
        # スタッフとして登録された有効なユーザーのみを order 順で取得
        users = (
            User.objects.select_related('profile')
            .filter(profile__is_staff=True, is_active=True)
            .order_by('profile__order', 'profile__family_name', 'profile__given_name', 'username')
        )
        positions = PerformancePosition.objects.all().order_by('order', 'name')
        return users, positions
