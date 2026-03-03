# TEST_CASE_DESIGN_v2.md

## 公演手配管理システム テストケース完全設計書（単価スナップショット対応版）

* * *

# 1. テスト戦略（v2）

## 目的

-   業務事故ゼロ
-   ダブルブッキングゼロ
-   権限突破ゼロ
-   ロック破壊ゼロ
-   API暴走ゼロ
-   単価改ざんゼロ
-   スナップショット不整合ゼロ

* * *

## テストレイヤー

1.  Service単体テスト（最重要）
2.  単価履歴テスト
3.  スナップショットテスト
4.  権限テスト
5.  状態遷移テスト
6.  API統合テスト（モック）
7.  監査ログ検証テスト
8.  View最小確認テスト

* * *

# 2. 単価履歴テスト（新規）

* * *

## TC-UP-01 単価履歴作成（正常）

前提：AdminまたはEditor

期待：

-   UnitPriceHistory作成成功
-   AuditLog生成（UNIT_PRICE_HISTORY_CREATED）

* * *

## TC-UP-02 単価履歴更新

期待：

-   before_state保存
-   after_state保存
-   AuditLog生成（UNIT_PRICE_HISTORY_UPDATED）

* * *

## TC-UP-03 単価有効期間判定

valid_from=2026-01-01  
slot日付=2026-02-01

期待：

-   正しい単価が取得される

* * *

## TC-UP-04 単価履歴無効化

is_active=False

期待：

-   取得対象外
-   AuditLog生成

* * *

## TC-UP-05 有効期間重複

同一ユーザー・期間重複登録

期待：

-   ValidationError

* * *

# 3. スナップショットテスト（新規最重要）

* * *

## TC-SNAP-01 Lock時スナップショット生成

期待：

-   CostSnapshot生成
-   snapshot_hash生成
-   COST_SNAPSHOT_CREATEDログ生成

* * *

## TC-SNAP-02 snapshot_hash整合性

snapshot_json再ハッシュ

期待：

-   保存hashと一致

* * *

## TC-SNAP-03 Unlock→再Lock

期待：

-   COST_SNAPSHOT_REGENERATED生成
-   新hash生成
-   旧snapshot上書き

* * *

## TC-SNAP-04 Lock後単価変更

手順：

1.  Lock
2.  UnitPrice変更
3.  再Lock

期待：

-   新snapshot金額反映
-   ログ両方保存

* * *

## TC-SNAP-05 Lock後単価変更のみ

再Lockしない

期待：

-   既存snapshot不変

* * *

# 4. Performance関連（既存＋監査追加）

* * *

## TC-P-01 公演作成（正常）

期待：

-   Performance作成成功
-   is_active=True

* * *

## TC-P-03 公演無効化

期待：

-   is_active=False
-   PERFORMANCE_DEACTIVATEDログ生成

* * *

# 5. PhaseSlot関連（既存＋スナップショット前提）

* * *

## TC-S-05 Locked状態での更新禁止

期待：

-   update_phase_slot()例外
-   DB未変更

* * *

# 6. ダブルブッキング検出（変更なし）

既存ケース維持

追加：

* * *

## TC-C-05 同時Lock競合

同一slotを並列Lock実行

期待：

-   select_for_updateにより1回のみ成功
-   競合なし

* * *

# 7. Request / Assignment

* * *

## TC-A-04 Assignment→Lock一連成功

期待：

-   Assigned
-   Snapshot生成
-   Locked

* * *

# 8. Locked耐性（強化）

* * *

## TC-L-03 Snapshot直接編集試行

CostSnapshot.save()

期待：

-   禁止（ValidationError）

* * *

# 9. 監査ログ拡張テスト

* * *

## TC-LOG-03 Snapshot生成ログ

期待：

-   after_stateに金額JSON存在
-   snapshot_hash存在

* * *

## TC-LOG-04 単価変更ログ

期待：

-   before/after両方保存

* * *

## TC-LOG-05 ログ改ざん試行

AuditLog.save()更新

期待：

-   ValidationError

* * *

# 10. トランザクション耐性（拡張）

* * *

## TC-TX-03 Snapshot生成中例外

途中例外発生

期待：

-   PhaseSlot未Locked
-   Snapshot未保存

* * *

# 11. API送信（変更なし）

既存ケース維持

追加：

* * *

## TC-API-05 Snapshot未生成でAPI送信禁止

期待：

-   ValidationError

* * *

# 12. セキュリティ（強化）

* * *

## TC-SEC-03 単価履歴直接削除試行

期待：

-   論理削除のみ
-   物理削除不可

* * *

## TC-SEC-04 Unlock理由未入力

期待：

-   ValidationError

* * *

# 13. パフォーマンス（拡張）

* * *

## TC-PERF-02 1000件監査ログ生成

期待：

-   応答性能維持
-   index有効

* * *

## TC-PERF-03 Snapshot大量生成

期待：

-   30人同時Lockでも競合なし

* * *

# 14. 回帰テスト必須領域（v2）

最重要：

1.  単価有効期間判定
2.  スナップショット生成
3.  snapshot_hash一致
4.  Unlock→再Lock
5.  ダブルブッキング
6.  Locked耐性
7.  権限突破防止

* * *

# 15. テスト実行優先順位（v2）

最優先：

1.  スナップショット整合性
2.  単価履歴有効期間
3.  ダブルブッキング
4.  Locked耐性
5.  監査ログ改ざん耐性

* * *

# v2完成度

-   法的防御力検証可能
-   改ざん耐性テスト網羅
-   スナップショット整合性保証
-   再Lock安全性検証
-   小規模運用に過不足なし

