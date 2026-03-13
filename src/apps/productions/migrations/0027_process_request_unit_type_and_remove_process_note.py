from django.db import migrations, models

TRAVEL_BLOCK_KEYS = {'travel_load', 'travel_unload'}


def forwards(apps, schema_editor):
    Process = apps.get_model('productions', 'Process')
    ProcessRequestUnit = apps.get_model('productions', 'ProcessRequestUnit')
    StaffRequest = apps.get_model('productions', 'StaffRequest')
    VehicleRequest = apps.get_model('productions', 'VehicleRequest')

    for process in Process.objects.all():
        units = list(
            ProcessRequestUnit.objects.filter(process_id=process.pk).order_by(
                'work_date', 'order', 'start_time', 'id'
            )
        )
        next_order = 0
        for unit in units:
            vehicle_request = VehicleRequest.objects.filter(process_request_unit_id=unit.pk).first()
            staff_requests = list(StaffRequest.objects.filter(process_request_unit_id=unit.pk))
            has_transport = process.block_key in TRAVEL_BLOCK_KEYS or vehicle_request is not None
            has_staffing = process.block_key not in TRAVEL_BLOCK_KEYS and bool(staff_requests)

            if has_transport and has_staffing:
                original_note = unit.note
                original_setup_label = unit.setup_label
                unit.unit_type = 'transport'
                unit.order = next_order
                unit.note = ''
                unit.setup_label = ''
                unit.save(update_fields=['unit_type', 'order', 'note', 'setup_label'])
                next_order += 1

                staffing_unit = ProcessRequestUnit.objects.create(
                    process_id=unit.process_id,
                    process_type_id=unit.process_type_id,
                    unit_type='staffing',
                    order=next_order,
                    work_date=unit.work_date,
                    location=unit.location,
                    start_time=unit.start_time,
                    end_time=unit.end_time,
                    note=original_note,
                    setup_label=original_setup_label,
                )
                for staff_request in staff_requests:
                    staff_request.process_request_unit_id = staffing_unit.pk
                    staff_request.save(update_fields=['process_request_unit'])
                next_order += 1
            elif has_transport:
                unit.unit_type = 'transport'
                unit.order = next_order
                unit.note = ''
                unit.setup_label = ''
                unit.save(update_fields=['unit_type', 'order', 'note', 'setup_label'])
                next_order += 1
            else:
                unit.unit_type = 'staffing'
                unit.order = next_order
                unit.save(update_fields=['unit_type', 'order'])
                next_order += 1


def backwards(apps, schema_editor):
    ProcessRequestUnit = apps.get_model('productions', 'ProcessRequestUnit')
    for unit in ProcessRequestUnit.objects.all():
        unit.unit_type = 'staffing'
        unit.save(update_fields=['unit_type'])


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0026_process_request_unit_phase1'),
    ]

    operations = [
        migrations.AddField(
            model_name='processrequestunit',
            name='unit_type',
            field=models.CharField(
                choices=[('transport', '車両便申請'), ('staffing', '人員申請')],
                default='staffing',
                max_length=20,
                verbose_name='申請単位種別',
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='process',
            name='note',
        ),
    ]
