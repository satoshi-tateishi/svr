from django.contrib.auth.models import User
from django.db import models


class Performance(models.Model):
    """公演・案件"""

    title = models.CharField(max_length=200, verbose_name='公演名')
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
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def start_date(self):
        """全工程の最初の日から算出"""
        first_phase = (
            self.phases.exclude(suggested_date__isnull=True).order_by('suggested_date').first()
        )
        return first_phase.suggested_date if first_phase else None

    @property
    def end_date(self):
        """全工程の最後の日から算出"""
        last_phase = (
            self.phases.exclude(suggested_date__isnull=True).order_by('suggested_date').last()
        )
        return last_phase.suggested_date if last_phase else None

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

    @property
    def locked_assignment_count(self):
        """Lock 済みアサイン数（prefetch 済みキャッシュを利用）"""
        return sum(1 for a in self.assignments.all() if a.locked_at is not None)

    @property
    def locked_total_amount(self):
        """Lock 済みアサインの確定合計金額（prefetch 済みキャッシュを利用）"""
        return sum(
            (a.applied_total_amount or 0) for a in self.assignments.all() if a.locked_at is not None
        )


class PerformancePosition(models.Model):
    """ポジションマスタ（役割）"""

    name = models.CharField(max_length=100, unique=True, verbose_name='ポジション名')
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')

    class Meta:
        verbose_name = 'ポジションマスタ'
        verbose_name_plural = 'ポジションマスタ一覧'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class PerformanceResponsibleStaff(models.Model):
    """公演の担当者（複数人アサイン可能）"""

    performance = models.ForeignKey(
        Performance,
        on_delete=models.CASCADE,
        related_name='responsible_staff',
        verbose_name='公演',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='responsible_performances',
        verbose_name='担当者（氏名）',
    )
    position = models.ForeignKey(
        PerformancePosition,
        on_delete=models.PROTECT,
        related_name='responsible_staff',
        verbose_name='ポジション',
    )

    class Meta:
        verbose_name = '公演担当者'
        verbose_name_plural = '公演担当者一覧'
        unique_together = ('performance', 'user', 'position')

    def __str__(self):
        full_name = self.user.get_full_name() or self.user.username
        return f'{self.performance.title} - {full_name} ({self.position.name})'
