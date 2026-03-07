from django.db import migrations

def create_initial_process_types(apps, schema_editor):
    ProcessType = apps.get_model("productions", "ProcessType")
    
    # 既存データの削除（クリーンアップが必要な場合）
    # ProcessType.objects.all().delete()

    data = [
        # 準備・稽古
        {"name": "機材スタンバイ", "slug": "kizai-standby", "color": "#718096", "order": 10},
        {"name": "稽古場仕込み", "slug": "rehearsal-setup", "color": "#4A5568", "order": 20},
        {"name": "稽古", "slug": "rehearsal", "color": "#3182CE", "order": 30},
        {"name": "稽古場バラシ", "slug": "rehearsal-strike", "color": "#2D3748", "order": 40},
        
        # 劇場
        {"name": "劇場仕込み", "slug": "theatre-setup", "color": "#805AD5", "order": 50},
        {"name": "劇場舞台稽古", "slug": "stage-rehearsal", "color": "#B794F4", "order": 60},
        {"name": "初日", "slug": "opening-night", "color": "#E53E3E", "order": 70},
        {"name": "本番", "slug": "performance", "color": "#F56565", "order": 80},
        {"name": "劇場バラシ", "slug": "theatre-strike", "color": "#4A5568", "order": 90},
        
        # 物流
        {"name": "倉庫荷積み", "slug": "warehouse-load", "color": "#718096", "order": 100},
        {"name": "倉庫荷降ろし", "slug": "warehouse-unload", "color": "#718096", "order": 110},
        {"name": "劇場荷降ろし", "slug": "theatre-unload", "color": "#718096", "order": 120},
        {"name": "移動", "slug": "transport", "color": "#A0AEC0", "order": 130},
        {"name": "積み替え", "slug": "reload", "color": "#CBD5E0", "order": 140},
        {"name": "最終荷降ろし", "slug": "final-unload", "color": "#2D3748", "order": 150},
        
        # その他
        {"name": "録音", "slug": "recording", "color": "#38A169", "order": 160},
        {"name": "記者会見", "slug": "press", "color": "#38A169", "order": 170},
        {"name": "旅公演", "slug": "tour-performance", "color": "#D69E2E", "order": 180},
    ]

    for item in data:
        ProcessType.objects.update_or_create(
            slug=item["slug"],
            defaults={"name": item["name"], "color": item.get("color", "#3182CE"), "order": item["order"]}
        )

class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_initial_process_types),
    ]
