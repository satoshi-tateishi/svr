# DATA_FLOW_DIAGRAM_v3.md

## 公演手配管理システム データフロー図設計書（スナップショット確定完全版）

---

# 1. 設計目的

- 業務責務の流れを可視化
- 🔒 Lock時金額スナップショット確定明示
- API再送安全性保証
- 不可逆性保証
- SaaS責務境界明確化
- 締日非保持明示

---

# 2. 重要前提（確定版）

- 単価は「案件 × ユーザー × ポジション × 期間」で決定
- 🔒 単価はLock時に確定し保存される
- 🔒 Lock後は再計算しない
- 手当もLock時に確定保存
- 締日概念は持たない

---

# 3. レベル1主要プロセス（更新）

```
(1) ポジション管理
(2) 単価履歴登録
(3) Assignment確定
(4) 🔒 Lock（単価検索＋スナップショット保存）
(5) 🔒 保存済データをAPI送信
(6) 通知
```

---

# 4. 🔒 実績ロックフロー（完全版）

```
Planner / Editor
   ↓
LockService.lock_phase_slot()
   ↓
PhaseSlot select_for_update
   ↓
StaffAssignment select_for_update
   ↓
status=Assigned確認
   ↓
各スタッフ処理：

   if is_freelance:
       applicable_rate検索
       条件：
         valid_from <= slot.start
         AND (valid_to is null OR slot.start < valid_to)

       0件 → 例外
       複数 → 例外

       ↓
       🔒 StaffAssignmentへ保存：
          applied_rate_id
          applied_unit_price

   else:
       applied_rate_id = NULL

   ↓
手当合計算出
   ↓
🔒 StaffAssignmentへ保存：
   applied_allowance_total
   applied_total_amount
   applied_position_name
   locked_at

   ↓
PhaseSlot.status = Locked
   ↓
AuditLog記録
   ↓
ApiIntegrationService.enqueue_send()
```

---

# 5. 🔒 単価スナップショット保存フロー

```
PerformanceFreelanceRate
   ↓
単価検索
   ↓
StaffAssignment.applied_rate_idへ保存
StaffAssignment.applied_unit_priceへ保存
StaffAssignment.applied_total_amountへ保存
```

以後、単価履歴は参照しない。

---

# 6. API送信フロー（更新）

```
ApiIntegrationService
   ↓
StaffAssignment.applied_* 取得
   ↓
payload生成
   ↓
ApiTransmissionLog保存（payload_snapshot）
   ↓
freee / board API呼出
```

🔒 PerformanceFreelanceRate再検索禁止

---

# 7. API再送フロー（厳密版）

```
Admin / Editor
   ↓
retry_transmission()
   ↓
保存済payload_snapshot取得
   ↓
再送信
   ↓
status更新
```

禁止事項：

- 単価再検索
- 金額再計算
- Lock解除

---

# 8. 単価履歴変更後の挙動

```
PerformanceFreelanceRate更新
   ↓
Locked済PhaseSlotへ影響なし
   ↓
未来Lockにのみ影響
```

---

# 9. 状態遷移（確定）

Draft  
→ Requested  
→ Assigned  
→ 🔒 Locked（単価確定済）

Locked後：

- Staff変更不可
- Position変更不可
- 手当変更不可
- 金額再計算不可

---

# 10. データフロー安全保証

- 単価履歴重複禁止
- Lock時単価未登録エラー
- 🔒 スナップショット保存
- 🔒 再計算禁止
- API失敗でもLocked維持
- 締日概念なし
- 巻き戻しなし

---

# 11. 同時実行制御（強化）

```
lock_phase_slot():
    select_for_update(slot)
    select_for_update(staff_assignments)
```

30人同時利用想定。

---

# 12. 最終設計思想

- 金額はLock時に確定
- 確定後は不変
- 再計算しない
- 過去を書き換えない
- SaaSは最終会計責任
- 自作アプリは確定実績責任