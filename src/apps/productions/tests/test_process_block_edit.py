import json
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.performances.models.vehicle import Vehicle
from apps.productions.models import (
    Position,
    Process,
    ProcessRequestUnit,
    ProcessType,
    Production,
    StaffRequest,
    VehicleRequest,
)


@pytest.mark.django_db
class TestProcessBlockEdit:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_user(username='block-editor', password='password')
        UserProfile.objects.filter(user=self.user).update(system_role=UserProfile.SystemRole.EDITOR)

        self.production = Production.objects.create(
            code='TEST-BLOCK-001',
            title='ブロック編集テスト',
            created_by=self.user,
        )
        for slug, name, category in [
            ('theatre-setup', '劇場仕込み', 'venue'),
            ('rehearsal-setup', '稽古場仕込み', 'rehearsal'),
            ('warehouse-load', '旅荷積み', 'logistics'),
            ('warehouse-unload', '旅荷降ろし', 'logistics'),
        ]:
            ProcessType.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'category': category},
            )

        self.setup_position, _ = Position.objects.get_or_create(
            slug='setup-crew',
            defaults={'name': '仕込み', 'order': 1},
        )
        self.vehicle = Vehicle.objects.create(
            name='新音車',
            vehicle_type=Vehicle.VehicleType.HIACE,
            ownership_type=Vehicle.OwnershipType.COMPANY,
            is_active=True,
            order=1,
        )
        self.theatre_process = Process.objects.create(
            production=self.production,
            title='劇場仕込み',
            block_key='theatre_setup',
            order=1,
        )
        self.rehearsal_process = Process.objects.create(
            production=self.production,
            title='稽古場仕込み',
            block_key='rehearsal_setup',
            order=2,
        )
        self.travel_load_process = Process.objects.create(
            production=self.production,
            title='旅荷積み',
            block_key='travel_load',
            order=3,
        )
        self.travel_unload_process = Process.objects.create(
            production=self.production,
            title='旅荷降ろし',
            block_key='travel_unload',
            order=4,
        )

    def _transport_unit(self, *, work_date='2026-04-01', vehicle_note='便メモ'):
        return {
            'unit_type': ProcessRequestUnit.UnitType.TRANSPORT,
            'work_date': work_date,
            'start_time': '',
            'end_time': '',
            'note': '',
            'setup_label': '',
            'vehicle': {
                'requested_vehicle_id': str(self.vehicle.pk),
                'request_kind': VehicleRequest.RequestKind.LOAD_IN,
                'requested_time': '09:30',
                'arrival_requested_time': '10:30',
                'route_from': '赤堤倉庫',
                'route_to': '劇場',
                'note': vehicle_note,
                'loading_qty': '2',
                'loading_include_self': True,
                'unloading_qty': '3',
                'unloading_include_self': True,
            },
            'staff_rows': [],
        }

    def _staffing_unit(
        self,
        *,
        work_date='2026-04-01',
        note='人員メモ',
        setup_label='opening_night',
    ):
        return {
            'unit_type': ProcessRequestUnit.UnitType.STAFFING,
            'work_date': work_date,
            'start_time': '08:30',
            'end_time': '18:00',
            'note': note,
            'setup_label': setup_label,
            'vehicle': None,
            'staff_rows': [
                {
                    'slug': 'setup-crew',
                    'qty': '2',
                    'include_self': True,
                }
            ],
        }

    def _post_block(self, client, process, units, **extra):
        client.force_login(self.user)
        payload = {
            'request_units_json': json.dumps(units),
            'final_performance_load_out_date': '2026-04-10',
            'final_performance_location': '大阪',
        }
        payload.update(extra)
        return client.post(
            reverse('productions:block_edit', kwargs={'process_pk': process.pk}),
            payload,
        )

    def test_form_shows_separate_add_buttons_and_no_block_note(self, client):
        client.force_login(self.user)

        response = client.get(
            reverse('productions:block_edit', kwargs={'process_pk': self.theatre_process.pk})
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert '車両便を追加' in content
        assert '人員申請を追加' in content
        assert '人員備考' in content
        assert '便備考' in content
        assert '開始時間' in content
        assert '終了時間' in content
        assert '申請単位を追加' not in content
        assert 'ブロック備考' not in content
        assert 'name="note"' not in content

    def test_travel_form_shows_transport_only(self, client):
        client.force_login(self.user)

        response = client.get(
            reverse('productions:block_edit', kwargs={'process_pk': self.travel_unload_process.pk})
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert '車両便を追加' in content
        assert '人員申請を追加' not in content
        assert '車両申請: 旅荷降ろし・倉庫荷降ろし' in content

    def test_save_splits_transport_and_staffing_units(self, client):
        response = self._post_block(
            client,
            self.theatre_process,
            [
                self._transport_unit(vehicle_note='1便メモ'),
                self._staffing_unit(note='初日人員メモ'),
            ],
        )

        assert response.status_code == 302
        transport_unit = ProcessRequestUnit.objects.get(
            process=self.theatre_process,
            unit_type=ProcessRequestUnit.UnitType.TRANSPORT,
        )
        staffing_unit = ProcessRequestUnit.objects.get(
            process=self.theatre_process,
            unit_type=ProcessRequestUnit.UnitType.STAFFING,
        )
        vehicle_request = VehicleRequest.objects.get(process_request_unit=transport_unit)
        staff_request = StaffRequest.objects.get(process_request_unit=staffing_unit)

        assert transport_unit.note == ''
        assert staffing_unit.note == '初日人員メモ'
        assert staffing_unit.setup_label == 'opening_night'
        assert vehicle_request.note == '1便メモ'
        assert not StaffRequest.objects.filter(process_request_unit=transport_unit).exists()
        assert not VehicleRequest.objects.filter(process_request_unit=staffing_unit).exists()
        assert staff_request.position == self.setup_position
        assert staff_request.quantity == 2

    def test_travel_load_saves_transport_unit_only(self, client):
        response = self._post_block(
            client,
            self.travel_load_process,
            [self._transport_unit(work_date='2026-04-07', vehicle_note='旅荷積み便メモ')],
        )

        assert response.status_code == 302
        unit = ProcessRequestUnit.objects.get(process=self.travel_load_process)
        vehicle_request = VehicleRequest.objects.get(process_request_unit=unit)

        assert unit.unit_type == ProcessRequestUnit.UnitType.TRANSPORT
        assert unit.note == ''
        assert vehicle_request.note == '旅荷積み便メモ'
        assert not StaffRequest.objects.filter(process_request_unit=unit).exists()

    def test_travel_unload_rejects_staffing_unit(self, client):
        response = self._post_block(
            client,
            self.travel_unload_process,
            [self._staffing_unit(work_date='2026-04-11')],
        )

        assert response.status_code == 200
        assert 'この工程では人員申請を追加できません。'.encode() in response.content

    def test_travel_unload_saves_block_meta_and_transport_only(self, client):
        response = self._post_block(
            client,
            self.travel_unload_process,
            [self._transport_unit(work_date='2026-04-11', vehicle_note='旅荷降ろし便メモ')],
            final_performance_load_out_date='2026-04-10',
            final_performance_location='大阪',
        )

        assert response.status_code == 302
        unit = ProcessRequestUnit.objects.get(process=self.travel_unload_process)
        self.travel_unload_process.refresh_from_db()

        assert unit.unit_type == ProcessRequestUnit.UnitType.TRANSPORT
        assert unit.note == ''
        assert (
            self.travel_unload_process.final_performance_load_out_date.isoformat() == '2026-04-10'
        )
        assert self.travel_unload_process.final_performance_location == '大阪'

    def test_detail_view_renders_vehicle_note_and_staff_note_without_process_note(self, client):
        self._post_block(
            client,
            self.theatre_process,
            [
                self._transport_unit(vehicle_note='劇場便メモ'),
                self._staffing_unit(note='劇場人員メモ'),
            ],
        )
        client.force_login(self.user)

        response = client.get(reverse('productions:detail', kwargs={'pk': self.production.pk}))

        assert response.status_code == 200
        content = response.content.decode()
        assert '劇場便メモ' in content
        assert '劇場人員メモ' in content
        assert 'ブロック備考' not in content

    def test_detail_template_uses_unit_type_structure(self):
        pb = {
            'process': self.theatre_process,
            'block_key': 'theatre_setup',
            'has_final_performance': False,
            'units': [
                {
                    'unit_type': 'transport',
                    'work_date': date(2026, 4, 1),
                    'start_time': None,
                    'end_time': None,
                    'note': '',
                    'setup_label_display': '',
                    'vehicle_request': None,
                    'staff_rows': [],
                },
                {
                    'unit_type': 'staffing',
                    'work_date': date(2026, 4, 1),
                    'start_time': None,
                    'end_time': None,
                    'note': '人員カード備考',
                    'setup_label_display': '初日',
                    'vehicle_request': None,
                    'staff_rows': [
                        {
                            'label': '仕込み',
                            'qty': 2,
                            'include_self': True,
                        }
                    ],
                },
            ],
        }

        content = render_to_string(
            'productions/partials/process_block_display.html',
            {'pb': pb, 'forloop': {'counter': 1}},
        )

        assert '車両便申請' in content
        assert '人員申請' in content
        assert '人員備考' in content
        assert '便備考' not in content
