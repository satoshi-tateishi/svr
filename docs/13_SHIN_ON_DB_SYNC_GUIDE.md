# shin-on_db 同期ガイド

## 1. 概要

shin-on_db が提供する内部APIから、マスターデータを svr のローカルDBに同期する機能です。

| 対象マスター | svr モデル | 同期トリガー |
|-------------|-----------|-------------|
| 使用場所マスター | `apps.locations.Location` | 管理画面のボタン操作 |

---

## 2. 認証

svr ユーザーがブラウザに持つ `portal_jwt` Cookie の値を、そのまま `Authorization: Bearer` ヘッダーに設定して shin-on_db API を呼び出します。

```
portal_jwt Cookie → Authorization: Bearer <token> → shin-on_db API
```

Portal SSO で認証済みであれば追加の設定なしにAPIを利用できます。

---

## 3. 場所マスター同期

### 同期フロー

1. ユーザーが管理画面 `/admin/locations/location/sync/` を開く
2. 「同期を実行する」ボタンを押す（POST）
3. `portal_jwt` Cookie を取得し、shin-on_db API `/api/v1/locations` を呼び出す
4. 取得データを `update_or_create`（`shin_on_db_id` をキーにupsert）
5. APIレスポンスに含まれなくなったレコードを `is_active=False` に更新
6. 作成・更新・無効化の件数を画面に表示

### 手動登録レコードの扱い

`shin_on_db_id = NULL` のレコード（管理画面から手動登録）は同期対象外です。無効化されません。

### 実装ファイル

| ファイル | 役割 |
|---------|------|
| `apps/locations/models.py` | `shin_on_db_id` フィールド（同期元IDの紐付けキー） |
| `apps/locations/services.py` | `sync_locations_from_shin_on_db()` 同期ロジック |
| `apps/locations/admin.py` | 管理画面カスタムビュー |
| `templates/admin/locations/location/sync.html` | 確認・結果ページ |

---

## 4. 設定

### 環境変数

```env
# shin-on_db 内部API URL（Docker コンテナ名で指定）
SHIN_ON_DB_API_URL=http://shin-on_db_app
```

`settings.py` の `SHIN_ON_DB_API_URL` に反映されます。

---

## 5. Docker ネットワーク設定

svr の `docker-compose.yml` はすでに `shin-on-internal` ネットワークに参加しています。shin-on_db 側も同ネットワークへの参加が必要です（設定済み）。

参加コンテナが増えた場合は `docker network connect shin-on-internal <container>` で追加します。

---

## 6. API仕様

shin-on_db が提供するAPIの詳細仕様（エンドポイント・レスポンスフィールド・実装例）は shin-on_db リポジトリのドキュメントを参照してください：

**`shin-on_db/claude/docs/Internal_API_Guide.md`**
