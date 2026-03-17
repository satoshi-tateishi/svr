from datetime import datetime, time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Max, Min

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

    @property
    def actual_start_date(self):
        """表示用開始日。申請単位日付を優先し、なければ ProcessDay / start_date を返す。"""
        # ProductionListView で annotate された値を優先（N+1 防止）
        process_min = getattr(self, 'process_min_date', None)
        if process_min is None:
            process_min = ProcessRequestUnit.objects.filter(process__production=self).aggregate(
                Min('work_date')
            )['work_date__min']
            if process_min is None:
                process_min = ProcessDay.objects.filter(process__production=self).aggregate(
                    Min('date')
                )['date__min']
        return process_min or self.start_date

    @property
    def actual_end_date(self):
        """表示用終了日。申請単位日付を優先し、なければ ProcessDay / end_date を返す。"""
        process_max = getattr(self, 'process_max_date', None)
        if process_max is None:
            process_max = ProcessRequestUnit.objects.filter(process__production=self).aggregate(
                Max('work_date')
            )['work_date__max']
            if process_max is None:
                process_max = ProcessDay.objects.filter(process__production=self).aggregate(
                    Max('date')
                )['date__max']
        return process_max or self.end_date


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

PROCESS_SETUP_LABEL_CHOICES = [
    ('setup_staff', '仕込み'),
    ('stage_rehearsal', '舞台稽古'),
    ('opening_night', '初日'),
]


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
    """公演ブロック（稽古場仕込み、劇場仕込み、旅荷積み等）"""

    production = models.ForeignKey(
        Production, on_delete=models.CASCADE, related_name='processes', verbose_name='公演'
    )
    title = models.CharField(
        max_length=100, verbose_name='ブロック名', help_text='例: 稽古場仕込み、劇場仕込み'
    )
    block_key = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='ブロックキー',
        help_text='テンプレート定義のキー（rehearsal_setup等）',
    )
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')
    sumida_required = models.BooleanField(null=True, blank=True, verbose_name='すみだ便必要')
    assistant_required = models.BooleanField(null=True, blank=True, verbose_name='助っ人必要')
    final_performance_load_out_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='最終公演地搬出日',
    )
    final_performance_location = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='最終公演地',
    )

    class Meta:
        verbose_name = '工程ブロック'
        verbose_name_plural = '工程ブロック'
        ordering = ['order']
        # 【2】同一公演内でのブロック名の重複を禁止
        unique_together = ['production', 'title']

    def __str__(self):
        return f'{self.production.title} - {self.title}'


class ProcessRequestUnit(models.Model):
    """工程ブロック内の申請単位"""

    class UnitType(models.TextChoices):
        TRANSPORT = 'transport', '車両便申請'
        STAFFING = 'staffing', '人員申請'

    process = models.ForeignKey(
        Process, on_delete=models.CASCADE, related_name='request_units', verbose_name='工程ブロック'
    )
    # 第1段階では既存の BLOCK_PROCESS_TYPE_MAP / ProcessType 前提との整合維持のため保持する。
    process_type = models.ForeignKey(ProcessType, on_delete=models.PROTECT, verbose_name='工程種別')
    unit_type = models.CharField(
        max_length=20,
        choices=UnitType.choices,
        default=UnitType.STAFFING,
        verbose_name='申請単位種別',
    )
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')
    work_date = models.DateField(null=True, blank=True, verbose_name='実施日')
    location = models.CharField(max_length=200, blank=True, default='', verbose_name='場所')
    start_time = models.TimeField(null=True, blank=True, verbose_name='開始時間')
    end_time = models.TimeField(null=True, blank=True, verbose_name='終了時間')
    note = models.TextField(blank=True, verbose_name='申請単位備考')
    setup_label = models.CharField(
        max_length=20,
        choices=PROCESS_SETUP_LABEL_CHOICES,
        blank=True,
        default='',
        verbose_name='劇場仕込みラベル',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='作成日時')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新日時')

    class Meta:
        verbose_name = '申請単位'
        verbose_name_plural = '申請単位'
        ordering = ['work_date', 'order', 'start_time', 'id']
        indexes = [
            models.Index(fields=['process', 'work_date']),
            models.Index(fields=['process', 'order']),
        ]

    def __str__(self):
        date_str = self.work_date.isoformat() if self.work_date else '未定'
        return f'{date_str} {self.process.title}'


class ProcessDay(models.Model):
    """個別の工程（タスク単位）"""

    SETUP_LABEL_CHOICES = PROCESS_SETUP_LABEL_CHOICES

    process = models.ForeignKey(
        Process, on_delete=models.CASCADE, related_name='days', verbose_name='工程ブロック'
    )
    process_type = models.ForeignKey(ProcessType, on_delete=models.PROTECT, verbose_name='工程種別')
    date = models.DateField(null=True, blank=True, verbose_name='実施日')
    location = models.CharField(max_length=200, blank=True, default='', verbose_name='場所')

    start_time = models.TimeField(null=True, blank=True, verbose_name='開始時間')
    end_time = models.TimeField(null=True, blank=True, verbose_name='終了時間')

    # 順序安定のためのフィールド
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')

    note = models.TextField(blank=True, verbose_name='備考')

    # 劇場仕込みブロック専用: その日の仕込みフェーズ（theatre_setup のみ意味を持つ）
    setup_label = models.CharField(
        max_length=20,
        choices=SETUP_LABEL_CHOICES,
        blank=True,
        default='',
        verbose_name='劇場仕込みラベル',
    )

    class Meta:
        verbose_name = '工程タスク'
        verbose_name_plural = '工程タスク'
        ordering = ['date', 'order', 'start_time']
        # 【3】ブロック内での日付検索を高速化するため複合インデックスを追加
        indexes = [
            models.Index(fields=['process', 'date']),
        ]

    def __str__(self):
        date_str = self.date.isoformat() if self.date else '未定'
        return f'{date_str} {self.process_type.name} ({self.process.title})'

    @property
    def start_datetime(self):
        if self.date is None:
            return None
        return datetime.combine(self.date, self.start_time or time.min)

    @property
    def end_datetime(self):
        if self.date is None:
            return None
        return datetime.combine(self.date, self.end_time or time.max)


class StaffRequest(models.Model):
    """人員申請"""

    process_day = models.ForeignKey(
        ProcessDay,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='staff_requests',
        verbose_name='工程タスク',
    )
    process_request_unit = models.ForeignKey(
        ProcessRequestUnit,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='staff_requests',
        verbose_name='申請単位',
    )
    position = models.ForeignKey(Position, on_delete=models.PROTECT, verbose_name='ポジション')

    quantity = models.PositiveIntegerField(default=1, verbose_name='希望人数')
    include_self = models.BooleanField(default=False, verbose_name='本人を含む')

    # 空欄の場合は工程時間（ProcessDay の start_time / end_time）に準ずる
    start_time = models.TimeField(null=True, blank=True, verbose_name='開始時間')
    end_time = models.TimeField(null=True, blank=True, verbose_name='終了時間')

    note = models.TextField(blank=True, verbose_name='備考')

    class Meta:
        verbose_name = '人員申請'
        verbose_name_plural = '人員申請'
        # 同一ポジションを時間帯別に複数申請できるため unique_together は設けない
        ordering = ['position__order', 'start_time']

    def __str__(self):
        return f'{self.position.name} x {self.quantity}'


class VehicleRequest(models.Model):
    """車両申請"""

    class RequestKind(models.TextChoices):
        LOAD_IN = 'load_in', '搬入'
        PICKUP = 'pickup', '引き取り'
        LOADING = 'loading', '荷積み'
        PRELOAD = 'preload', '積み置き'
        UNLOADING = 'unloading', '荷降ろし'
        OTHER = 'other', 'その他'

    process_day = models.ForeignKey(
        ProcessDay,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='vehicle_requests',
        verbose_name='工程タスク',
    )
    process_request_unit = models.OneToOneField(
        ProcessRequestUnit,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='vehicle_request',
        verbose_name='申請単位',
    )
    requested_vehicle = models.ForeignKey(
        'performances.Vehicle',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='production_vehicle_requests',
        verbose_name='申請車両',
    )
    request_kind = models.CharField(
        max_length=20,
        choices=RequestKind.choices,
        default=RequestKind.LOAD_IN,
        verbose_name='申請種別',
    )
    # 工程日と配車日が異なる場合に指定（空白=工程日に準ずる）
    date = models.DateField(null=True, blank=True, verbose_name='配車日')
    requested_time = models.TimeField(null=True, blank=True, verbose_name='配車希望時間')
    arrival_requested_time = models.TimeField(null=True, blank=True, verbose_name='到着希望時間')
    route_from = models.CharField(max_length=200, blank=True, default='', verbose_name='出発地')
    location_from = models.ForeignKey(
        'locations.Location',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='departures',
        verbose_name='出発地（マスタ）',
    )
    route_to = models.CharField(max_length=200, blank=True, default='', verbose_name='目的地')
    location_to = models.ForeignKey(
        'locations.Location',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='destinations',
        verbose_name='目的地（マスタ）',
    )
    note = models.TextField(blank=True, default='', verbose_name='備考')
    is_manager_added = models.BooleanField(default=False, verbose_name='管理側追加便')
    # 荷役人数申請（車両申請がある場合のみ有効）
    loading_qty = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='荷積み人数')
    loading_include_self = models.BooleanField(default=False, verbose_name='荷積み本人含む')
    unloading_qty = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='荷降ろし人数'
    )
    unloading_include_self = models.BooleanField(default=False, verbose_name='荷降ろし本人含む')

    class Meta:
        verbose_name = '車両申請'
        verbose_name_plural = '車両申請'

    @property
    def effective_date(self):
        """配車日。date フィールドが設定されていればそちらを優先する。"""
        if self.date:
            return self.date
        if self.process_request_unit_id:
            return self.process_request_unit.work_date
        if self.process_day_id:
            return self.process_day.date
        return None

    @property
    def effective_production(self):
        """公演。process_day → process_request_unit の順で取得。"""
        if self.process_day_id:
            return self.process_day.process.production
        if self.process_request_unit_id:
            return self.process_request_unit.process.production
        return None

    @property
    def effective_process_type(self):
        """工程種別。process_day → process_request_unit の順で取得。"""
        if self.process_day_id:
            return self.process_day.process_type
        if self.process_request_unit_id:
            return self.process_request_unit.process_type
        return None

    def __str__(self):
        return self.requested_vehicle.name if self.requested_vehicle else '未定車両'


class VehicleAssignment(models.Model):
    """車両手配（管理側）"""

    class Status(models.TextChoices):
        PENDING = 'pending', '未対応'
        REVIEWING = 'reviewing', '調整中'
        CONFIRMED = 'confirmed', '確定'

    vehicle_request = models.OneToOneField(
        VehicleRequest,
        on_delete=models.CASCADE,
        related_name='assignment',
        verbose_name='車両申請',
    )
    assigned_vehicle = models.ForeignKey(
        'performances.Vehicle',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='production_vehicle_assignments',
        verbose_name='手配車両',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='管理状態',
    )
    # arranged_time を廃止し、出発・到着の2フィールドに分離
    arranged_departure_time = models.TimeField(null=True, blank=True, verbose_name='管理配車時間')
    arranged_arrival_time = models.TimeField(null=True, blank=True, verbose_name='管理到着時間')
    note = models.TextField(blank=True, default='', verbose_name='管理メモ')
    departure_note = models.TextField(blank=True, default='', verbose_name='管理備考（配車）')
    arrival_note = models.TextField(blank=True, default='', verbose_name='管理備考（到着）')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '車両手配'
        verbose_name_plural = '車両手配一覧'
        ordering = [
            'vehicle_request__process_request_unit__work_date',
            'vehicle_request__requested_time',
        ]

    def __str__(self):
        return f'{self.vehicle_request} - {self.get_status_display()}'


class ProductionMember(models.Model):
    """公演担当者（サウンドデザイナー・チーフ等）"""

    class Role(models.TextChoices):
        SOUND_DESIGNER = 'sound_designer', 'サウンドデザイナー'
        CHIEF = 'chief', 'チーフ'

    production = models.ForeignKey(
        Production,
        on_delete=models.CASCADE,
        related_name='members',
        verbose_name='公演',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='production_memberships',
        verbose_name='担当者',
    )
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        verbose_name='役割',
    )
    start_date = models.DateField(null=True, blank=True, verbose_name='担当開始日')
    end_date = models.DateField(null=True, blank=True, verbose_name='担当終了日')
    note = models.TextField(blank=True, default='', verbose_name='備考')
    created_at = models.DateTimeField(auto_now_add=True)

    # role の表示順は Role.choices 定義順（sound_designer → chief）に従う。
    # DB の ordering は role の文字列ソートになるため、view 側で明示的に並べる。
    # （将来 role が増えた場合も Role.choices の列挙順に従って表示できる）
    class Meta:
        verbose_name = '公演担当者'
        verbose_name_plural = '公演担当者一覧'
        ordering = ['start_date']

    def __str__(self):
        name = self.user.profile.full_name if hasattr(self.user, 'profile') else self.user.username
        return f'{self.get_role_display()} - {name}'
