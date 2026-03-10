"""
ProcessType の初期データ投入マイグレーション。
templates.py で使用する全 slug を get_or_create で冪等に作成する。
"""

from django.db import migrations

PROCESS_TYPES = [
    # slug, name, category, color, order
    ('kizai-standby',   '機材スタンバイ',   'rehearsal',   '#718096', 10),
    ('rehearsal-setup', '稽古場仕込み',     'rehearsal',   '#4299e1', 20),
    ('rehearsal',       '稽古',             'rehearsal',   '#48bb78', 30),
    ('rehearsal-strike','稽古場バラシ',     'rehearsal',   '#718096', 40),
    ('theatre-setup',   '劇場仕込み',       'venue',       '#ed8936', 50),
    ('stage-rehearsal', '劇場舞台稽古',     'venue',       '#9f7aea', 60),
    ('opening-night',   '初日',             'performance', '#e53e3e', 70),
    ('performance',     '本番',             'performance', '#e53e3e', 80),
    ('theatre-strike',  '劇場バラシ',       'venue',       '#718096', 90),
    ('theatre-unload',  '劇場荷降ろし',     'logistics',   '#a0aec0', 100),
    ('warehouse-load',  '倉庫荷積み',       'warehouse',   '#a0aec0', 110),
    ('warehouse-unload','倉庫荷降ろし',     'warehouse',   '#a0aec0', 120),
    ('final-unload',    '最終荷降ろし',     'warehouse',   '#a0aec0', 130),
    ('transport',       '移動',             'logistics',   '#a0aec0', 140),
    ('reload',          '積み替え',         'logistics',   '#a0aec0', 150),
    ('recording',       '録音',             'other',       '#4299e1', 160),
    ('press',           '記者会見',         'other',       '#4299e1', 170),
]


def seed_process_types(apps, schema_editor):
    ProcessType = apps.get_model('productions', 'ProcessType')
    for slug, name, category, color, order in PROCESS_TYPES:
        ProcessType.objects.get_or_create(
            slug=slug,
            defaults={
                'name': name,
                'category': category,
                'color': color,
                'order': order,
                'is_active': True,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('productions', '0015_productionmember'),
    ]

    operations = [
        migrations.RunPython(seed_process_types, noop),
    ]
