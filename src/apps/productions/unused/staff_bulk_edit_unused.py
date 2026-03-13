import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.productions.models import (
    Position,
    Process,
    ProcessDay,
    ProcessType,
    Production,
    StaffRequest,
)


@pytest.mark.django_db
class TestStaffBulkEditUI:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        # テスト用ユーザー（editor ロールで権限あり）
        # post_save シグナルで UserProfile が自動生成されるため update で設定する
        self.user = User.objects.create_user(username='testuser', password='password')
        UserProfile.objects.filter(user=self.user).update(system_role=UserProfile.SystemRole.EDITOR)

        # 公演データ
        self.production = Production.objects.create(
            code='TEST-001', title='テスト公演', created_by=self.user
        )

        # マスタデータ（migration で事前挿入済みの場合は get_or_create で衝突を回避）
        self.pt_rehearsal, _ = ProcessType.objects.get_or_create(
            slug='rehearsal', defaults={'name': '稽古', 'category': 'rehearsal'}
        )
        self.pos_sound, _ = Position.objects.get_or_create(
            slug='sound', defaults={'name': '音響', 'order': 1}
        )
        self.pos_light, _ = Position.objects.get_or_create(
            slug='light', defaults={'name': '照明', 'order': 2}
        )

        # 工程データ
        self.process = Process.objects.create(production=self.production, title='基本工程')
        self.day = ProcessDay.objects.create(
            process=self.process, process_type=self.pt_rehearsal, date='2026-03-10'
        )

        # 初期手配（音響x1）
        self.existing_req = StaffRequest.objects.create(
            process_day=self.day, position=self.pos_sound, quantity=1, note='既存メモ'
        )

    def test_logic_only(self, client):
        """UI操作の前に、Viewレベルでの一括同期ロジックを検証"""
        client.force_login(self.user)
        url = reverse('productions:staff_requests_bulk_edit', kwargs={'day_pk': self.day.id})

        # 1. GET 確認 (初期値が JSON で渡されているか)
        response = client.get(url)
        assert response.status_code == 200
        assert b'initial-requests-data' in response.content

        # 2. POST 同期確認 (音響を2名に更新、照明を新規追加)
        payload = [
            {'position_id': self.pos_sound.id, 'quantity': 2, 'note': '音響更新'},
            {'position_id': self.pos_light.id, 'quantity': 3, 'note': '照明追加'},
        ]
        response = client.post(url, {'requests_json': json.dumps(payload)})

        # 成功時は HX-Redirect
        assert response.status_code == 200
        assert response.has_header('HX-Redirect')

        # DB状態の確認
        assert StaffRequest.objects.filter(process_day=self.day).count() == 2
        sound_req = StaffRequest.objects.get(process_day=self.day, position=self.pos_sound)
        assert sound_req.quantity == 2
        assert sound_req.note == '音響更新'

        light_req = StaffRequest.objects.get(process_day=self.day, position=self.pos_light)
        assert light_req.quantity == 3

        # 3. 削除の確認 (照明を削除して音響のみにする)
        payload = [{'position_id': self.pos_sound.id, 'quantity': 1, 'note': ''}]
        client.post(url, {'requests_json': json.dumps(payload)})
        assert StaffRequest.objects.filter(process_day=self.day).count() == 1
        assert not StaffRequest.objects.filter(
            process_day=self.day, position=self.pos_light
        ).exists()

    def test_validation_errors(self, client):
        """バリデーションエラーの確認"""
        client.force_login(self.user)
        url = reverse('productions:staff_requests_bulk_edit', kwargs={'day_pk': self.day.id})

        # 不正 JSON はエラー再描画
        response = client.post(url, {'requests_json': 'invalid-json'})
        assert response.status_code == 200
        assert 'データの形式が不正です'.encode() in response.content

        # 数量 0 はエラー再描画
        payload = [{'position_id': self.pos_sound.id, 'quantity': 0}]
        response = client.post(url, {'requests_json': json.dumps(payload)})
        assert response.status_code == 200
        assert '1名以上'.encode() in response.content
