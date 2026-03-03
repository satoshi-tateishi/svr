# ERD_v2.md

## 公演手配管理システム ERD（スナップショット保存対応版）

---

# 1. 改訂目的

- Lock時に金額を完全確定
- 単価履歴変更が過去実績へ影響しない構造
- API再送安全性確保
- 監査耐性強化

---

# 2. 設計方針

### ✅ 単価マスタは履歴保持
### ✅ Lock時にスナップショット保存
### ✅ Lock後は実績不変

---

# 3. 主要エンティティ一覧

- Performance
- PerformancePosition
- PhaseSlot
- PhaseSlotAssignment
- StaffAssignment
- VehicleAssignment
- PerformanceFreelanceRate
- PhaseSlotAllowance
- ApiTransmissionLog

---

# 4. ERD構造

---

## 4.1 Performance（案件）

```text
Performance
- id (PK)
- name
- client_name
- start_date
- end_date
- created_at
- updated_at
```

---

## 4.2 PerformancePosition（案件内ポジション）

```text
PerformancePosition
- id (PK)
- performance_id (FK → Performance)
- name
- description
- created_at
```

---

## 4.3 PerformanceFreelanceRate（単価履歴）

```text
PerformanceFreelanceRate
- id (PK)
- performance_id (FK → Performance)
- user_id (FK → User)
- position_id (FK → PerformancePosition)
- unit_price
- valid_from
- valid_to (nullable)
- created_at
- updated_at
```

### 制約

- performance × user × position で期間重複禁止
- 上書き禁止（履歴保持）

---

## 4.4 PhaseSlot（実作業単位）

```text
PhaseSlot
- id (PK)
- performance_id (FK → Performance)
- phase_type
- start_datetime
- end_datetime
- status (Draft / Assigned / Locked)
- created_at
- updated_at
```

---

## 4.5 PhaseSlotAssignment（アサイン確定）

```text
PhaseSlotAssignment
- id (PK)
- phase_slot_id (FK → PhaseSlot)
- confirmed_at
- confirmed_by
```

---

# 5. 🔒 スナップショット対応：StaffAssignment（改訂）

```text
StaffAssignment
- id (PK)
- phase_slot_id (FK → PhaseSlot)
- user_id (FK → User)
- position_id (FK → PerformancePosition)

# ---- Lock前利用 ----
- occupied_start
- occupied_end

# ---- 🔒 Lock時スナップショット ----
- applied_rate_id (FK → PerformanceFreelanceRate, nullable)
- applied_unit_price
- applied_allowance_total
- applied_total_amount
- applied_position_name
- applied_is_freelance (boolean)

- locked_at (nullable)
- created_at
- updated_at
```

---

# 6. Lock時のデータ確定ロジック

## フリーランスの場合

```text
1. applicable_rate検索
2. applied_rate_id保存
3. applied_unit_price保存
4. 手当合計計算
5. applied_allowance_total保存
6. applied_total_amount保存
7. locked_atセット
```

## 社員の場合

```text
applied_is_freelance = False
applied_rate_id = NULL
applied_unit_price = NULL
applied_total_amount = NULL
```

（給与計算はfreee責務）

---

# 7. PhaseSlotAllowance（手当）

```text
PhaseSlotAllowance
- id (PK)
- phase_slot_id (FK → PhaseSlot)
- allowance_type
- amount
- description
- created_at
```

※ Locked後編集禁止

---

# 8. ApiTransmissionLog

```text
ApiTransmissionLog
- id (PK)
- phase_slot_id (FK → PhaseSlot)
- target_service (freee / board)
- payload_json
- status (Pending / Success / Failed)
- retry_count
- error_message
- sent_at
- created_at
```

---

# 9. ERDリレーション概要

```text
Performance
  ├── PerformancePosition
  ├── PerformanceFreelanceRate
  └── PhaseSlot
         ├── PhaseSlotAssignment
         ├── StaffAssignment
         ├── VehicleAssignment
         ├── PhaseSlotAllowance
         └── ApiTransmissionLog
```

---

# 10. 重要設計原則

### ① Lock後は金額再計算しない

金額は常に：

```text
StaffAssignment.applied_total_amount
```

を参照。

---

### ② 単価履歴変更は未来用

PerformanceFreelanceRateを変更しても  
Locked済実績は影響を受けない。

---

### ③ API再送はスナップショット使用

再送時も

```text
applied_unit_price
applied_total_amount
```

を利用。

---

# 11. 監査対応

監査時は：

- applied_rate_id
- applied_unit_price
- applied_position_name
- locked_at

を提示可能。

「当時の単価」を完全再現可能。

---

# 12. データ整合性保証

| イベント | 影響 |
|----------|------|
| 単価履歴変更 | Locked済みデータへ影響なし |
| API失敗 | 実績維持 |
| API再送 | 金額変動なし |
| 手当変更（Lock前） | 再計算 |
| 手当変更（Lock後） | 禁止 |

---

# 13. まとめ

本ERD改訂により：

- 金額確定の不可逆性保証
- 監査耐性強化
- 外部SaaS整合性維持
- 単価履歴安全更新
- 再送安全設計

を実現する。
