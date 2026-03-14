import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.performances.models.vehicle import Vehicle
from apps.productions.models import (
    Process,
    ProcessDay,
    ProcessType,
    Production,
    ProductionMember,
    VehicleAssignment,
    VehicleRequest,
)


@pytest.mark.django_db
class TestProductionActiveRoutes:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_user(username='active-routes', password='password')
        UserProfile.objects.filter(user=self.user).update(system_role=UserProfile.SystemRole.EDITOR)

        self.production = Production.objects.create(
            code='TEST-ACTIVE-001',
            title='現役導線テスト',
            created_by=self.user,
        )
        self.process_type = ProcessType.objects.create(
            slug='active-routes-type',
            name='稽古',
            category='rehearsal',
        )
        self.process = Process.objects.create(
            production=self.production,
            title='劇場仕込み',
            block_key='theatre_setup',
            order=1,
        )
        self.day = ProcessDay.objects.create(
            process=self.process,
            process_type=self.process_type,
            date='2026-04-01',
        )
        self.vehicle = Vehicle.objects.create(
            name='現役導線車両',
            vehicle_type=Vehicle.VehicleType.HIACE,
            ownership_type=Vehicle.OwnershipType.COMPANY,
            is_active=True,
            order=1,
        )
        self.vehicle_request = VehicleRequest.objects.create(
            process_day=self.day,
            requested_vehicle=self.vehicle,
            request_kind=VehicleRequest.RequestKind.LOAD_IN,
        )
        self.member = ProductionMember.objects.create(
            production=self.production,
            user=self.user,
            role=ProductionMember.Role.SOUND_DESIGNER,
        )

    def test_list_and_detail_pages_are_available(self, client):
        client.force_login(self.user)

        list_response = client.get(reverse('productions:list'))
        create_response = client.get(reverse('productions:create'))
        detail_response = client.get(
            reverse('productions:detail', kwargs={'pk': self.production.pk})
        )

        assert list_response.status_code == 200
        assert create_response.status_code == 200
        assert detail_response.status_code == 200
        assert reverse('productions:create') in list_response.content.decode()
        assert 'name="note"' in create_response.content.decode()
        assert (
            reverse('productions:edit', kwargs={'pk': self.production.pk})
            in list_response.content.decode()
        )
        assert '車両管理' not in detail_response.content.decode()

    def test_list_page_keeps_production_edit_modal(self, client):
        client.force_login(self.user)

        edit_response = client.get(
            reverse('productions:edit', kwargs={'pk': self.production.pk}),
            HTTP_HX_REQUEST='true',
        )
        save_response = client.post(
            reverse('productions:edit', kwargs={'pk': self.production.pk}),
            {'title': '更新後タイトル', 'note': '更新後備考'},
            HTTP_HX_REQUEST='true',
        )

        assert edit_response.status_code == 200
        assert '公演情報を編集' in edit_response.content.decode()
        assert 'productions/production_edit_modal.html' in [
            template.name for template in edit_response.templates
        ]
        assert save_response.status_code == 200
        assert save_response['HX-Redirect'] == reverse('productions:list')

        self.production.refresh_from_db()
        assert self.production.title == '更新後タイトル'
        assert self.production.note == '更新後備考'

    def test_detail_page_keeps_member_and_block_modals(self, client):
        client.force_login(self.user)

        add_response = client.get(
            reverse('productions:member_add', kwargs={'production_pk': self.production.pk}),
            HTTP_HX_REQUEST='true',
        )
        edit_response = client.get(
            reverse('productions:member_edit', kwargs={'pk': self.member.pk}),
            HTTP_HX_REQUEST='true',
        )
        block_response = client.get(
            reverse('productions:block_edit', kwargs={'process_pk': self.process.pk}),
            HTTP_HX_REQUEST='true',
        )

        assert add_response.status_code == 200
        assert edit_response.status_code == 200
        assert block_response.status_code == 200

    def test_detail_page_uses_renamed_staff_days_script_partial(self, client):
        client.force_login(self.user)

        response = client.get(reverse('productions:detail', kwargs={'pk': self.production.pk}))

        assert response.status_code == 200
        assert 'function requestUnitsApp(blockKey)' in response.content.decode()
        assert 'productions/partials/_scripts_staff_days.html' in [
            template.name for template in response.templates
        ]

    def test_dashboard_vehicle_assignment_page_and_modal_are_available(self, client):
        client.force_login(self.user)

        list_response = client.get(reverse('performances:production_vehicle_assignments'))
        edit_response = client.get(
            reverse(
                'performances:production_vehicle_assignment_edit',
                kwargs={'pk': self.vehicle_request.pk},
            ),
            HTTP_HX_REQUEST='true',
        )

        assert list_response.status_code == 200
        assert edit_response.status_code == 200
        assert self.production.title in list_response.content.decode()

    def test_productions_vehicle_assignment_page_and_modal_are_available(self, client):
        client.force_login(self.user)

        list_response = client.get(
            reverse('productions:vehicle_assignment_list', kwargs={'pk': self.production.pk})
        )
        edit_response = client.get(
            reverse(
                'productions:vehicle_assignment_edit',
                kwargs={'pk': self.vehicle_request.pk},
            ),
            HTTP_HX_REQUEST='true',
        )

        assert list_response.status_code == 200
        assert edit_response.status_code == 200
        assert self.production.title in list_response.content.decode()
        assert '車両手配を編集' in edit_response.content.decode()
        assert 'productions/vehicle_assignment_edit_modal.html' in [
            template.name for template in edit_response.templates
        ]
        assignment = VehicleAssignment.objects.get(vehicle_request=self.vehicle_request)
        assert assignment.pk is not None

    def test_dashboard_has_vehicle_management_entry(self, client):
        client.force_login(self.user)

        response = client.get(reverse('performances:dashboard'))

        assert response.status_code == 200
        content = response.content.decode()
        assert '車両管理へ' in content
        assert reverse('performances:production_vehicle_assignments') in content
