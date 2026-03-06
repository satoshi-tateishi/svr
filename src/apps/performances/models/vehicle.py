from django.contrib.auth.models import User
from django.db import models

from .base import Performance


class Vehicle(models.Model):
    """車輌マスタ"""

    class VehicleType(models.TextChoices):
        TRUCK_2T = '2t', '2tトラック'
        TRUCK_2TL = '2tL', '2tロングトラック'
        TRUCK_4T = '4t', '4tトラック'
        TRUCK_11T = '11t', '11tトラック'
        HIACE = 'hiace', 'ハイエース'
        KEIBAN = 'keiban', '軽バン'
        CAR = 'car', '乗用車'
        OTHER = 'other', 'その他'

    class OwnershipType(models.TextChoices):
        COMPANY = 'company', '自社'
        PERSONAL = 'personal', '自家用'
        EXTERNAL = 'external', '外注'

    name = models.CharField(max_length=100, verbose_name='車輌名')
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, verbose_name='車種')
    ownership_type = models.CharField(
        max_length=20, choices=OwnershipType.choices, verbose_name='所有区分'
    )
    is_active = models.BooleanField(default=True, verbose_name='有効')
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')
    note = models.TextField(blank=True, default='', verbose_name='備考')

    class Meta:
        verbose_name = '車輌'
        verbose_name_plural = '車輌マスタ'
        ordering = ['order', 'name']

    def __str__(self):
        return (
            f'{self.name}（{self.get_vehicle_type_display()}／{self.get_ownership_type_display()}）'
        )

    @property
    def is_external(self):
        """外注車輌か（ダブルブッキング判定で除外対象）"""
        return self.ownership_type == self.OwnershipType.EXTERNAL


class VehicleOperation(models.Model):
    """
    運行工程

    希望（requested_*）と確定（scheduled_*）を別フィールドで保持する。
    制作の申請値（requested_*）は確定後も上書きせず、乖離を可視化する。
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', '下書き'
        ASSIGNED = 'assigned', '割当済'
        LOCKED = 'locked', '確定'

    performance = models.ForeignKey(
        Performance,
        on_delete=models.CASCADE,
        related_name='vehicle_operations',
        verbose_name='公演',
    )
    title = models.CharField(max_length=100, verbose_name='運行タイトル')

    # 希望（制作の申請値 — 上書き禁止・乖離分析の基準値）
    requested_start = models.DateTimeField(verbose_name='希望開始')
    requested_end = models.DateTimeField(verbose_name='希望終了')

    # 確定（管理者が設定する実際の配車時間）
    scheduled_start = models.DateTimeField(null=True, blank=True, verbose_name='確定開始')
    scheduled_end = models.DateTimeField(null=True, blank=True, verbose_name='確定終了')

    route_from = models.CharField(max_length=200, verbose_name='出発地')
    route_to = models.CharField(max_length=200, verbose_name='到着地')
    requested_staff_count = models.PositiveIntegerField(default=0, verbose_name='希望助手人数')
    description = models.TextField(blank=True, default='', verbose_name='内容説明')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='ステータス',
    )
    
    # 論理削除・操作履歴
    is_active = models.BooleanField(default=True, verbose_name='有効')
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='削除日時')
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_vehicle_operations',
        verbose_name='削除実行者',
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_vehicle_operations',
        verbose_name='最終更新者',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '運行工程'
        verbose_name_plural = '運行工程一覧'
        ordering = ['requested_start']

    def __str__(self):
        return f'{self.performance.title} - {self.title}'

    @property
    def schedule_drift_minutes(self):
        """希望開始と確定開始の乖離（分）。確定前は None を返す"""
        if self.scheduled_start is None:
            return None
        delta = self.scheduled_start - self.requested_start
        return int(delta.total_seconds() / 60)


class VehicleAssignment(models.Model):
    """
    配車割当

    Lock 時に applied_* フィールドへ原価・請求額をスナップショット保存する（Week 5 で実装）。
    """

    vehicle_operation = models.ForeignKey(
        VehicleOperation,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='運行工程',
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='車輌',
    )
    driver_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='driving_assignments',
        verbose_name='ドライバー',
    )
    is_external_driver = models.BooleanField(default=False, verbose_name='外注ドライバー')

    # 🔒 Lock 時スナップショット（Week 5 で確定する。それ以前は null）
    applied_cost_amount = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='外注費・ドライバー費（確定）'
    )
    applied_sales_amount = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='案件請求額（確定）'
    )
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='確定日時')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '配車割当'
        verbose_name_plural = '配車割当一覧'

    def __str__(self):
        return f'{self.vehicle_operation.title} - {self.vehicle.name}'

    @property
    def is_locked(self):
        return self.locked_at is not None
