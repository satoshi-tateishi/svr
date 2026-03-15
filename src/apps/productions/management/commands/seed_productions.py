"""
seed_productions — productions アプリ用ダミーデータ生成コマンド

既存のスタッフユーザー・車輌データを使用して、
公演 10件とそれに紐づく工程ブロック・申請単位（ProcessRequestUnit）・
車両申請・車両手配・人員申請のダミーデータを生成する。

対象テーブル:
  - productions_production              （公演）
  - productions_productionmember        （公演担当者一覧）
  - productions_process                 （工程ブロック）
  - productions_processrequestunit      （申請単位）
  - productions_vehiclerequest          （車両申請）
  - productions_vehicleassignment       （車両手配一覧）
  - productions_staffrequest            （人員申請）

使い方:
  call_command('seed_productions')              # データがない場合のみ実行
  call_command('seed_productions', force=True)  # 既存データを全削除して再生成
  call_command('seed_productions', append=True) # 既存データを保持したまま追加
"""

import random
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.performances.models.vehicle import Vehicle
from apps.productions.models import (
    Position,
    Process,
    ProcessDay,
    ProcessRequestUnit,
    ProcessType,
    Production,
    ProductionMember,
    StaffRequest,
    VehicleAssignment,
    VehicleRequest,
)

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

# 10公演の定義
# ※ idx=2 と 3 は load_in_date を同一日（2026-06-10）にして車両申請の日程重複を再現
PRODUCTION_CONFIGS = [
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
        # 劇場仕込み: 2026-06-10（#3 と重複 → 車両手配 REVIEWING）
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

# ProcessType マスターデータ（slug, name, category, color, order）
PROCESS_TYPES_DATA = [
    ('rehearsal-setup', '稽古場仕込み', 'rehearsal', '#38a169', 1),
    ('rehearsal-strike', '稽古場バラシ', 'rehearsal', '#e53e3e', 2),
    ('theatre-setup', '劇場仕込み', 'venue', '#3182ce', 3),
    ('theatre-strike', '劇場バラシ', 'venue', '#dd6b20', 4),
    ('warehouse-load', '旅荷積み', 'logistics', '#805ad5', 5),
    ('warehouse-unload', '旅荷降ろし', 'logistics', '#319795', 6),
]

# Position マスターデータ（slug, name, order）
POSITIONS_DATA = [
    ('setup-crew', '仕込みスタッフ', 1),
    ('strike-crew', 'バラシスタッフ', 2),
    ('loading', '荷積み担当', 3),
    ('unloading', '荷降ろし担当', 4),
    ('helper', '助っ人', 5),
]


def _t(hour: int, minute: int = 0) -> time:
    """時刻オブジェクトを生成するヘルパー"""
    return time(hour, minute)


def _plus_1h(t: time) -> time:
    """時刻に1時間加算する（23:00 → 0:00 とならないよう 23:59 でクランプ）"""
    dt = datetime.combine(date.min, t) + timedelta(hours=1)
    return min(dt.time(), time(23, 59))


def _compute_dates(config: dict, rng: random.Random) -> dict:
    """公演設定から各工程の日付を計算する"""
    premiere = config['premiere_date']
    has_tour = config.get('has_tour', False)
    tour_days = config.get('tour_days', 7)

    # 劇場バラシは初日から7〜24日後
    load_out_date = premiere + timedelta(days=rng.randint(7, 24))

    if has_tour:
        travel_load_date = load_out_date + timedelta(days=1)
        tour_start = load_out_date + timedelta(days=2)
        tour_end = tour_start + timedelta(days=tour_days - 1)
        travel_unload_date = tour_end + timedelta(days=1)
    else:
        travel_load_date = None
        travel_unload_date = None

    # 劇場仕込みは稽古場バラシ（premiere - 7日）の翌日がデフォルト
    load_in_date = config.get('load_in_date', premiere - timedelta(days=6))

    return {
        'rehearsal_load_in': premiere - timedelta(days=35),
        'rehearsal_load_out': premiere - timedelta(days=7),
        'load_in': load_in_date,
        'stage_rehearsal': premiere - timedelta(days=1),
        'premiere': premiere,
        'load_out': load_out_date,
        'travel_load': travel_load_date,
        'travel_unload': travel_unload_date,
    }


class Command(BaseCommand):
    help = 'productions アプリ用ダミーデータ（公演・工程・車両申請・人員申請）を生成する'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true', help='既存の公演データを全削除して再生成する'
        )
        parser.add_argument(
            '--append', action='store_true', help='既存データを保持したまま追加生成する'
        )

    def handle(self, *args, **options):
        force = options['force']
        append = options['append']

        # ─── 既存データチェック ───
        if Production.objects.exists():
            if force:
                self.stdout.write('既存の公演データを削除中...')
                Production.objects.all().delete()
            elif not append:
                self.stderr.write(
                    self.style.WARNING(
                        '既に公演データが存在します。'
                        '--force で全削除して再生成、'
                        '--append で既存データを保持したまま追加できます。'
                    )
                )
                return

        # ─── マスターデータ整備 ───
        process_types = self._setup_process_types()
        positions = self._setup_positions()

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

        # ─── 10公演を生成 ───
        # 劇場仕込みの (date, vehicle_id) を追跡して競合を検出する
        seen_load_in: set[tuple] = set()

        self.stdout.write('')
        for i, config in enumerate(PRODUCTION_CONFIGS):
            self._seed_production(
                config=config,
                idx=i,
                users=users,
                sd_pool=sd_pool,
                chief_pool=chief_pool,
                main_vehicle=main_vehicle,
                external_vehicle=external_vehicle,
                process_types=process_types,
                positions=positions,
                seen_load_in=seen_load_in,
            )
            self.stdout.write(f'  [{i + 1:2d}/10] {config["title"]}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('シーダー完了：10公演のダミーデータを生成しました。'))

    # ─────────────────────────────────────────────────────────────────────────

    def _setup_process_types(self) -> dict[str, ProcessType]:
        """ProcessType マスターデータを get_or_create で整備する"""
        result = {}
        for slug, name, category, color, order in PROCESS_TYPES_DATA:
            pt, _ = ProcessType.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'category': category, 'color': color, 'order': order},
            )
            result[slug] = pt
        return result

    def _setup_positions(self) -> dict[str, Position]:
        """Position マスターデータを get_or_create で整備する"""
        result = {}
        for slug, name, order in POSITIONS_DATA:
            pos, _ = Position.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'order': order},
            )
            result[slug] = pos
        return result

    def _seed_production(
        self,
        config: dict,
        idx: int,
        users: list,
        sd_pool: list,
        chief_pool: list,
        main_vehicle,
        external_vehicle,
        process_types: dict,
        positions: dict,
        seen_load_in: set,
    ) -> None:
        """1公演分のデータを生成する"""
        premiere = config['premiere_date']
        rng = random.Random(premiere.toordinal() + hash(config['title']) % 10000)
        dates = _compute_dates(config, rng)
        is_large = config.get('is_large', False)
        vehicle = (external_vehicle or main_vehicle) if is_large else main_vehicle

        rehearsal_venue = rng.choice(REHEARSAL_VENUES)
        theater = rng.choice(THEATERS)

        # ─── Production 作成 ───
        production = Production.objects.create(
            code=f'P-{premiere:%Y%m%d}-{idx + 1:03d}',
            title=config['title'],
            created_by=(sd_pool[0] if sd_pool else users[0]),
        )

        # ─── ProductionMember 作成 ───
        sd_user = rng.choice(sd_pool) if sd_pool else users[0]
        chief_user = rng.choice(chief_pool) if chief_pool else rng.choice(sd_pool)
        ProductionMember.objects.create(
            production=production,
            user=sd_user,
            role=ProductionMember.Role.SOUND_DESIGNER,
        )
        if chief_user != sd_user:
            ProductionMember.objects.create(
                production=production,
                user=chief_user,
                role=ProductionMember.Role.CHIEF,
            )

        # ─── Process（工程ブロック）作成 ───
        has_tour = config.get('has_tour', False)
        blocks = [
            ('rehearsal_setup', '稽古場仕込み', 1),
            ('sumida_check', 'すみだものチェック', 2),
            ('kizai_standby', '本番機材スタンバイ', 3),
            ('rehearsal_strike', '稽古場バラシ', 4),
            ('theatre_setup', '劇場仕込み', 5),
            ('theatre_strike', '劇場バラシ', 6),
        ]
        if has_tour:
            blocks += [
                ('travel_load', '旅荷積み', 7),
                ('travel_unload', '旅荷降ろし', 8),
            ]

        for block_key, title, order in blocks:
            process = Process.objects.create(
                production=production,
                title=title,
                block_key=block_key,
                order=order,
            )
            self._populate_process(
                process=process,
                block_key=block_key,
                dates=dates,
                rehearsal_venue=rehearsal_venue,
                theater=theater,
                vehicle=vehicle,
                process_types=process_types,
                positions=positions,
                rng=rng,
                seen_load_in=seen_load_in,
            )

    def _populate_process(
        self,
        process: Process,
        block_key: str,
        dates: dict,
        rehearsal_venue: str,
        theater: str,
        vehicle,
        process_types: dict,
        positions: dict,
        rng: random.Random,
        seen_load_in: set,
    ) -> None:
        """工程ブロックに申請単位・車両申請・人員申請を生成する"""

        if block_key == 'sumida_check':
            process.sumida_required = True
            process.save(update_fields=['sumida_required'])
            return

        if block_key == 'kizai_standby':
            # views.py の _save_kizai_standby と同様に ProcessDay を使用
            process.assistant_required = True
            process.save(update_fields=['assistant_required'])
            pt = process_types.get('rehearsal-setup')
            if pt:
                day, _ = ProcessDay.objects.get_or_create(
                    process=process,
                    process_type=pt,
                    defaults={'order': 0},
                )
                StaffRequest.objects.get_or_create(
                    process_day=day,
                    position=positions['helper'],
                    defaults={'quantity': 1, 'include_self': True},
                )
            return

        if block_key == 'rehearsal_setup':
            d = dates['rehearsal_load_in']
            if d is None:
                return
            pt = process_types['rehearsal-setup']
            load_in_h = rng.choice([8, 9, 10])
            end_h = min(load_in_h + rng.choice([3, 4]), 14)

            # 車両申請単位
            tu = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.TRANSPORT,
                work_date=d,
                location=rehearsal_venue,
                order=1,
            )
            self._create_vehicle_request(
                tu, vehicle, 'load_in', '赤堤倉庫', rehearsal_venue, _t(load_in_h), seen_load_in
            )

            # 人員申請単位
            su = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.STAFFING,
                work_date=d,
                location=rehearsal_venue,
                start_time=_t(load_in_h),
                end_time=_t(end_h),
                order=2,
            )
            self._create_staff_request(su, positions['setup-crew'], 2)

        elif block_key == 'rehearsal_strike':
            d = dates['rehearsal_load_out']
            if d is None:
                return
            pt = process_types['rehearsal-strike']
            load_out_h = rng.choice([18, 19, 20])
            end_h = min(load_out_h + rng.choice([2, 3]), 22)

            # 車両申請単位
            tu = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.TRANSPORT,
                work_date=d,
                location=rehearsal_venue,
                order=1,
            )
            self._create_vehicle_request(
                tu, vehicle, 'loading', rehearsal_venue, '赤堤倉庫', _t(load_out_h), seen_load_in
            )

            # 人員申請単位
            su = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.STAFFING,
                work_date=d,
                location=rehearsal_venue,
                start_time=_t(load_out_h),
                end_time=_t(end_h),
                order=2,
            )
            self._create_staff_request(su, positions['strike-crew'], 2)

        elif block_key == 'theatre_setup':
            self._populate_theatre_setup(
                process, dates, theater, vehicle, process_types, positions, rng, seen_load_in
            )

        elif block_key == 'theatre_strike':
            d = dates['load_out']
            if d is None:
                return
            pt = process_types['theatre-strike']
            load_out_h = rng.choice([18, 19, 20, 21])
            end_h = min(load_out_h + rng.choice([2, 3]), 23)
            staff_count = rng.randint(3, 4)

            # 車両申請単位
            tu = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.TRANSPORT,
                work_date=d,
                location=theater,
                order=1,
            )
            self._create_vehicle_request(
                tu, vehicle, 'loading', theater, '赤堤倉庫', _t(load_out_h), seen_load_in
            )

            # 人員申請単位
            su = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.STAFFING,
                work_date=d,
                location=theater,
                start_time=_t(load_out_h),
                end_time=_t(end_h),
                order=2,
            )
            self._create_staff_request(su, positions['strike-crew'], staff_count)

        elif block_key == 'travel_load':
            d = dates['travel_load']
            if d is None:
                return
            pt = process_types['warehouse-load']
            load_h = rng.choice([9, 10, 11])
            end_h = min(load_h + rng.choice([2, 3]), 15)
            load_count = rng.randint(1, 3)

            # 車両申請単位
            tu = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.TRANSPORT,
                work_date=d,
                location='赤堤倉庫',
                order=1,
            )
            vr = VehicleRequest.objects.create(
                process_day=None,
                process_request_unit=tu,
                requested_vehicle=vehicle,
                request_kind='loading',
                route_from='赤堤倉庫',
                route_to=theater,
                requested_time=_t(load_h),
                arrival_requested_time=_plus_1h(_t(load_h)),
                loading_qty=2,
                loading_include_self=True,
                unloading_qty=2,
                unloading_include_self=True,
            )
            VehicleAssignment.objects.create(
                vehicle_request=vr,
                assigned_vehicle=vehicle,
                status=VehicleAssignment.Status.CONFIRMED,
            )

            # 人員申請単位
            su = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.STAFFING,
                work_date=d,
                location='赤堤倉庫',
                start_time=_t(load_h),
                end_time=_t(end_h),
                order=2,
            )
            self._create_staff_request(su, positions['loading'], load_count)

        elif block_key == 'travel_unload':
            d = dates['travel_unload']
            if d is None:
                return
            pt = process_types['warehouse-unload']
            unload_h = rng.choice([11, 12, 13, 14])
            end_h = min(unload_h + rng.choice([2, 3]), 17)
            unload_count = rng.randint(1, 3)

            # 車両申請単位
            tu = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.TRANSPORT,
                work_date=d,
                location='すみだ倉庫',
                order=1,
            )
            vr = VehicleRequest.objects.create(
                process_day=None,
                process_request_unit=tu,
                requested_vehicle=vehicle,
                request_kind='unloading',
                route_from=theater,
                route_to='すみだ倉庫',
                requested_time=_t(unload_h),
                arrival_requested_time=_plus_1h(_t(unload_h)),
                loading_qty=2,
                loading_include_self=True,
                unloading_qty=2,
                unloading_include_self=True,
            )
            VehicleAssignment.objects.create(
                vehicle_request=vr,
                assigned_vehicle=vehicle,
                status=VehicleAssignment.Status.CONFIRMED,
            )

            # 人員申請単位
            su = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.STAFFING,
                work_date=d,
                location='すみだ倉庫',
                start_time=_t(unload_h),
                end_time=_t(end_h),
                order=2,
            )
            self._create_staff_request(su, positions['unloading'], unload_count)

    def _populate_theatre_setup(
        self,
        process: Process,
        dates: dict,
        theater: str,
        vehicle,
        process_types: dict,
        positions: dict,
        rng: random.Random,
        seen_load_in: set,
    ) -> None:
        """劇場仕込みブロック: 搬入・仕込み2日・舞台稽古3日・初日の申請単位を生成する"""
        pt = process_types['theatre-setup']
        premiere = dates['premiere']
        load_in_d = dates['load_in']
        load_in_h = rng.choice([9, 10])
        setup_count = rng.randint(3, 4)
        sr_count = rng.randint(3, 4)

        # ① 車両申請単位（搬入日・transport）
        tu = ProcessRequestUnit.objects.create(
            process=process,
            process_type=pt,
            unit_type=ProcessRequestUnit.UnitType.TRANSPORT,
            work_date=load_in_d,
            location=theater,
            order=1,
        )
        self._create_vehicle_request(
            tu, vehicle, 'load_in', '赤堤倉庫', theater, _t(load_in_h), seen_load_in
        )

        # ② 劇場仕込み人員（setup_staff）: 舞台稽古開始前2日間
        #    premiere-5日, premiere-4日
        for i, delta in enumerate([5, 4]):
            su = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.STAFFING,
                work_date=premiere - timedelta(days=delta),
                location=theater,
                start_time=_t(load_in_h),
                end_time=_t(min(load_in_h + 9, 22)),
                setup_label='setup_staff',
                order=2 + i,
            )
            self._create_staff_request(su, positions['setup-crew'], setup_count)

        # ③ 舞台稽古人員（stage_rehearsal）: 初日前3日間
        #    premiere-3日, premiere-2日, premiere-1日
        for i, delta in enumerate([3, 2, 1]):
            su = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=ProcessRequestUnit.UnitType.STAFFING,
                work_date=premiere - timedelta(days=delta),
                location=theater,
                start_time=_t(10),
                end_time=_t(19),
                setup_label='stage_rehearsal',
                order=4 + i,
            )
            self._create_staff_request(su, positions['setup-crew'], sr_count)

        # ④ 初日人員（opening_night）: 舞台稽古人数 − 1名
        opening_count = max(sr_count - 1, 1)
        su_opening = ProcessRequestUnit.objects.create(
            process=process,
            process_type=pt,
            unit_type=ProcessRequestUnit.UnitType.STAFFING,
            work_date=premiere,
            location=theater,
            start_time=_t(11),
            end_time=_t(21),
            setup_label='opening_night',
            order=7,
        )
        self._create_staff_request(su_opening, positions['setup-crew'], opening_count)

    def _create_vehicle_request(
        self,
        unit: ProcessRequestUnit,
        vehicle,
        request_kind: str,
        route_from: str,
        route_to: str,
        requested_time: time,
        seen_load_in: set,
    ) -> None:
        """VehicleRequest と VehicleAssignment を生成する。競合時は REVIEWING にする。"""
        if vehicle is None:
            return

        vr = VehicleRequest.objects.create(
            process_day=None,
            process_request_unit=unit,
            requested_vehicle=vehicle,
            request_kind=request_kind,
            route_from=route_from,
            route_to=route_to,
            requested_time=requested_time,
            arrival_requested_time=_plus_1h(requested_time),
            loading_qty=2,
            loading_include_self=True,
            unloading_qty=2,
            unloading_include_self=True,
        )

        # 劇場仕込み（load_in）の日程競合チェック
        conflict_key = (unit.work_date, vehicle.pk)
        if request_kind == 'load_in' and route_to not in ('赤堤倉庫', 'すみだ倉庫'):
            if conflict_key in seen_load_in:
                status = VehicleAssignment.Status.REVIEWING
                self.stderr.write(
                    self.style.WARNING(
                        f'  ⚠ 車両競合: {unit.work_date}（{vehicle.name}）→ 調整中に設定'
                    )
                )
            else:
                seen_load_in.add(conflict_key)
                status = VehicleAssignment.Status.CONFIRMED
        else:
            status = VehicleAssignment.Status.CONFIRMED

        VehicleAssignment.objects.create(
            vehicle_request=vr,
            assigned_vehicle=vehicle,
            status=status,
        )

    @staticmethod
    def _create_staff_request(
        unit: ProcessRequestUnit,
        position: Position,
        quantity: int,
    ) -> StaffRequest:
        """StaffRequest を生成する（include_self=True）"""
        return StaffRequest.objects.create(
            process_day=None,
            process_request_unit=unit,
            position=position,
            quantity=quantity,
            include_self=True,
        )
