# DATA_FLOW_DIAGRAM_v4.md

## 公演手配管理システム データフロー図設計書（人員・配車・テンプレート統合版）

* * *

# 1. 設計目的

-   テンプレート展開から実績確定までのデータライフサイクルを可視化
-   **人員単価** と **車輌原価** の同時スナップショット確定プロセスの明示
-   「希望（Request） vs 確定（Assignment）」のデータ保持構造の分離
-   🔒 Lock後の完全な不変性（Immutable）の保証

* * *

# 2. 業務フロー全体像

* * *

# 3. 主要データフロー（レベル1プロセス）

Plaintext

```
(1) テンプレート展開 (PhaseService)
    - 1〜9の標準工程を一括生成
    - 録音などのカスタム工程の手動追加

(2) 手配申請 (Request Phase)
    - 人員：希望人数 (requested_staff_count) の設定
    - 配車：希望時間 (requested_start/end) とルートの設定

(3) 手配確定 (Assignment Phase)
    - 人員：スタッフ割当 + 重複チェック
    - 配車：実車輌割当 + 確定時間 (scheduled_start/end) 設定

(4) 原価入力 (Costing Phase)
    - 外注車輌・ドライバー費の最終金額入力

(5) 🔒 Lock (スナップショット確定)
    - 単価検索 + 原価固定 + スナップショット保存

(6) SaaS連携 (External Integration)
    - 🔒保存済スナップショットデータの送信
```

* * *

# 4. 🔒 実績ロック・スナップショットフロー（詳細）

このプロセスは `LockService` により `atomic` トランザクションで実行される。

Plaintext

```
Planner / Editor (Lockボタン押下)
   ↓
LockService.lock_execution()
   ↓
PhaseSlot & VehicleOperation (select_for_update)
   ↓
StaffAssignment & VehicleAssignment (select_for_update)
   ↓
-------------------------------------------------------
[人員スナップショット処理]
   if is_freelance:
       applicable_rate検索 (FreelanceRateService)
       ↓
       🔒 StaffAssignmentへ保存:
          - applied_unit_price
          - applied_allowance_total
          - applied_total_amount
          - applied_position_name

[配車スナップショット処理]
   if is_external or need_costing:
       確定入力済みの原価を取得
       ↓
       🔒 VehicleAssignmentへ保存:
          - applied_cost_amount (確定原価)
          - applied_sales_amount (請求用金額)

[共通メタデータ保存]
   - locked_at = NOW()
-------------------------------------------------------
   ↓
各Status = Locked へ遷移
   ↓
AuditLog記録 (「希望vs確定」の最終乖離値も記録)
   ↓
ApiIntegrationService.enqueue_send()
```

* * *

# 5. API送信・再送フロー（スナップショット参照）

Plaintext

```
ApiIntegrationService
   ↓
StaffAssignment.applied_* 取得
VehicleAssignment.applied_* 取得
   ↓
payload生成 (マスタ再検索・再計算は厳禁)
   ↓
ApiTransmissionLog保存 (payload_snapshot)
   ↓
freee (支払・給与) / board (売上・外注費) API呼出
```

* * *

# 6. 「希望 vs 確定」の乖離比較フロー

Plaintext

```
DashboardQueryService
   ↓
1. 人員数比較:
   PhaseSlot.requested_staff_count 
   vs 
   COUNT(StaffAssignment)

2. 配車時間比較:
   VehicleOperation.requested_start 
   vs 
   VehicleOperation.scheduled_start

3. 警告表示:
   - 欠員あり
   - 時間大幅変更
   - Lock漏れ（過去日付の未Lock）
```

* * *

# 7. 状態遷移（Status）と制約

| ステータス | 人員変更 | 車輌変更 | 金額変更 | 時間変更 |
| --- | --- | --- | --- | --- |
| **Draft** | 可   | 可   | 可   | 可   |
| **Assigned** | 可   | 可   | 可   | 可   |
| **🔒 Locked** | **禁止** | **禁止** | **禁止** | **禁止** |

Google スプレッドシートにエクスポート

* * *

# 8. 設計思想の最終確認

1.  **金額・時間はLock時に「結晶化」する**: 一度結晶化したデータは、外部マスタ（単価履歴）が変わっても、物理的な走行距離が変わっても、本システム内では「確定実績」として保護される。
2.  **比較可能性の維持**: 制作の「最初の希望」を上書きせず残すことで、手配の負荷や無理なスケジュールの可視化を行う。
3.  **SaaSとの整合性**: 自作アプリは「何を確定させたか」のスナップショットを証跡として持ち、SaaS側での修正が必要な場合は、その差分を別途管理する。



