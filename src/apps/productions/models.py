from datetime import datetime, time

from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models

# =========================
# 公演
# =========================


class Production(models.Model):
    """公演プロジェクト"""

    code = models.CharField(
        max_length=50, unique=True, verbose_name='公演コード', help_text='例: 2026-PROD-001'
    )
    title = models.CharField(max_length=200, verbose_name='公演タイトル')
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='created_productions', verbose_name='作成者'
    )
    # 【1】日付フィールドを nullable に変更
    start_date = models.DateField(null=True, blank=True, verbose_name='開始日')
    end_date = models.DateField(null=True, blank=True, verbose_name='終了日')

    note = models.TextField(blank=True, verbose_name='備考')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='作成日時')

    class Meta:
        verbose_name = '公演'
        verbose_name_plural = '公演'

    def __str__(self):
        return f'[{self.code}] {self.title}'


class ProductionHoliday(models.Model):
    """休演日"""

    production = models.ForeignKey(
        Production, on_delete=models.CASCADE, related_name='holidays', verbose_name='公演'
    )
    date = models.DateField(verbose_name='休演日')
    note = models.CharField(max_length=100, blank=True, verbose_name='備考')

    class Meta:
        verbose_name = '休演日'
        verbose_name_plural = '休演日'
        unique_together = ['production', 'date']


# =========================
# マスター関連
# =========================


class ProcessType(models.Model):
    """工程種別マスター（劇場仕込み、本番、バラシ、荷降ろし等）"""

    CATEGORY_CHOICES = [
        ('rehearsal', '稽古場関連'),
        ('venue', '劇場関連'),
        ('warehouse', '倉庫関連'),
        ('logistics', '荷積み荷降ろし・輸送関連'),
        ('performance', '本番関連'),
        ('other', 'その他'),
    ]
    name = models.CharField(max_length=100, verbose_name='工程種別名')
    slug = models.SlugField(max_length=50, unique=True, verbose_name='識別スラッグ')
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name='カテゴリー'
    )

    # ガントチャート用のカラー設定
    color = models.CharField(
        max_length=7,
        default='#3182ce',
        verbose_name='表示色',
        validators=[RegexValidator(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')],
        help_text='カラーコード（例: #3182ce）',
    )

    order = models.PositiveIntegerField(default=0, verbose_name='表示順')
    is_active = models.BooleanField(default=True, verbose_name='有効')

    class Meta:
        verbose_name = '工程種別'
        verbose_name_plural = '工程種別'
        ordering = ['order']

    def __str__(self):
        return self.name


class Position(models.Model):
    """担当ポジションマスター"""

    name = models.CharField(max_length=100, verbose_name='ポジション名')
    slug = models.SlugField(max_length=50, unique=True, verbose_name='識別スラッグ')
    description = models.TextField(blank=True, verbose_name='説明')

    order = models.PositiveIntegerField(default=0, verbose_name='表示順')

    class Meta:
        verbose_name = 'ポジション'
        verbose_name_plural = 'ポジション'
        ordering = ['order']

    def __str__(self):
        return self.name


# =========================
# 工程・申請
# =========================


class ProductionTemplate(models.Model):
    """工程構成のテンプレートプリセット"""

    name = models.CharField(max_length=100, verbose_name='テンプレート名')
    description = models.TextField(blank=True, verbose_name='説明')

    # production_setup の instances と同じ構造を保存
    template_data = models.JSONField(verbose_name='テンプレートデータ')

    is_active = models.BooleanField(default=True, verbose_name='有効')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='作成日時')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新日時')

    class Meta:
        verbose_name = '工程テンプレート'
        verbose_name_plural = '工程テンプレート'
        ordering = ['name']

    def __str__(self):
        return self.name


class Process(models.Model):
    """公演ブロック（大阪公演、東京公演、移動、倉庫作業期間など）"""

    production = models.ForeignKey(
        Production, on_delete=models.CASCADE, related_name='processes', verbose_name='公演'
    )
    title = models.CharField(
        max_length=100, verbose_name='ブロック名', help_text='例: 大阪公演、稽古、倉庫作業'
    )
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')
    note = models.TextField(blank=True, verbose_name='備考')

    class Meta:
        verbose_name = '工程ブロック'
        verbose_name_plural = '工程ブロック'
        ordering = ['order']
        # 【2】同一公演内でのブロック名の重複を禁止
        unique_together = ['production', 'title']

    def __str__(self):
        return f'{self.production.title} - {self.title}'


class ProcessDay(models.Model):
    """個別の工程（タスク単位）"""

    process = models.ForeignKey(
        Process, on_delete=models.CASCADE, related_name='days', verbose_name='工程ブロック'
    )
    process_type = models.ForeignKey(ProcessType, on_delete=models.PROTECT, verbose_name='工程種別')
    date = models.DateField(verbose_name='実施日')
    location = models.CharField(max_length=200, blank=True, default='', verbose_name='場所')

    start_time = models.TimeField(null=True, blank=True, verbose_name='開始時間')
    end_time = models.TimeField(null=True, blank=True, verbose_name='終了時間')

    # 順序安定のためのフィールド
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')

    note = models.TextField(blank=True, verbose_name='備考')

    class Meta:
        verbose_name = '工程タスク'
        verbose_name_plural = '工程タスク'
        ordering = ['date', 'order', 'start_time']
        # 【3】ブロック内での日付検索を高速化するため複合インデックスを追加
        indexes = [
            models.Index(fields=['process', 'date']),
        ]

    def __str__(self):
        return f'{self.date} {self.process_type.name} ({self.process.title})'

    @property
    def start_datetime(self):
        return datetime.combine(self.date, self.start_time or time.min)

    @property
    def end_datetime(self):
        return datetime.combine(self.date, self.end_time or time.max)


class StaffRequest(models.Model):
    """人員申請"""

    process_day = models.ForeignKey(
        ProcessDay,
        on_delete=models.CASCADE,
        related_name='staff_requests',
        verbose_name='工程タスク',
    )
    position = models.ForeignKey(Position, on_delete=models.PROTECT, verbose_name='ポジション')

    quantity = models.PositiveIntegerField(default=1, verbose_name='必要人数')

    note = models.TextField(blank=True, verbose_name='備考')

    class Meta:
        verbose_name = '人員申請'
        verbose_name_plural = '人員申請'
        # 同一工程タスク・同一ポジションの重複を禁止
        unique_together = ['process_day', 'position']

    def __str__(self):
        return f'{self.position.name} x {self.quantity}'


class VehicleRequest(models.Model):
    """車両申請"""

    process_day = models.ForeignKey(
        ProcessDay,
        on_delete=models.CASCADE,
        related_name='vehicle_requests',
        verbose_name='工程タスク',
    )
    requested_vehicle = models.ForeignKey(
        'performances.Vehicle',
        on_delete=models.PROTECT,
        related_name='production_vehicle_requests',
        verbose_name='申請車両',
    )
    requested_time = models.TimeField(null=True, blank=True, verbose_name='配車希望時間')
    note = models.TextField(blank=True, default='', verbose_name='備考')

    class Meta:
        verbose_name = '車両申請'
        verbose_name_plural = '車両申請'

    def __str__(self):
        return self.requested_vehicle.name
