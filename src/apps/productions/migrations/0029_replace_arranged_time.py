from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productions', '0028_add_arranged_time_and_is_manager_added'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='vehicleassignment',
            name='arranged_time',
        ),
        migrations.AddField(
            model_name='vehicleassignment',
            name='arranged_departure_time',
            field=models.TimeField(blank=True, null=True, verbose_name='管理配車時間'),
        ),
        migrations.AddField(
            model_name='vehicleassignment',
            name='arranged_arrival_time',
            field=models.TimeField(blank=True, null=True, verbose_name='管理到着時間'),
        ),
    ]
