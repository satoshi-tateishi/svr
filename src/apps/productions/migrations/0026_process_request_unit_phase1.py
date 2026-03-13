import django.db.models.deletion
from django.db import migrations, models


def forwards(apps, schema_editor):
    ProcessDay = apps.get_model('productions', 'ProcessDay')
    ProcessRequestUnit = apps.get_model('productions', 'ProcessRequestUnit')
    StaffRequest = apps.get_model('productions', 'StaffRequest')
    VehicleRequest = apps.get_model('productions', 'VehicleRequest')

    unit_map = {}
    for day in ProcessDay.objects.all().order_by('process_id', 'date', 'order', 'id'):
        unit = ProcessRequestUnit.objects.create(
            process_id=day.process_id,
            process_type_id=day.process_type_id,
            order=day.order,
            work_date=day.date,
            location=day.location,
            start_time=day.start_time,
            end_time=day.end_time,
            note=day.note,
            setup_label=day.setup_label,
        )
        unit_map[day.pk] = unit.pk

    for vehicle_request in VehicleRequest.objects.exclude(process_day_id=None):
        vehicle_request.process_request_unit_id = unit_map.get(vehicle_request.process_day_id)
        vehicle_request.save(update_fields=['process_request_unit'])

    for staff_request in StaffRequest.objects.exclude(process_day_id=None):
        staff_request.process_request_unit_id = unit_map.get(staff_request.process_day_id)
        staff_request.save(update_fields=['process_request_unit'])


def backwards(apps, schema_editor):
    StaffRequest = apps.get_model('productions', 'StaffRequest')
    VehicleRequest = apps.get_model('productions', 'VehicleRequest')

    StaffRequest.objects.update(process_request_unit_id=None)
    VehicleRequest.objects.update(process_request_unit_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0025_rename_final_performance_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcessRequestUnit',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    ),
                ),
                ('order', models.PositiveIntegerField(default=0, verbose_name='表示順')),
                ('work_date', models.DateField(blank=True, null=True, verbose_name='実施日')),
                (
                    'location',
                    models.CharField(blank=True, default='', max_length=200, verbose_name='場所'),
                ),
                ('start_time', models.TimeField(blank=True, null=True, verbose_name='開始時間')),
                ('end_time', models.TimeField(blank=True, null=True, verbose_name='終了時間')),
                ('note', models.TextField(blank=True, verbose_name='申請単位備考')),
                (
                    'setup_label',
                    models.CharField(
                        blank=True,
                        choices=[
                            ('setup_staff', '仕込み人数'),
                            ('stage_rehearsal', '舞台稽古'),
                            ('opening_night', '初日'),
                        ],
                        default='',
                        max_length=20,
                        verbose_name='劇場仕込みラベル',
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='作成日時')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新日時')),
                (
                    'process',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='request_units',
                        to='productions.process',
                        verbose_name='工程ブロック',
                    ),
                ),
                (
                    'process_type',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to='productions.processtype',
                        verbose_name='工程種別',
                    ),
                ),
            ],
            options={
                'verbose_name': '申請単位',
                'verbose_name_plural': '申請単位',
                'ordering': ['work_date', 'order', 'start_time', 'id'],
            },
        ),
        migrations.AddField(
            model_name='staffrequest',
            name='process_request_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='staff_requests',
                to='productions.processrequestunit',
                verbose_name='申請単位',
            ),
        ),
        migrations.AddField(
            model_name='vehiclerequest',
            name='process_request_unit',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vehicle_request',
                to='productions.processrequestunit',
                verbose_name='申請単位',
            ),
        ),
        migrations.AlterField(
            model_name='staffrequest',
            name='process_day',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='staff_requests',
                to='productions.processday',
                verbose_name='工程タスク',
            ),
        ),
        migrations.AlterField(
            model_name='vehiclerequest',
            name='process_day',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vehicle_requests',
                to='productions.processday',
                verbose_name='工程タスク',
            ),
        ),
        migrations.AlterField(
            model_name='vehiclerequest',
            name='requested_vehicle',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='production_vehicle_requests',
                to='performances.vehicle',
                verbose_name='申請車両',
            ),
        ),
        migrations.AddIndex(
            model_name='processrequestunit',
            index=models.Index(
                fields=['process', 'work_date'], name='productions_process_6e2bc1_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='processrequestunit',
            index=models.Index(fields=['process', 'order'], name='productions_process_2fb720_idx'),
        ),
        migrations.RunPython(forwards, backwards),
    ]
