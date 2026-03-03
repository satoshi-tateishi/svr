# AUDIT_LOG_DESIGN_v2.md

## 公演手配管理システム 監査ログ詳細設計書（単価スナップショット対応版）

* * *

# 1. 設計目的

監査ログの目的は：

-   実績改ざん防止
-   トラブル時の追跡
-   SaaS送信証跡の確保
-   権限乱用の抑止
-   法的リスク低減
-   単価確定証跡の保持（スナップショット方式対応）

* * *

# 2. 記録方針

## 2.1 原則

-   物理削除禁止
-   更新禁止（append-only）
-   監査ログ自体は編集不可
-   DBレベルでUPDATE/DELETE禁止推奨
-   すべてService層経由で記録

* * *

# 3. ログ対象イベント

* * *

## 3.1 重要度：最上位（必須）

1.  Assignment確定
2.  Locked実行
3.  Locked解除（Adminのみ）
4.  Staff変更
5.  Vehicle変更
6.  API送信
7.  API再送
8.  公演無効化（is_active=False）
9.  単価履歴作成
10.  単価履歴更新
11.  単価履歴無効化
12.  コストスナップショット生成
13.  コストスナップショット再生成

* * *

## 3.2 中重要度

1.  PhaseSlot時間変更
2.  バッファ変更
3.  Request内容変更
4.  PerformanceMember追加/削除

* * *

## 3.3 ログ対象外

-   閲覧操作
-   ダッシュボード表示
-   フィルタリング操作

* * *

# 4. AuditLogエンティティ設計

* * *

## 4.1 AuditLog

| Field | Type | 説明  |
| --- | --- | --- |
| id  | PK  |     |
| event_type | varchar | イベント種別 |
| actor_user_id | FK -> User | 実行者 |
| system_role_snapshot | varchar | 実行時system_role |
| performance_role_snapshot | varchar | 実行時公演ロール |
| related_object_type | varchar | 例: PhaseSlot |
| related_object_id | int | 対象ID |
| before_state | JSON | 変更前状態 |
| after_state | JSON | 変更後状態 |
| ip_address | varchar | 任意  |
| user_agent | varchar | 任意  |
| created_at | datetime | 作成日時 |

※エンティティ構造の追加変更は不要（JSON拡張で対応）

* * *

# 5. event_type一覧（v2）

## 5.1 既存

-   ASSIGNMENT_CONFIRMED
-   PHASE_SLOT_LOCKED
-   PHASE_SLOT_UNLOCKED
-   STAFF_ASSIGNED
-   STAFF_REMOVED
-   VEHICLE_ASSIGNED
-   VEHICLE_REMOVED
-   API_SEND_SUCCESS
-   API_SEND_FAILED
-   API_RETRY
-   PERFORMANCE_DEACTIVATED
-   PHASE_SLOT_UPDATED
-   REQUEST_UPDATED

## 5.2 単価関連（新規追加）

-   UNIT_PRICE_HISTORY_CREATED
-   UNIT_PRICE_HISTORY_UPDATED
-   UNIT_PRICE_HISTORY_DEACTIVATED

## 5.3 スナップショット関連（新規追加）

-   COST_SNAPSHOT_CREATED
-   COST_SNAPSHOT_REGENERATED

* * *

# 6. スナップショット保持仕様

## 6.1 スナップショット生成タイミング

-   PhaseSlot.status = Locked へ遷移時
-   Unlock後再Lock時

生成処理は：

LockService.lock_phase_slot() 内で実行。

* * *

## 6.2 スナップショットJSON例

after_state例：

コード

{  
  "phase_slot_id": 120,  
  "staff_cost_total": 80000,  
  "vehicle_cost_total": 40000,  
  "grand_total": 120000,  
  "staff_details": [  
    {  
      "staff_id": 3,  
      "unit_price": 20000,  
      "quantity": 4,  
      "subtotal": 80000  
    }  
  ],  
  "vehicle_details": [  
    {  
      "vehicle_id": 2,  
      "unit_price": 20000,  
      "quantity": 2,  
      "subtotal": 40000  
    }  
  ],  
  "calculation_version": 1,  
  "snapshot_hash": "sha256:xxxxxxxx"  
}

* * *

## 6.3 snapshot_hashの目的

-   改ざん検知
-   法的防御力向上
-   将来の外部監査対応

計算対象：

-   JSONを正規化
-   SHA-256ハッシュ生成
-   変更不可

* * *

# 7. 単価履歴ログ仕様

## 7.1 単価履歴作成

UNIT_PRICE_HISTORY_CREATED

after_state例：

コード

{  
  "staff_id": 3,  
  "performance_id": 12,  
  "position": "Chief",  
  "unit_price": 20000,  
  "valid_from": "2026-04-01",  
  "valid_to": null  
}

* * *

## 7.2 単価履歴更新

before_stateとafter_state両方保存。

理由：

-   遡及修正の追跡
-   不正変更検出

* * *

# 8. Locked解除特別ルール

解除時は必ず：

-   理由入力必須
-   reasonをafter_stateへ保存

例：

コード

{  
  "unlock_reason": "入力ミス修正のため"  
}

Unlock後再Lock時は：

-   COST_SNAPSHOT_REGENERATED を必ず記録

* * *

# 9. 記録タイミング

| イベント | 記録箇所 |
| --- | --- |
| Assignment確定 | confirm_assignment()成功直後 |
| Locked実行 | LockService内 |
| Snapshot生成 | LockService内 |
| 単価履歴変更 | UnitPriceService内 |
| API送信 | ApiIntegrationService内 |

* * *

# 10. 改ざん耐性

## 10.1 DB制約

-   UPDATE禁止
-   DELETE禁止
-   Append-onlyテーブル設計

## 10.2 Django防御

コード

def save(self, *args, **kwargs):  
    if self.pk is not None:  
        raise ValidationError("AuditLog is immutable")

* * *

# 11. 表示ポリシー

| Role | 閲覧範囲 |
| --- | --- |
| Admin | 全ログ閲覧可 |
| Editor | 関与公演のみ |
| Planner | 自公演のみ |
| General | 不可  |
| Viewer | 不可  |

* * *

# 12. パフォーマンス設計

必須index：

-   created_at
-   related_object_id
-   event_type

保存期間：

-   5年保存
-   それ以降アーカイブ可能

* * *

# 13. APIログとの関係

ApiTransmissionLog：

-   技術ログ
-   再送制御

AuditLog：

-   業務証跡
-   法的根拠

役割は明確に分離。

* * *

# 14. 同時実行安全性

-   元処理と同一トランザクション内で記録
-   ロールバック時はログもロールバック

例外：

-   外部API成功後のログは独立可

* * *

# 15. テスト項目（v2追加）

必須：

-   単価履歴作成でログ生成
-   単価履歴更新でbefore/after保存
-   Locked時にCOST_SNAPSHOT_CREATED生成
-   Unlock→再LockでCOST_SNAPSHOT_REGENERATED生成
-   snapshot_hash検証
-   ログ編集不可確認

* * *

# 16. 将来拡張

-   CSVエクスポート
-   公演単位履歴UI
-   差分可視化
-   ハッシュ外部保存（改ざん耐性強化）
-   外部監査連携

* * *

# 完成度評価（v2）

-   法的防御力：高
-   単価確定証跡：強
-   改ざん耐性：高
-   内部統制レベル：中〜高
-   小規模企業適正：維持
-   過剰実装：なし

