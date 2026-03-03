from django.contrib.auth.models import User
from django.db import models

from .base import Performance, PerformancePosition, PhaseSlot


class PerformanceFreelanceRate(models.Model):
    """
    フリーランス単価履歴（期間重複禁止・上書き禁止）

    同一 user × position × performance で期間が重複する登録は禁止。
    一度登録した単価は変更できない（修正が必要な場合は valid_until を設定して新規作成）。
    """

    performance = models.ForeignKey(
        Performance,
        on_delete=models.CASCADE,
        related_name='freelance_rates',
        verbose_name='公演',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='freelance_rates',
        verbose_name='スタッフ',
    )
    position = models.ForeignKey(
        PerformancePosition,
        on_delete=models.CASCADE,
        related_name='freelance_rates',
        verbose_name='ポジション',
    )
    unit_price = models.PositiveIntegerField(verbose_name='単価（円）')
    allowance = models.PositiveIntegerField(default=0, verbose_name='手当（円）')
    valid_from = models.DateField(verbose_name='適用開始日')
    valid_until = models.DateField(null=True, blank=True, verbose_name='適用終了日')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='登録日時')

    class Meta:
        verbose_name = 'フリーランス単価'
        verbose_name_plural = 'フリーランス単価一覧'
        ordering = ['-valid_from']

    def __str__(self):
        return (
            f'{self.user.get_full_name() or self.user.username} '
            f'/ {self.position.name} / ¥{self.unit_price:,}'
        )

    @property
    def total_per_day(self):
        """1日あたりの合計金額（単価 + 手当）"""
        return self.unit_price + self.allowance


class StaffAssignment(models.Model):
    """
    人員割当

    占有時間（集合〜解散）を保持し、ダブルブッキング判定に使用する（Week 3 で実装）。
    Lock 時に applied_* フィールドへ単価・金額をスナップショット保存する（Week 5 で実装）。
    """

    phase_slot = models.ForeignKey(
        PhaseSlot,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='人員枠',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='staff_assignments',
        verbose_name='スタッフ',
    )
    position = models.ForeignKey(
        PerformancePosition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_assignments',
        verbose_name='ポジション',
    )
    # 占有時間（集合〜解散、バッファ込み）— ダブルブッキング判定用（Week 3）
    occupied_start = models.DateTimeField(verbose_name='占有開始（集合）')
    occupied_end = models.DateTimeField(verbose_name='占有終了（解散）')

    # 🔒 Lock 時スナップショット（Week 5 で確定する。それ以前は null）
    applied_unit_price = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='確定単価（円）'
    )
    applied_allowance_total = models.PositiveIntegerField(
        default=0, verbose_name='確定手当合計（円）'
    )
    applied_total_amount = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='確定合計金額（円）'
    )
    applied_position_name = models.CharField(
        max_length=100, blank=True, verbose_name='確定ポジション名'
    )
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='確定日時')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '人員割当'
        verbose_name_plural = '人員割当一覧'

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f'{self.phase_slot.phase.name} - {name}'

    @property
    def is_locked(self):
        return self.locked_at is not None
