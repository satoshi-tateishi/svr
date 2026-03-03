# SERVICE_LAYER_v3.md

## 公演手配管理システム サービス層設計書（スナップショット確定完全版）

---

# 1. 設計目的

Service層の目的：

- View / API から業務ロジックを完全分離
- トランザクション境界明確化
- 単価履歴整合性担保
- 🔒 Lock時金額スナップショット確定
- 🔒 Lock後不変性保証
- SaaS責務侵害防止
- AI実装時のロジック混在防止

---

# 2. レイヤー構成

View / API  
↓  
Service層（業務ロジック）  
↓  
Repository（ORM）  
↓  
Model

---

# 3. サービス分類（最終版）

1. PerformanceService
2. PhaseService
3. PhaseSlotService
4. AssignmentService
5. PositionService
6. FreelanceRateService
7. AllowanceService
8. ScheduleConflictService
9. 🔒 LockService（スナップショット確定責務）
10. ApiIntegrationService
11. DashboardQueryService
12. AuditLogService

---

# 4. 各サービス詳細

---

## 4.1 PerformanceService

責務：
- 公演作成
- 公演更新
- メンバー管理

atomic：各操作単位

---

## 4.2 PhaseService

責務：
- フェーズ管理

atomic：必要時のみ

---

## 4.3 PhaseSlotService

責務：
- PhaseSlot作成・更新
- 占有時間算出
- すみだ倉庫初期値反映

### メソッド

calculate_occupied_time(slot)

※ 占有時間ロジックはここ以外に記述禁止

---

## 4.4 PositionService

責務：
- 案件内ポジション管理

### メソッド

create_position(performance_id, name)  
update_position(position_id, name)  
deactivate_position(position_id)

### 制約

- (performance, name) 重複禁止
- Locked済slotで使用中なら削除不可

atomic必須

---

## 4.5 FreelanceRateService（履歴保持）

責務：
- 単価登録（履歴追加のみ）
- 期間重複検証
- 単価取得

---

### create_rate(...)

- 上書き禁止
- performance × user × position 単位で重複禁止
- DB制約＋アプリ検証両方実装

atomic必須

---

### get_applicable_rate(...)

検索条件：

1. performance一致
2. user一致
3. position一致
4. valid_from <= target_datetime
5. valid_to is null OR target_datetime < valid_to

許容件数：

- 1件 → OK
- 0件 → RateNotFoundException
- 複数 → RateConflictException

---

## 4.6 AllowanceService

責務：
- 手当付与
- 手当削除
- 手当合計算出

### メソッド

add_allowance(...)  
remove_allowance(...)  
calculate_total_allowance(slot_id)

制約：

- Locked後変更禁止
- 同一slot×allowance_type重複禁止

atomic必須

---

## 4.7 AssignmentService

責務：
- Request作成
- Assignment確定
- Staff紐付け（position必須）

### confirm_assignment(slot_id, staff_data, vehicle_data)

処理：

1. PhaseSlot select_for_update
2. occupied時間算出
3. ScheduleConflictService検証
4. StaffAssignment作成
5. PhaseSlot.status=Assigned

禁止：

- 単価参照禁止
- 金額計算禁止

atomic必須

---

## 4.8 ScheduleConflictService

責務：
- occupied時間帯重複判定

ロジック：

existing.start < new.end  
AND  
existing.end > new.start

副作用なし

---

# 5. 🔒 LockService（最重要）

責務：

- 実績確定
- 単価確定
- 手当確定
- 🔒 スナップショット保存
- API送信トリガー

---

## lock_phase_slot(slot_id, locked_by)

### トランザクション必須

```
@transaction.atomic
```

### 処理フロー

1. PhaseSlot select_for_update
2. status=Assigned確認
3. StaffAssignment取得（select_for_update）

4. 各スタッフ処理：

   if is_freelance:
       rate = FreelanceRateService.get_applicable_rate()

       applied_rate_id = rate.id
       applied_unit_price = rate.unit_price
   else:
       applied_rate_id = None
       applied_unit_price = None

5. allowance_total = AllowanceService.calculate_total_allowance(slot_id)

6. total_amount算出

7. StaffAssignmentへ保存：

   - applied_rate_id
   - applied_unit_price
   - applied_allowance_total
   - applied_total_amount
   - applied_position_name
   - locked_at

8. PhaseSlot.status = Locked

9. AuditLogService.record_lock()

10. ApiIntegrationService.enqueue_send()

---

### 🔒 絶対原則

- Lock後に単価再計算禁止
- Lock後にposition変更禁止
- Lock後に手当変更禁止
- Lock解除API作らない

---

# 6. ApiIntegrationService

責務：

- payload生成
- freee送信
- board送信
- 送信ログ記録
- 手動再送

---

## payload生成原則

🔒 PerformanceFreelanceRate再参照禁止

必ず使用するのは：

- applied_unit_price
- applied_total_amount
- applied_position_name

---

## retry_transmission(log_id)

- 元payload再利用
- 再計算禁止
- PhaseSlot.status変更禁止

---

# 7. DashboardQueryService

責務：

- 今日の工程
- API失敗一覧
- 単価未登録警告
- Lock可能事前チェック

DB更新禁止

---

# 8. AuditLogService

責務：

- 単価登録記録
- Lock記録
- API再送記録
- 手当変更記録

削除禁止

---

# 9. トランザクション境界（確定版）

atomic必須：

- confirm_assignment
- create_rate
- add_allowance
- lock_phase_slot
- APIログ生成

select_for_update必須：

- Lock対象PhaseSlot
- Lock対象StaffAssignment

---

# 10. 状態遷移

Draft  
→ Requested  
→ Assigned  
→ 🔒 Locked

Locked後：

- Staff変更不可
- Position変更不可
- 単価変更不可
- 手当変更不可
- occupied時間変更不可

---

# 11. 整合性保証まとめ

- 単価履歴重複禁止
- Lock時単価未登録エラー
- スナップショット保存
- 再計算禁止
- API失敗でもLocked維持
- 締日概念なし

---

# 12. 禁止事項（強化）

1. Lock後データ変更
2. Lock後単価再取得
3. API再送時再計算
4. Lock解除実装
5. Modelに金額ロジック記述

---

# 13. テスト戦略（強化）

必須テスト：

- 単価期間重複検出
- 単価0件取得エラー
- 単価複数件取得エラー
- Lock時スナップショット保存確認
- Lock後単価履歴変更しても影響なし
- API再送で金額不変
- 手当Lock後変更禁止

---

# 14. 設計思想の固定

- 金額はLock時に確定
- 確定後は不変
- 過去を書き換えない
- 巻き戻さない
- SaaS責務を侵害しない