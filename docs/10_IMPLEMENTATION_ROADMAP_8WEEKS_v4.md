# 実装ロードマップ

## 1. 完了済み

- Portal JWT 連携
- `productions` の公演一覧 / 詳細 / セットアップ
- 人員申請・車両申請の一括編集
- 公演担当者管理
- 車両手配管理
- `performances` の標準工程展開
- ダブルブッキング防止
- Lock
- PDF 出力
- 乖離ダッシュボード

## 2. 進行中と見るべき領域

### `productions` と `performances` のつなぎ込み

今の最大ギャップはここです。申請系と実績系が別集約なので、運用で橋渡ししている部分が残っています。

### 権限制御の横展開

`productions` 側はサービス化済みですが、`performances` 側はまだ簡易制御が混在しています。

### テストの厚み

`performances` に比べて `productions` のユースケース網羅が薄い箇所があります。

## 3. 次の優先順位

1. `productions` と `performances` の連携設計固定
2. Lock 済み編集禁止の UI / View レベル統一
3. AuditLog 実装
4. 本番起動系の確定
5. SaaS 連携の土台

## 4. やらない前提で扱うもの

現時点で「完了済み」と書かないこと:

- Unlock
- `FinancialSnapshot`
- 監査ログ基盤
- Celery 実運用
- SaaS API 連携
