from django.contrib.auth.models import User
from django.db import models


class Performance(models.Model):
    """公演・案件"""

    title = models.CharField(max_length=200, verbose_name='公演タイトル')
    start_date = models.DateField(verbose_name='開始日')
    end_date = models.DateField(verbose_name='終了日')
    description = models.TextField(blank=True, default='', verbose_name='備考')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_performances',
        verbose_name='作成者',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='作成日時')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新日時')

    class Meta:
        verbose_name = '公演'
        verbose_name_plural = '公演一覧'
        ordering = ['-start_date']

    def __str__(self):
        return self.title

    @property
    def has_phases(self):
        """テンプレート展開済みかどうかを返す"""
        return self.phases.exists()


class Phase(models.Model):
    """工程（テンプレートから自動生成される 1〜9 の工程）"""

    performance = models.ForeignKey(
        Performance,
        on_delete=models.CASCADE,
        related_name='phases',
        verbose_name='公演',
    )
    name = models.CharField(max_length=100, verbose_name='工程名')  # 例: "1. 機材作り"
    order = models.PositiveIntegerField(verbose_name='順序')
    suggested_date = models.DateField(null=True, blank=True, verbose_name='予定日（目安）')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '工程'
        verbose_name_plural = '工程一覧'
        ordering = ['order']

    def __str__(self):
        return f'{self.performance.title} - {self.name}'


class PhaseSlot(models.Model):
    """人員の要求枠（希望人数 vs 実際のアサイン数を管理）"""

    class Status(models.TextChoices):
        DRAFT = 'draft', '下書き'
        ASSIGNED = 'assigned', '割当済'
        LOCKED = 'locked', '確定'

    phase = models.ForeignKey(
        Phase,
        on_delete=models.CASCADE,
        related_name='slots',
        verbose_name='工程',
    )
    requested_staff_count = models.PositiveIntegerField(default=0, verbose_name='希望人数')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='ステータス',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '人員枠'
        verbose_name_plural = '人員枠一覧'

    def __str__(self):
        return f'{self.phase.name} 人員枠'

    @property
    def actual_staff_count(self):
        """実際のアサイン人数（StaffAssignment の数）"""
        return self.assignments.count()

    @property
    def is_understaffed(self):
        """希望人数に対してアサインが不足しているか"""
        return self.actual_staff_count < self.requested_staff_count


class PerformancePosition(models.Model):
    """公演内のポジション（役割）"""

    performance = models.ForeignKey(
        Performance,
        on_delete=models.CASCADE,
        related_name='positions',
        verbose_name='公演',
    )
    name = models.CharField(max_length=100, verbose_name='ポジション名')

    class Meta:
        verbose_name = 'ポジション'
        verbose_name_plural = 'ポジション一覧'

    def __str__(self):
        return f'{self.performance.title} - {self.name}'
