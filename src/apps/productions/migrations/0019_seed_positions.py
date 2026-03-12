"""
Position マスターデータ投入。
人員申請フォームで使用するポジション（積み込み・搬入・仕込み等）を get_or_create で冪等に作成する。
"""

from django.db import migrations

POSITIONS = [
    # slug, name, order
    ('loading', '積み込み', 10),
    ('carry-in', '搬入', 20),
    ('setup-crew', '仕込み', 30),
    ('strike-crew', 'バラシ', 40),
    ('unloading', '荷降ろし', 50),
    ('helper', '助っ人', 60),
]


def seed_positions(apps, schema_editor):
    Position = apps.get_model('productions', 'Position')
    for slug, name, order in POSITIONS:
        Position.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'order': order},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('productions', '0018_process_block_fields_staffrequest_include_self'),
    ]

    operations = [
        migrations.RunPython(seed_positions, noop),
    ]
