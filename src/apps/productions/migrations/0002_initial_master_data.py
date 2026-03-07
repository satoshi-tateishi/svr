from django.db import migrations

def create_initial_data(apps, schema_editor):
    ProcessType = apps.get_model('productions', 'ProcessType')
    Position = apps.get_model('productions', 'Position')

    # ProcessTypes
    process_types = [
        {'name': '機材準備', 'slug': 'standby', 'color': '#718096', 'order': 10},
        {'name': '荷積み/荷降ろし', 'slug': 'load', 'color': '#4a5568', 'order': 20},
        {'name': '稽古', 'slug': 'rehearsal', 'color': '#3182ce', 'order': 30},
        {'name': '劇場仕込み', 'slug': 'theater_setup', 'color': '#38a169', 'order': 40},
        {'name': '本番', 'slug': 'performance', 'color': '#e53e3e', 'order': 50},
        {'name': 'バラシ', 'slug': 'strike', 'color': '#d69e2e', 'order': 60},
        {'name': '倉庫作業', 'slug': 'warehouse', 'color': '#805ad5', 'order': 70},
    ]
    for pt in process_types:
        ProcessType.objects.get_or_create(slug=pt['slug'], defaults=pt)

    # Positions
    positions = [
        {'name': 'チーフ', 'slug': 'chief', 'order': 10},
        {'name': 'サブチーフ', 'slug': 'sub_chief', 'order': 20},
        {'name': '一般スタッフ', 'slug': 'general', 'order': 30},
        {'name': 'ドライバー', 'slug': 'driver', 'order': 40},
        {'name': '特殊機材担当', 'slug': 'specialist', 'order': 50},
    ]
    for pos in positions:
        Position.objects.get_or_create(slug=pos['slug'], defaults=pos)

def remove_initial_data(apps, schema_editor):
    ProcessType = apps.get_model('productions', 'ProcessType')
    Position = apps.get_model('productions', 'Position')
    ProcessType.objects.all().delete()
    Position.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_initial_data, remove_initial_data),
    ]
