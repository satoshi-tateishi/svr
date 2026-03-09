from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0009_vehiclerequest_request_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerequest',
            name='route_from',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='出発地'),
        ),
    ]
