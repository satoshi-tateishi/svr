import pytest
import json
from django.urls import reverse
from apps.productions.models import Production, Process, ProcessType, Position, StaffRequest, ProcessDay
from django.contrib.auth.models import User

@pytest.mark.django_db
class TestStaffBulkEditUI:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        # テスト用ユーザー
        self.user = User.objects.create_user(username="testuser", password="password")
        
        # 公演データ
        self.production = Production.objects.create(
            code="TEST-001", title="テスト公演", created_by=self.user
        )
        
        # マスタデータ
        self.pt_rehearsal = ProcessType.objects.create(name="稽古", slug="rehearsal", category="rehearsal")
        self.pos_sound = Position.objects.create(name="音響", slug="sound", order=1)
        self.pos_light = Position.objects.create(name="照明", slug="light", order=2)
        
        # 工程データ
        self.process = Process.objects.create(production=self.production, title="基本工程")
        self.day = ProcessDay.objects.create(
            process=self.process, process_type=self.pt_rehearsal, date="2026-03-10"
        )
        
        # 初期手配（音響x1）
        self.existing_req = StaffRequest.objects.create(
            process_day=self.day, position=self.pos_sound, quantity=1, note="既存メモ"
        )

    def test_bulk_edit_workflow(self, live_server, page):
        """人員手配一括編集のワークフロー確認"""
        
        # ログイン処理
        # (実際は shin-on Portal 連携があるが、テスト用は LoginRequiredMixin を考慮)
        page.goto(f"{live_server}{reverse('productions:detail', kwargs={'pk': self.production.id})}")
        # ※ 認証をバイパスするか、テスト用ログイン処理が必要
        # ここでは View が LoginRequired であるため、強制ログインを行う
        
    def test_logic_only(self, client):
        """UI操作の前に、Viewレベルでの一括同期ロジックを検証"""
        client.force_login(self.user)
        url = reverse('productions:staff_requests_bulk_edit', kwargs={'day_pk': self.day.id})
        
        # 1. GET 確認 (初期値が JSON で渡されているか)
        response = client.get(url)
        assert response.status_code == 200
        assert b"initial-requests-data" in response.content
        
        # 2. POST 同期確認 (音響を2名に更新、照明を新規追加)
        payload = [
            {"position_id": self.pos_sound.id, "quantity": 2, "note": "音響更新"},
            {"position_id": self.pos_light.id, "quantity": 3, "note": "照明追加"}
        ]
        response = client.post(url, {"requests_json": json.dumps(payload)})
        
        # 成功時は HX-Redirect
        assert response.status_code == 200
        assert response.has_header("HX-Redirect")
        
        # DB状態の確認
        assert StaffRequest.objects.filter(process_day=self.day).count() == 2
        sound_req = StaffRequest.objects.get(process_day=self.day, position=self.pos_sound)
        assert sound_req.quantity == 2
        assert sound_req.note == "音響更新"
        
        light_req = StaffRequest.objects.get(process_day=self.day, position=self.pos_light)
        assert light_req.quantity == 3
        
        # 3. 削除の確認 (照明を削除して音響のみにする)
        payload = [{"position_id": self.pos_sound.id, "quantity": 1, "note": ""}]
        client.post(url, {"requests_json": json.dumps(payload)})
        assert StaffRequest.objects.filter(process_day=self.day).count() == 1
        assert not StaffRequest.objects.filter(process_day=self.day, position=self.pos_light).exists()

    def test_validation_errors(self, client):
        """バリデーションエラーの確認"""
        client.force_login(self.user)
        url = reverse('productions:staff_requests_bulk_edit', kwargs={'day_pk': self.day.id})
        
        # 重複チェック
        payload = [
            {"position_id": self.pos_sound.id, "quantity": 1},
            {"position_id": self.pos_sound.id, "quantity": 2} # 重複
        ]
        response = client.post(url, {"requests_json": json.dumps(payload)})
        assert response.status_code == 200 # エラー時は再描画
        assert b"\xe9\x87\x8d\xe8\xa4\x87\xe3\x81\x97\xe3\x81\xa6\xe3\x81\x84\xe3\x81\xbe\xe3\x81\x99" in response.content # "重複しています" のバイト列
