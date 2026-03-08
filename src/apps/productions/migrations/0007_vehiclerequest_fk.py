# Generated manually on 2026-03-08
# VehicleRequest.vehicle_name (CharField) を requested_vehicle (FK) に直接置換
# 事前に productions_vehiclerequest テーブルの件数が 0 件であることを確認済み

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('performances', '0001_initial'),
        ('productions', '0006_productiontemplate'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='vehiclerequest',
            name='vehicle_name',
        ),
        migrations.AddField(
            model_name='vehiclerequest',
            name='requested_vehicle',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='production_vehicle_requests',
                to='performances.vehicle',
                verbose_name='申請車両',
            ),
        ),
        migrations.AlterField(
            model_name='vehiclerequest',
            name='note',
            field=models.TextField(blank=True, default='', verbose_name='備考'),
        ),
        migrations.AlterUniqueTogether(
            name='vehiclerequest',
            unique_together={('process_day', 'requested_vehicle')},
        ),
    ]
