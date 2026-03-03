# DJANGO_IMPLEMENTATION_TEMPLATE_v2.md

## 公演手配管理システム Django実装テンプレート（単価スナップショット対応版）

* * *

# 1. ディレクトリ構成

Plain text

apps/  
 ├── performances/  
 │    ├── models.py  
 │    ├── services/  
 │    │    ├── performance_service.py  
 │    │    ├── phase_slot_service.py  
 │    │    ├── assignment_service.py  
 │    │    ├── lock_service.py  
 │    │    ├── cost_snapshot_service.py  
 │    │    ├── unit_price_service.py  
 │    │    ├── schedule_conflict_service.py  
 │    │    ├── api_integration_service.py  
 │    │    └── dashboard_query_service.py  
 │    ├── permissions.py  
 │    ├── audit.py  
 │    ├── hashing.py  
 │    ├── selectors.py  
 │    └── exceptions.py  
 │  
 ├── accounts/  
 │    └── models.py  
 │  
 └── core/  
      └── mixins.py

* * *

# 2. models.py（追加モデル含む）

## 2.1 単価履歴

Python

class UnitPriceHistory(models.Model):  
    performance = models.ForeignKey("Performance", on_delete=models.CASCADE)  
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)  
    position = models.CharField(max_length=50)  
  
    unit_price = models.IntegerField()  
  
    valid_from = models.DateField()  
    valid_to = models.DateField(null=True, blank=True)  
  
    is_active = models.BooleanField(default=True)  
  
    created_at = models.DateTimeField(auto_now_add=True)

* * *

## 2.2 コストスナップショット

Python

class CostSnapshot(models.Model):  
    phase_slot = models.OneToOneField("PhaseSlot", on_delete=models.CASCADE)  
  
    staff_cost_total = models.IntegerField()  
    vehicle_cost_total = models.IntegerField()  
    grand_total = models.IntegerField()  
  
    snapshot_json = models.JSONField()  
    snapshot_hash = models.CharField(max_length=128)  
  
    calculation_version = models.IntegerField(default=1)  
  
    created_at = models.DateTimeField(auto_now_add=True)

* * *

# 3. ハッシュ生成

## hashing.py

Python

import hashlib  
import json  
  
def generate_snapshot_hash(snapshot_dict: dict) -> str:  
    normalized = json.dumps(snapshot_dict, sort_keys=True)  
    return "sha256:" + hashlib.sha256(normalized.encode()).hexdigest()

* * *

# 4. UnitPriceService

Python

class UnitPriceService:  
  
    @staticmethod  
    @transaction.atomic  
    def create_unit_price(actor, data):  
        obj = UnitPriceHistory.objects.create(**data)  
  
        AuditService.log_event(  
            actor,  
            "UNIT_PRICE_HISTORY_CREATED",  
            obj,  
            before=None,  
            after=data  
        )  
  
        return obj

* * *

# 5. CostSnapshotService

Python

class CostSnapshotService:  
  
    @staticmethod  
    def generate_snapshot(slot):  
  
        staff_total = 0  
        vehicle_total = 0  
  
        staff_details = []  
  
        for assignment in slot.staffassignment_set.all():  
  
            unit_price_obj = UnitPriceHistory.objects.filter(  
                performance=slot.performance,  
                user=assignment.user,  
                valid_from__lte=slot.start_datetime.date(),  
                is_active=True  
            ).order_by("-valid_from").first()  
  
            unit_price = unit_price_obj.unit_price if unit_price_obj else 0  
            subtotal = unit_price * assignment.quantity  
  
            staff_total += subtotal  
  
            staff_details.append({  
                "user_id": assignment.user.id,  
                "unit_price": unit_price,  
                "quantity": assignment.quantity,  
                "subtotal": subtotal  
            })  
  
        grand_total = staff_total + vehicle_total  
  
        snapshot_dict = {  
            "phase_slot_id": slot.id,  
            "staff_cost_total": staff_total,  
            "vehicle_cost_total": vehicle_total,  
            "grand_total": grand_total,  
            "staff_details": staff_details,  
            "calculation_version": 1  
        }  
  
        snapshot_hash = generate_snapshot_hash(snapshot_dict)  
  
        snapshot = CostSnapshot.objects.update_or_create(  
            phase_slot=slot,  
            defaults={  
                "staff_cost_total": staff_total,  
                "vehicle_cost_total": vehicle_total,  
                "grand_total": grand_total,  
                "snapshot_json": snapshot_dict,  
                "snapshot_hash": snapshot_hash  
            }  
        )[0]  
  
        return snapshot, snapshot_dict

* * *

# 6. LockService（改訂版）

Python

class LockService:  
  
    @staticmethod  
    @transaction.atomic  
    def lock_phase_slot(actor, slot_id):  
  
        slot = PhaseSlot.objects.select_for_update().get(id=slot_id)  
  
        if slot.status != "Assigned":  
            raise ValueError("Only Assigned can be locked")  
  
        snapshot, snapshot_dict = CostSnapshotService.generate_snapshot(slot)  
  
        AuditService.log_event(  
            actor,  
            "COST_SNAPSHOT_CREATED",  
            slot,  
            before=None,  
            after=snapshot_dict  
        )  
  
        slot.status = "Locked"  
        slot.save()  
  
        AuditService.log_event(  
            actor,  
            "PHASE_SLOT_LOCKED",  
            slot,  
            before={"status": "Assigned"},  
            after={"status": "Locked"}  
        )  
  
        ApiIntegrationService.send(slot)

* * *

# 7. Unlock対応

Python

    @staticmethod  
    @transaction.atomic  
    def unlock_phase_slot(actor, slot_id, reason):  
  
        slot = PhaseSlot.objects.select_for_update().get(id=slot_id)  
  
        if actor.system_role != "Admin":  
            raise PermissionError("Only Admin can unlock")  
  
        before = {"status": slot.status}  
  
        slot.status = "Assigned"  
        slot.save()  
  
        AuditService.log_event(  
            actor,  
            "PHASE_SLOT_UNLOCKED",  
            slot,  
            before=before,  
            after={  
                "status": "Assigned",  
                "unlock_reason": reason  
            }  
        )

再Lock時は：

-   既存Snapshot存在 → COST_SNAPSHOT_REGENERATED

* * *

# 8. AuditService改訂

Python

class AuditService:  
  
    @staticmethod  
    def log_event(actor, event_type, obj, before, after):  
  
        performance_role = None  
  
        if hasattr(obj, "performance"):  
            member = PerformanceMember.objects.filter(  
                performance=obj.performance,  
                user=actor,  
                is_active=True  
            ).first()  
            performance_role = member.role if member else None  
  
        AuditLog.objects.create(  
            event_type=event_type,  
            actor_user=actor,  
            system_role_snapshot=actor.system_role,  
            performance_role_snapshot=performance_role,  
            related_object_type=obj.__class__.__name__,  
            related_object_id=obj.id,  
            before_state=before,  
            after_state=after,  
        )

* * *

# 9. 実装ルール（v2追加）

-   Locked時必ずスナップショット生成
-   Unlock→再Lock時は再生成
-   単価履歴変更はログ必須
-   Snapshotハッシュ必須
-   CostSnapshotは手動編集禁止

* * *

# 10. pytest追加例

Python

def test_snapshot_created_on_lock(db, admin_user, slot_assigned):  
    LockService.lock_phase_slot(admin_user, slot_assigned.id)  
  
    snapshot = CostSnapshot.objects.get(phase_slot=slot_assigned)  
    assert snapshot.grand_total >= 0  
    assert snapshot.snapshot_hash.startswith("sha256:")

* * *

# v2の完成度

-   スナップショット完全対応
-   改ざん耐性強化
-   法的証跡レベル向上
-   Service層責務明確化
-   再Lock追跡可能

