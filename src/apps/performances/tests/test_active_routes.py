import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.performances.models.vehicle import Vehicle
from apps.productions.models import Process, ProcessDay, ProcessType, Production, VehicleRequest


@pytest.mark.django_db
class TestPerformanceActiveRoutes:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_user(username='performance-routes', password='password')
        UserProfile.objects.filter(user=self.user).update(system_role=UserProfile.SystemRole.EDITOR)

        self.production = Production.objects.create(
            code='TEST-PERF-001',
            title='Performance 導線テスト',
            created_by=self.user,
        )
        self.process_type = ProcessType.objects.create(
            slug='performance-routes-type',
            name='仕込み',
            category='venue',
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
            date='2026-05-01',
        )
        self.vehicle = Vehicle.objects.create(
            name='Performance 導線車両',
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

    def test_root_redirects_to_dashboard(self, client):
        client.force_login(self.user)

        response = client.get(reverse('performances:list'))

        assert response.status_code == 302
        assert response.url == reverse('performances:dashboard')

    def test_dashboard_is_available(self, client):
        client.force_login(self.user)

        response = client.get(reverse('performances:dashboard'))

        assert response.status_code == 200
        assert 'production_management/dashboard.html' in [
            template.name for template in response.templates
        ]

    def test_vehicle_assignment_dashboard_and_modal_are_available(self, client):
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
        assert '車両手配を編集' in edit_response.content.decode()
        assert 'production_management/production_vehicle_assignment_form.html' in [
            template.name for template in edit_response.templates
        ]
