from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0007_vehiclerequest_fk'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='vehiclerequest',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='vehiclerequest',
            name='quantity',
        ),
        migrations.AddField(
            model_name='vehiclerequest',
            name='requested_time',
            field=models.TimeField(blank=True, null=True, verbose_name='配車希望時間'),
        ),
    ]
