"""
DashboardQueryService — 乖離分析・不足警告クエリサービス

【設計原則】
- 申請（希望）と実態（確定）の差分を抽出し、管理者へ警告情報を提供する。
- 全メソッドは QuerySet を返す（呼び出し側でさらにフィルタ・ページネーション可能）。
- DB への書き込みは行わない（読み取り専用サービス）。
"""

from datetime import timedelta

from django.db.models import Count, F, Q
from django.utils import timezone

from apps.performances.models.base import PhaseSlot
from apps.performances.models.vehicle import VehicleOperation


class DashboardQueryService:
    @staticmethod
    def get_staffing_shortages():
        """
        人員不足スロット一覧を返す。

        requested_staff_count > 実際のアサイン数（StaffAssignment の件数）の
        PhaseSlot QuerySet を返す。

        Returns:
            QuerySet[PhaseSlot]: 人員が不足している PhaseSlot の一覧
                                  （actual_count アノテーション付き）
        """
        return (
            PhaseSlot.objects.annotate(actual_count=Count('assignments')).filter(
                actual_count__lt=F('requested_staff_count')
            )
        ).select_related('phase', 'phase__performance')

    @staticmethod
    def get_schedule_drifts(threshold_minutes: int = 30):
        """
        希望開始と確定開始が指定分数以上乖離している運行工程一覧を返す。

        乖離は絶対値で判定する（早まった場合・遅れた場合の両方を検出）。
        確定時間（scheduled_start）が未設定の工程は除外する。

        Args:
            threshold_minutes: 乖離とみなす閾値（分）。デフォルトは 30 分。

        Returns:
            QuerySet[VehicleOperation]: 乖離が閾値以上の運行工程一覧
        """
        threshold = timedelta(minutes=threshold_minutes)
        return (
            VehicleOperation.objects.exclude(scheduled_start__isnull=True)
            .filter(
                Q(scheduled_start__gte=F('requested_start') + threshold)
                | Q(scheduled_start__lte=F('requested_start') - threshold)
            )
            .select_related('performance')
        )

    @staticmethod
    def get_unlocked_past_slots():
        """
        日時が超過しているが Locked になっていない PhaseSlot 一覧を返す。

        Phase の suggested_start_date が本日より前であり、かつ
        PhaseSlot のステータスが LOCKED でない項目を返す。

        Returns:
            QuerySet[PhaseSlot]: Lock 漏れの可能性がある PhaseSlot の一覧
        """
        today = timezone.now().date()
        return (
            PhaseSlot.objects.filter(phase__suggested_start_date__lt=today)
            .exclude(status=PhaseSlot.Status.LOCKED)
            .select_related('phase', 'phase__performance')
        )
