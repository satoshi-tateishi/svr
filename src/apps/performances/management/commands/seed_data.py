"""
seed_data — 開発・デモ用ダミーデータ生成コマンド

既存のスタッフユーザー・車輌データを使用して、
公演 10件とそれに紐づく工程・車両申請・人員申請のダミーデータを生成する。

使い方:
  call_command('seed_data')             # データがない場合のみ実行
  call_command('seed_data', force=True) # 既存の公演データを削除して再生成
"""

import random
from datetime import date, datetime, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.performances.exceptions import ConflictError
from apps.performances.models.base import Performance, PerformancePosition
from apps.performances.models.vehicle import Vehicle
from apps.performances.services.assignment_service import AssignmentService
from apps.performances.services.performance_service import PerformanceService
from apps.performances.services.phase_service import PhaseService
from apps.performances.services.vehicle_service import VehicleService

# 稽古場・劇場の候補リスト
REHEARSAL_VENUES = [
    '新宿村スタジオ',
    'すみだパークスタジオ',
    '芸能花伝舎',
    '水天宮ピット',
    'SIMスタジオ',
    'リーホースタジオ',
    'シアターコクーン稽古場',
    'ファンファーレスタジオ',
    '森下スタジオ',
]

THEATERS = [
    'パルコ劇場',
    '紀伊國屋ホール',
    '紀伊國屋サザンシアター',
    'THEATER MILANO-Za',
    '東京芸術劇場',
    '赤坂ACTシアター',
    '青年館ホール',
    '世田谷パブリックシアター',
    "I'M A SHOW",
    '新国立劇場',
    'パルテノン多摩',
    'よみうり大手町ホール',
    '座・高円寺',
    'よみうりホール',
    'シアタークリエ',
]

# 10公演の設定
# ※ idx=2 と 3 は load_in_date を同一日（2026-06-10）にして車両申請の日程重複を再現
PERFORMANCE_CONFIGS = [
    {
        'title': '春の劇場公演 ～夜明けの声～',
        'premiere_date': date(2026, 4, 10),
        'run_days': 3,
        'has_tour': False,
        'is_large': False,
    },
    {
        'title': '東京リアリティシアター vol.12',
        'premiere_date': date(2026, 5, 8),
        'run_days': 5,
        'has_tour': False,
        'is_large': False,
    },
    {
        # 劇場仕込み: 2026-06-10（#4 と重複）
        'title': '夏の陣2026',
        'premiere_date': date(2026, 6, 12),
        'run_days': 2,
        'has_tour': False,
        'is_large': False,
        'load_in_date': date(2026, 6, 10),
    },
    {
        # 劇場仕込み: 2026-06-10（#3 と重複 → 車両競合デモ）
        'title': 'COMPANY produce #8 「静かな革命」',
        'premiere_date': date(2026, 6, 19),
        'run_days': 3,
        'has_tour': False,
        'is_large': False,
        'load_in_date': date(2026, 6, 10),
    },
    {
        'title': '真夏の夜の喜劇',
        'premiere_date': date(2026, 7, 17),
        'run_days': 4,
        'has_tour': False,
        'is_large': True,
    },
    {
        'title': 'SOUND DRAMA PROJECT 2026',
        'premiere_date': date(2026, 8, 14),
        'run_days': 3,
        'has_tour': True,
        'tour_days': 8,
        'is_large': False,
    },
    {
        'title': '秋の演劇祭 参加作品「境界線」',
        'premiere_date': date(2026, 9, 18),
        'run_days': 5,
        'has_tour': False,
        'is_large': False,
    },
    {
        'title': 'ツアー公演2026 ─ 再会の地へ',
        'premiere_date': date(2026, 10, 16),
        'run_days': 2,
        'has_tour': True,
        'tour_days': 10,
        'is_large': True,
    },
    {
        'title': '冬の特別公演「記憶の声」',
        'premiere_date': date(2026, 11, 13),
        'run_days': 4,
        'has_tour': False,
        'is_large': False,
    },
    {
        'title': '年末特別公演2026',
        'premiere_date': date(2026, 12, 11),
        'run_days': 3,
        'has_tour': False,
        'is_large': False,
    },
]

# 工程インデックス（PhaseService.TEMPLATE_STEPS の順）ごとの人員人数範囲
# (最小, 最大)、None = 人員割当なし
STAFF_COUNT_BY_PHASE_IDX = {
    0: (1, 3),  # 機材作り（荷積み相当）
    1: (2, 2),  # 稽古場仕込み
    3: (2, 2),  # 稽古場バラシ
    4: (3, 4),  # 劇場仕込み
    5: (3, 4),  # 舞台稽古
    7: (3, 4),  # 劇場バラシ
    9: (1, 3),  # 最終荷降ろし
}


def _make_aware(d: date, hour: int, minute: int = 0) -> datetime:
    """日付と時刻（時・分）からタイムゾーン付き datetime を生成する"""
    return timezone.make_aware(datetime(d.year, d.month, d.day, hour, minute))


def _time_hour(t) -> int:
    """TimeField 値（datetime.time または "HH:MM" 文字列）から時を返す"""
    if t is None:
        return 9
    if isinstance(t, str):
        return int(t.split(':')[0])
    return t.hour


def _time_minute(t) -> int:
    """TimeField 値（datetime.time または "HH:MM" 文字列）から分を返す"""
    if t is None:
        return 0
    if isinstance(t, str):
        return int(t.split(':')[1])
    return t.minute


def _t(hour: int, minute: int = 0) -> str:
    """TimeField 用の時刻文字列を返す（例: "09:00"）"""
    return f'{hour:02d}:{minute:02d}'


def _build_phase_data(config: dict, rng: random.Random) -> list:
    """
    公演設定から PhaseService に渡す 10工程分のデータリストを生成する。

    Returns:
        list of (start_date, end_date, start_time_str, end_time_str)
        ※ TEMPLATE_STEPS と同じ順序:
        0:機材作り, 1:稽古場仕込み, 2:稽古, 3:稽古場バラシ, 4:劇場仕込み,
        5:舞台稽古, 6:本番, 7:劇場バラシ, 8:ツアー, 9:最終荷降ろし
    """
    premiere = config['premiere_date']
    run_days = config.get('run_days', 3)
    has_tour = config.get('has_tour', False)
    tour_days = config.get('tour_days', 7)

    # 本番期間
    premiere_end = premiere + timedelta(days=run_days - 1)

    # 劇場バラシ
    load_out_date = premiere_end + timedelta(days=1)

    # ツアー・最終荷降ろし
    if has_tour:
        tour_start = load_out_date + timedelta(days=2)
        tour_end = tour_start + timedelta(days=tour_days - 1)
        final_unload = tour_end + timedelta(days=1)
    else:
        tour_start = tour_end = final_unload = None

    # 劇場仕込み（load_in_date 指定があればその日を使用）
    if 'load_in_date' in config:
        load_in_start = config['load_in_date']
        load_in_end = min(load_in_start + timedelta(days=1), premiere - timedelta(days=1))
    else:
        load_in_start = premiere - timedelta(days=2)
        load_in_end = premiere - timedelta(days=1)

    stage_rehearsal = premiere - timedelta(days=1)
    rehearsal_load_out = premiere - timedelta(days=7)
    rehearsal_end = premiere - timedelta(days=8)
    rehearsal_start = premiere - timedelta(days=34)
    rehearsal_load_in = premiere - timedelta(days=35)
    equipment_start = premiere - timedelta(days=42)
    equipment_end = premiere - timedelta(days=40)

    # 工程ごとの時間帯（ランダム）
    r_load_in_h = rng.choice([8, 9, 10])  # 稽古場搬入（午前中）
    r_load_out_h = rng.choice([18, 19, 20])  # 稽古場搬出
    load_in_h = rng.choice([9, 10])  # 劇場搬入
    load_out_h = rng.choice([18, 19, 20, 21])  # 劇場搬出
    final_h = rng.choice([11, 12, 13, 14])  # 最終荷降ろし

    return [
        (equipment_start, equipment_end, None, None),
        (
            rehearsal_load_in,
            rehearsal_load_in,
            _t(r_load_in_h),
            _t(min(r_load_in_h + rng.choice([3, 4]), 14)),
        ),
        (rehearsal_start, rehearsal_end, None, None),
        (
            rehearsal_load_out,
            rehearsal_load_out,
            _t(r_load_out_h),
            _t(min(r_load_out_h + rng.choice([2, 3]), 22)),
        ),
        (load_in_start, load_in_end, _t(load_in_h), _t(min(load_in_h + 9, 22))),
        (stage_rehearsal, stage_rehearsal, '10:00', '19:00'),
        (premiere, premiere_end, '13:00', '21:00'),
        (
            load_out_date,
            load_out_date,
            _t(load_out_h),
            _t(min(load_out_h + rng.choice([2, 3]), 23)),
        ),
        (tour_start, tour_end, None, None),
        (
            final_unload,
            final_unload,
            _t(final_h) if final_unload else None,
            _t(min(final_h + rng.choice([2, 3]), 17)) if final_unload else None,
        ),
    ]


class Command(BaseCommand):
    help = 'デモ・開発用ダミーデータ（公演・工程・車両申請・人員申請）を生成する'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='既存の公演データを全削除して再生成する',
        )
        parser.add_argument(
            '--append',
            action='store_true',
            help='既存の公演データを残したまま追加生成する',
        )

    def handle(self, *args, **options):
        force = options['force']
        append = options['append']

        # ─── 既存データチェック ───
        if Performance.objects.exists():
            if force:
                self.stdout.write('既存の公演データを削除中...')
                Performance.objects.all().delete()
            elif not append:
                self.stderr.write(
                    self.style.WARNING(
                        '既に公演データが存在します。'
                        '--force で全削除して再生成、'
                        '--append で既存データを残したまま追加できます。'
                    )
                )
                return

        # ─── 既存スタッフユーザー取得 ───
        users = list(
            User.objects.filter(profile__is_active_staff=True, is_active=True)
            .select_related('profile')
            .order_by('profile__order', 'profile__family_name', 'profile__given_name', 'username')
        )
        if not users:
            raise CommandError(
                'アクティブなスタッフ（UserProfile.is_active_staff=True）が存在しません。'
                '先にスタッフユーザーを登録してください。'
            )
        self.stdout.write(f'スタッフ {len(users)} 名を取得しました。')
        # サウンドデザイナー選択プール: ソート上位 12 名 / チーフ選択プール: それ以外
        sd_pool = users[:12]
        chief_pool = users[12:]

        # ─── 既存車輌取得 ───
        main_vehicle = Vehicle.objects.filter(name='新音車', is_active=True).first()
        external_vehicle = Vehicle.objects.filter(ownership_type='external', is_active=True).first()
        if not main_vehicle:
            self.stderr.write(
                self.style.WARNING('"新音車" が見つかりません。車両割当をスキップします。')
            )
        if not external_vehicle:
            self.stderr.write(
                self.style.WARNING('外注車輌が見つかりません。大型案件にも新音車を使用します。')
            )

        # ─── ポジション（公演担当者用）取得または作成 ───
        pos_sd, _ = PerformancePosition.objects.get_or_create(
            name='サウンドデザイナー', defaults={'order': 10}
        )
        pos_chief, _ = PerformancePosition.objects.get_or_create(
            name='チーフ', defaults={'order': 20}
        )

        # ─── 10公演を順番に生成 ───
        self.stdout.write('')
        for i, config in enumerate(PERFORMANCE_CONFIGS):
            self._seed_performance(
                config=config,
                users=users,
                sd_pool=sd_pool,
                chief_pool=chief_pool,
                main_vehicle=main_vehicle,
                external_vehicle=external_vehicle,
                pos_sd=pos_sd,
                pos_chief=pos_chief,
            )
            self.stdout.write(f'  [{i + 1:2d}/10] {config["title"]}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('シーダー完了：10公演のダミーデータを生成しました。'))

    # ─────────────────────────────────────────────────────────────────────────
    # 内部メソッド
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_performance(
        self,
        config: dict,
        users: list,
        sd_pool: list,
        chief_pool: list,
        main_vehicle,
        external_vehicle,
        pos_sd,
        pos_chief,
    ) -> None:
        """1公演分のデータ（工程・車両申請・人員申請）を生成する"""
        premiere = config['premiere_date']
        # 再現性のあるランダム生成（公演タイトルと日付でシード）
        rng = random.Random(premiere.toordinal() + hash(config['title']) % 10000)

        rehearsal_venue = rng.choice(REHEARSAL_VENUES)
        theater = rng.choice(THEATERS)
        is_large = config.get('is_large', False)
        vehicle = (external_vehicle or main_vehicle) if is_large else main_vehicle

        # 担当者選択: サウンドデザイナーは上位 12 名から、チーフはそれ以外から
        sd_user = rng.choice(sd_pool) if sd_pool else users[0]
        chief_user = rng.choice(chief_pool) if chief_pool else rng.choice(sd_pool)
        responsible_staff_data = [{'user_id': sd_user.id, 'position_id': pos_sd.id}]
        if chief_user != sd_user:
            responsible_staff_data.append({'user_id': chief_user.id, 'position_id': pos_chief.id})

        # 公演を作成
        perf = PerformanceService.create_performance(
            title=config['title'],
            created_by=sd_user,
            responsible_staff_data=responsible_staff_data,
        )

        # 10工程を一括展開
        phase_data = _build_phase_data(config, rng)
        phases = PhaseService.apply_production_template(perf, phase_data)

        # 各工程の処理
        stage_rehearsal_count = None
        for idx, phase in enumerate(phases):
            slot = phase.slots.first()
            if slot is None:
                continue
            # 本番（初日）: 舞台稽古の申請人数 − 1人
            override = None
            if idx == 6 and stage_rehearsal_count is not None:
                override = max(stage_rehearsal_count - 1, 1)
            self._process_phase(
                idx=idx,
                phase=phase,
                slot=slot,
                users=users,
                vehicle=vehicle,
                rehearsal_venue=rehearsal_venue,
                theater=theater,
                perf=perf,
                rng=rng,
                override_count=override,
            )
            # 舞台稽古の確定人数を保存（本番工程で使用）
            if idx == 5:
                stage_rehearsal_count = slot.requested_staff_count

    def _process_phase(
        self,
        idx: int,
        phase,
        slot,
        users: list,
        vehicle,
        rehearsal_venue: str,
        theater: str,
        perf,
        rng: random.Random,
        override_count: int | None = None,
    ) -> None:
        """1工程の人員設定・車両申請・人員申請を処理する"""
        start_date = phase.suggested_start_date
        start_time = phase.suggested_start_time
        end_time = phase.suggested_end_time

        # ─── 人員設定・StaffAssignment ───
        staff_range = STAFF_COUNT_BY_PHASE_IDX.get(idx)
        if override_count is not None:
            count = override_count
        elif staff_range:
            count = rng.randint(*staff_range)
        else:
            count = None
        if count and start_date:
            slot.requested_staff_count = count
            slot.save()

            occ_start = _make_aware(start_date, _time_hour(start_time), _time_minute(start_time))
            occ_end = _make_aware(
                start_date,
                _time_hour(end_time) if end_time else 18,
                _time_minute(end_time) if end_time else 0,
            )
            if occ_end <= occ_start:
                occ_end = occ_start + timedelta(hours=5)

            # スタッフをランダムに選択してアサイン（ConflictError はスキップ）
            candidates = list(users)
            rng.shuffle(candidates)
            assigned = 0
            for user in candidates:
                if assigned >= count:
                    break
                try:
                    AssignmentService.confirm_staff_assignment(slot, user, occ_start, occ_end)
                    assigned += 1
                except ConflictError:
                    continue

        # ─── VehicleOperation（車両申請）───
        if vehicle is None or not start_date:
            return

        op_config = self._get_vehicle_op_config(idx, rehearsal_venue, theater)
        if op_config is None:
            return

        title, route_from, route_to = op_config
        req_start = _make_aware(start_date, _time_hour(start_time), _time_minute(start_time))
        req_end = _make_aware(
            start_date,
            _time_hour(end_time) if end_time else 18,
            _time_minute(end_time) if end_time else 0,
        )
        if req_end <= req_start:
            req_end = req_start + timedelta(hours=5)

        op = VehicleService.create_operation(
            performance=perf,
            title=title,
            requested_start=req_start,
            requested_end=req_end,
            route_from=route_from,
            route_to=route_to,
        )
        op = VehicleService.confirm_schedule(op, req_start, req_end)

        try:
            AssignmentService.confirm_vehicle_assignment(op, vehicle)
        except ConflictError:
            # 別公演と日程が重複している場合（意図的なデモデータ）
            self.stderr.write(
                self.style.WARNING(
                    f'  ⚠ 車両競合: {phase.name}（{start_date}）の車両割当をスキップ'
                    f'（{vehicle.name} が他の公演と重複）'
                )
            )

    @staticmethod
    def _get_vehicle_op_config(
        idx: int, rehearsal_venue: str, theater: str
    ) -> tuple[str, str, str] | None:
        """
        工程インデックスに対応する (title, route_from, route_to) を返す。
        車両申請が不要な工程は None を返す。
        """
        if idx == 1:  # 稽古場仕込み
            return f'搬入（{rehearsal_venue}）', '赤堤倉庫', rehearsal_venue
        if idx == 3:  # 稽古場バラシ
            return f'搬出（{rehearsal_venue}）', rehearsal_venue, '赤堤倉庫'
        if idx == 4:  # 劇場仕込み
            return f'搬入（{theater}）', '赤堤倉庫', theater
        if idx == 7:  # 劇場バラシ
            return f'搬出（{theater}）', theater, '赤堤倉庫'
        if idx == 9:  # 最終荷降ろし
            return f'最終荷降ろし（{theater}→すみだ倉庫）', theater, 'すみだ倉庫'
        return None
