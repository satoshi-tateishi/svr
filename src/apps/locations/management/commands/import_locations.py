"""
import_locations — 場所マスタCSVインポートコマンド

使い方:
  call_command('import_locations')                         # デフォルトCSVパスから読み込み
  call_command('import_locations', csv='/path/to/file.csv')  # CSVパスを指定
  call_command('import_locations', force=True)             # 全削除して再インポート
"""

import csv
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.locations.models import Location

# デフォルトCSVパス（リポジトリ内 csv/ ディレクトリ）
DEFAULT_CSV_PATH = Path('/csv/locations.csv')


class Command(BaseCommand):
    help = '場所マスタCSVをインポートする'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            type=str,
            default=str(DEFAULT_CSV_PATH),
            help=f'CSVファイルのパス（デフォルト: {DEFAULT_CSV_PATH}）',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='既存データを全削除して再インポート',
        )

    def handle(self, *args, **options):
        csv_path = Path(options['csv'])
        force = options['force']

        if not csv_path.exists():
            self.stderr.write(self.style.ERROR(f'CSVファイルが見つかりません: {csv_path}'))
            return

        if not force and Location.objects.exists():
            count = Location.objects.count()
            self.stdout.write(
                self.style.WARNING(
                    f'場所マスタに既に {count} 件のデータが存在します。'
                    '再インポートするには --force オプションを指定してください。'
                )
            )
            return

        if force:
            deleted_count, _ = Location.objects.all().delete()
            self.stdout.write(f'既存データ {deleted_count} 件を削除しました。')

        locations = []
        with csv_path.open(encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                locations.append(
                    Location(
                        sort=int(row['sort']) if row['sort'] else 0,
                        name=row['name'],
                        furigana=row['furigana'] or '',
                        postal_code=row['postal_code'] or '',
                        address=row['address'] or '',
                        note=row['note'] or '',
                        is_active=row['is_active'] == '1',
                        created_at=timezone.make_aware(datetime.fromisoformat(row['created_at'])),
                        updated_at=timezone.make_aware(datetime.fromisoformat(row['updated_at'])),
                    )
                )

        Location.objects.bulk_create(locations)
        self.stdout.write(
            self.style.SUCCESS(f'場所マスタを {len(locations)} 件インポートしました。')
        )
