from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0011_vehiclerequest_route_to'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerequest',
            name='arrival_requested_time',
            field=models.TimeField(blank=True, null=True, verbose_name='到着希望時間'),
        ),
    ]
