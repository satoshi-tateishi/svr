# 07_DJANGO_IMPLEMENTATION_TEMPLATE_v3.md

## 公演手配管理システム Django実装テンプレート（人員・配車・テンプレート統合版）

* * *

# 1. ディレクトリ構成（拡張版）

Plaintext

```
apps/
 ├── performances/
 │    ├── models/
 │    │    ├── base.py          # Performance, Phase, PhaseSlot
 │    │    ├── staff.py         # StaffAssignment, FreelanceRate
 │    │    └── vehicle.py       # Vehicle, VehicleOperation, VehicleAssignment
 │    ├── services/
 │    │    ├── phase_service.py      # テンプレート展開(1〜9)担当
 │    │    ├── vehicle_service.py    # 配車・原価計算担当
 │    │    ├── lock_service.py       # 人員・車輌同時スナップショット確定
 │    │    └── ...
 │    ├── signals.py                 # 自動ステータス更新等
 │    └── selectors.py               # 乖離分析クエリ(希望vs確定)
 ├── productions/
 │    ├── models.py                  # Production, ProcessDay, StaffRequest
 │    ├── views.py                   # HTMX + Alpine.js モーダル操作
 │    └── templates/
 │         └── productions/          # 一括編集・セットアップ画面
```

* * *

# 2. models.py（主要モデル抜粋）

## 2.1 運行工程（時間比較用）

Python

```
class VehicleOperation(models.Model):
    performance = models.ForeignKey("Performance", on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    
    # 希望 (Requested)
    requested_start = models.DateTimeField()
    requested_end = models.DateTimeField()
    
    # 確定 (Scheduled)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(max_length=20, default="Draft") # Draft/Assigned/Locked
```

## 2.2 統合スナップショット

Python

```
class FinancialSnapshot(models.Model):
    # PhaseSlot(人員用) または VehicleOperation(配信用) に紐付け
    phase_slot = models.OneToOneField("PhaseSlot", on_delete=models.CASCADE, null=True)
    vehicle_operation = models.OneToOneField("VehicleOperation", on_delete=models.CASCADE, null=True)

    applied_staff_cost = models.IntegerField(default=0)
    applied_vehicle_cost = models.IntegerField(default=0)
    
    # 乖離情報の記録
    staff_count_gap = models.IntegerField(default=0)
    schedule_drift_minutes = models.IntegerField(default=0)
    
    snapshot_json = models.JSONField()
    snapshot_hash = models.CharField(max_length=128)
    locked_at = models.DateTimeField(auto_now_add=True)
```

* * *

# 3. PhaseService（テンプレート展開）

Python

```
class PhaseService:
    @staticmethod
    @transaction.atomic
    def apply_production_template(performance, start_date):
        TEMPLATE_STEPS = [
            "機材作り", "稽古場仕込み", "稽古", "稽古場バラシ",
            "劇場仕込み", "舞台稽古", "本番", "劇場バラシ", "ツアー/最終荷降ろし"
        ]
        
        created_phases = []
        for i, name in enumerate(TEMPLATE_STEPS):
            phase = Phase.objects.create(
                performance=performance,
                name=f"{i+1}. {name}",
                order=i
            )
            # デフォルトのスロットを1つ作成
            PhaseSlot.objects.create(
                phase=phase,
                start_datetime=start_date + timedelta(days=i), # 仮の日程
                status="Draft"
            )
            created_phases.append(phase)
            
        return created_phases
```

* * *

# 4. LockService（統合ロック）

Python

```
class LockService:
    @staticmethod
    @transaction.atomic
    def lock_execution(actor, target_id, target_type='staff'):
        """
        人員(PhaseSlot)または配車(VehicleOperation)をロックし、
        その時点の単価・原価・乖離理由をスナップショット保存する。
        """
        if target_type == 'staff':
            target = PhaseSlot.objects.select_for_update().get(id=target_id)
            assignments = target.staffassignment_set.all()
        else:
            target = VehicleOperation.objects.select_for_update().get(id=target_id)
            assignments = target.vehicleassignment_set.all()

        # 1. 金額計算ロジック (既存のUnitPriceService等を利用)
        calculation_result = CalculationService.run(target, assignments)
        
        # 2. 乖離(Gap/Drift)の算出
        drift = target.calculate_drift() if target_type == 'vehicle' else 0
        
        # 3. JSON生成 & ハッシュ化
        snapshot_dict = {
            "target_id": target.id,
            "items": calculation_result.details,
            "drift_minutes": drift,
            "timestamp": now().isoformat()
        }
        snap_hash = generate_snapshot_hash(snapshot_dict)

        # 4. 保存
        FinancialSnapshot.objects.update_or_create(
            **{f"{target_type if target_type == 'staff' else 'vehicle_operation'}": target},
            defaults={
                "applied_staff_cost": calculation_result.staff_total,
                "applied_vehicle_cost": calculation_result.vehicle_total,
                "snapshot_json": snapshot_dict,
                "snapshot_hash": snap_hash,
                "schedule_drift_minutes": drift
            }
        )

        # 5. ステータス更新 & 監査ログ
        target.status = "Locked"
        target.save()
        AuditService.log_event(actor, "EXECUTION_LOCKED", target, after=snapshot_dict)
```

* * *

# 5. DashboardQuery（乖離分析セレクタ）

Python

```
class PerformanceSelectors:
    @staticmethod
    def get_handover_issues(performance_id):
        """
        制作の希望と管理者の手配に乖離がある項目を抽出
        """
        ops = VehicleOperation.objects.filter(
            performance_id=performance_id
        ).annotate(
            drift=ExpressionWrapper(
                F('scheduled_start') - F('requested_start'),
                output_field=DurationField()
            )
        ).filter(drift__gt=timedelta(minutes=30))
        
        return ops
```

* * *

# 6. 実装上の絶対ルール（v3）

1.  **時間計算の厳密化**: `scheduled_start` が `None` の状態（未配車）でのLockは `ValidationError` とする。
2.  **外注原価の必須化**: 外注車輌がアサインされている場合、`applied_cost_amount` が 0 の状態でのLockは警告を出す。
3.  **テンプレートの冪等性**: `apply_production_template` は、既にPhaseが存在する場合は重複作成しないようガードをかける。
4.  **ハッシュ検証**: `FinancialSnapshot` の参照時、保存されている `snapshot_hash` と JSON の内容が一致するか検証するプロパティを Model に実装する。

* * *

# 7. pytest（乖離チェックのテスト）

Python

```
def test_lock_fails_if_unassigned(admin_user, slot_draft):
    # アサインが一人もいない状態でロックしようとするとエラーになること
    with pytest.raises(ValueError, match="No assignments found"):
        LockService.lock_execution(admin_user, slot_draft.id, 'staff')


* * *

# 8. モダン UI パターン (HTMX + Alpine.js)

人員手配の一括編集など、リッチなインタラクションが必要な箇所では以下のパターンを採用する。

## 8.1 HTMX によるモーダル制御

`hx-target="#modal"`, `hx-swap="innerHTML"` でモーダル全体を取得・差し替え、保存成功時は `HX-Redirect` または部分更新（カードのみ）を返す。

## 8.2 Alpine.js によるクライアントサイド状態管理

### 一括編集 (Bulk Edit)
-   `x-data` で `requests` 配列を保持。
-   `initial_requests` を `json_script` で渡し、`init()` で文字列型に変換して保持。
-   `prepareSubmit()` で整数型に戻し、単一の `requests_json` hidden input に同期させて送信。

### タイマー制御メッセージ
-   多重起動を避けるため、`messageTimer` を保持し、`clearTimeout` してから新規セットする。

### 確認ステップ (Two-step confirmation)
-   削除や上書きコピーなど、破壊的な操作では `showConfirm` フラグを用いたボタンの二段階表示（通常 -> 確認）を行い、ブラウザ標準の `alert/confirm` を回避する。
```



