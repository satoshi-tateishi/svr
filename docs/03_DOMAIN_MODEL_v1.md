# Django ドメインモデル仕様

## 1. ドメイン境界

現行コードは次の 2 つの業務境界に分かれています。

### productions

制作・申請・工程入力のためのドメイン。

### performances

確定実績・Lock・帳票出力のためのドメイン。

この分離を無視して 1 つの集約として扱うと、実装と文書が乖離します。

## 2. モデル責務

### `Production`

- 公演案件の入力単位
- 工程ブロック群の親
- 公演単位担当者の親

### `Process`

- 公演内ブロック
- `block_key` により UI テンプレートと連携

### `ProcessRequestUnit`

- ブロック内の申請単位
- 新しい UI は `ProcessRequestUnit` 中心
- `ProcessDay` は既存 UI 互換の役割も残る

### `ProcessDay`

- 既存モーダル編集の中心単位
- 人員申請・車両申請の親

### `StaffRequest`

- 制作が入力する人員希望
- 数量・時間帯・本人含むフラグを保持

### `VehicleRequest`

- 制作が入力する配車希望
- 1 レコード 1 便の粒度
- 車両種別希望と配車希望時間、到着希望時間を保持

### `productions.VehicleAssignment`

- 申請に対する管理側の手配結果
- 実績固定前の「管理状態」

### `Performance`

- 実績帳票の親
- `productions.Production` の置換ではなく別集約

### `Phase`

- 標準工程の 1 要素
- `PhaseService` が一括展開する

### `PhaseSlot`

- 人員実績確定の単位
- Lock 状態を持つ

### `StaffAssignment`

- 実績人員割当
- 占有時間と Lock スナップショットを持つ

### `PerformanceFreelanceRate`

- 単価履歴
- 上書きではなく期間で管理する

### `Vehicle`

- 共有マスタ
- `productions` と `performances` の両方から参照される

### `VehicleOperation`

- 実績運行工程
- 希望値と確定値を別フィールドで保持する

### `performances.VehicleAssignment`

- 実績配車割当
- Lock 時に原価スナップショットを固定する

## 3. 重要な不変条件

### Lock 後不変

- `PhaseSlot.status == LOCKED`
- `VehicleOperation.status == LOCKED`

のレコードは、解除や再計算を前提に扱わない。

### スナップショット参照

- PDF や外部連携は `applied_*` を参照する
- 元の単価テーブルや申請テーブルを遡って再計算しない

### 権限分離

- 全体権限は `UserProfile.system_role`
- 公演単位権限は `ProductionMember.role`

## 4. 現時点で存在しないもの

以下は旧設計に登場するが、現行コードには存在しないか未実装です。

- `FinancialSnapshot` モデル
- AuditLog モデル
- Unlock API
- `Production` と `Performance` の自動同期
