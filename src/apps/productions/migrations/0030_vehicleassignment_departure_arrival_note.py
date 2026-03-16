from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0029_replace_arranged_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicleassignment',
            name='departure_note',
            field=models.TextField(blank=True, default='', verbose_name='管理備考（配車）'),
        ),
        migrations.AddField(
            model_name='vehicleassignment',
            name='arrival_note',
            field=models.TextField(blank=True, default='', verbose_name='管理備考（到着）'),
        ),
    ]
