# 06_AUDIT_LOG_DESIGN_v3.md

## 公演手配管理システム 監査ログ詳細設計書（人員・配車・乖離ログ統合版）

* * *

# 1. 設計目的

監査ログの役割を「単なる変更履歴」から、**「支払・請求の法的根拠」**および**「手配精度の分析基盤」**へと格上げする。

-   **配車原価の確定証跡**: 外注費等の入力・確定プロセスの透明化。
-   **希望 vs 確定の乖離記録**: なぜ予定より人数が増えたか、なぜ時間がずれたかの理由（Reason）を強制保持。
-   **スナップショットの完全性**: Lock時の人員単価と車輌原価の同時パッケージング。

* * *

# 2. ログ対象イベント（追加・更新）

## 2.1 重要度：最上位（不変性の担保）

1.  **VEHICLE_ASSIGNED / REMOVED**: 車輌割当の変更。
2.  **VEHICLE_SCHEDULE_CONFIRMED**: 運行時間の確定（希望時間との差異発生タイミング）。
3.  **EXTERNAL_COST_FINALIZED**: 外注費・ドライバー費の最終入力。
4.  **PHASE_TEMPLATE_APPLIED**: テンプレート（1〜9）による一括生成実行。
5.  **STAFF_GAP_ACKNOWLEDGED**: 希望人数とアサイン人数が異なる状態でのLock承認。

* * *

# 3. AuditLog エンティティ拡張

`before_state` / `after_state` (JSON) に以下の要素を必須含める。

| カテゴリ | 記録すべきキー |
| --- | --- |
| **配車時間比較** | `requested_start`, `scheduled_start`, `time_diff_minutes` |
| **人員数比較** | `requested_count`, `actual_count`, `gap_reason` |
| **配車原価** | `vehicle_id`, `applied_cost_amount`, `cost_type(fixed/distance)` |

Google スプレッドシートにエクスポート

* * *

# 4. event_type 一覧（v3）

### 4.1 配車・工程関連

-   `PHASE_TEMPLATE_APPLIED`: テンプレート展開
-   `VEHICLE_OPERATION_CREATED`: 運行工程の追加
-   `VEHICLE_SCHEDULE_UPDATED`: 運行時間の変更（希望と確定の乖離発生）
-   `VEHICLE_COST_UPDATED`: 外注費の入力・修正

### 4.2 乖離・承認関連

-   `STAFF_COUNT_MISMATCH_LOCKED`: 人数不足状態でのLock実行
-   `SCHEDULE_DRIFT_LOCKED`: 希望時間から大幅に乖離した状態でのLock実行

* * *

# 5. スナップショット JSON 例（v3 統合版）

`PHASE_SLOT_LOCKED` 時の `after_state` は、人員と配車の情報を包括する。

JSON

```
{
  "lock_id": "LCK-2026-001",
  "performance_id": 12,
  "phase_name": "劇場仕込み",
  "financial_summary": {
    "total_staff_cost": 120000,
    "total_vehicle_cost": 45000,
    "grand_total": 165000
  },
  "staff_snapshot": [
    {
      "user_name": "山田太郎",
      "position": "Chief",
      "unit_price": 30000,
      "allowance": 5000
    }
  ],
  "vehicle_snapshot": [
    {
      "vehicle_name": "自社2t-A",
      "driver_name": "外注ドライバーA",
      "cost_amount": 15000,
      "is_external": true
    }
  ],
  "compliance": {
    "staff_count_gap": -1,
    "gap_reason": "急な欠員により1名減で対応",
    "schedule_drift_max": 45,
    "snapshot_hash": "sha256:abcd1234..."
  }
}
```

* * *

# 6. 特別ルール：希望と確定の乖離（Drift）

管理者が `VehicleOperation` の時間を確定する際、申請者の希望（Requested）から **60分以上の乖離** がある場合：

-   ログに `drift_warning: true` を付与。
-   `reason_for_drift`（渋滞、劇場都合、手配不可等）の入力を必須とし、ログに保存。

* * *

# 7. 記録タイミングとトランザクション

| イベント | 記録箇所 | 整合性要件 |
| --- | --- | --- |
| **テンプレート展開** | `PhaseService.apply_template` | 展開された全レコードIDをログに保持 |
| **外注費確定** | `VehicleService.finalize_cost` | Lock前の最終変更として記録 |
| **Lock実行** | `LockService.lock_execution` | 人員・車輌の全SSを同一TXで記録 |

Google スプレッドシートにエクスポート

* * *

# 8. 閲覧・監査ポリシー（強化）

-   **乖離レポート**: DashboardQueryService を通じて、`STAFF_COUNT_MISMATCH_LOCKED` などのログを統計的に集計し、「手配精度の低い案件」を特定可能にする。
-   **改ざん検知**: `snapshot_hash` を定期的にバッチで再計算し、DB上の値と一致するか検証する（改ざん検知アラート）。

* * *

# 9. 禁止事項

1.  **乖離理由の空欄保存**: 人数不足や時間変更時のLockにおいて、理由（Reason）がない状態でのログ記録を禁止する（Service層でバリデーション）。
2.  **ログの非同期記録**: 証跡の確実性を担保するため、メインの更新処理と同一トランザクション内で記録すること（API送信ログを除く）。



