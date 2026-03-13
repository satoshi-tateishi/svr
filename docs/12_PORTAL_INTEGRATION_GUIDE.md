# Portal 連携ガイド

## 1. 概要

`apps.accounts.middleware.PortalJWTMiddleware` が、Portal が発行した `portal_jwt` クッキーを検証し、Django セッションへログインを行います。

## 2. フロー

```text
portal_jwt クッキー受信
  ├─ sub(portal_uuid) で UserProfile を検索
  ├─ 見つからなければ email で User を検索して portal_uuid をリンク
  └─ 見つからなければ User を新規作成
```

## 3. 必要設定

- `PORTAL_JWKS_URL`
- `PORTAL_JWT_ISSUER`
- `PORTAL_JWT_AUDIENCE`
- `PORTAL_LOGIN_URL`

## 4. 実装上の注意

- `AuthenticationMiddleware` の後に `PortalJWTMiddleware` を置く
- 新規作成直後は `user.profile` を使う
- JWT が不正でも例外で全体を落とさず、認証をスキップする

## 5. 現在同期している項目

`UserProfile`:

- `portal_uuid`
- `family_name`
- `given_name`
- `phonetic_family_name`
- `phonetic_given_name`
- `phone_number`
- `email`

`User`:

- `first_name`
- `last_name`
- `email`

## 6. 既知の制約

- JWKS は `PyJWKClient` によりプロセス内キャッシュ
- 複数 `User` が同一 email を持つ場合は先頭 1 件を使う
- Portal 連携は `accounts` に閉じており、権限付与自体は別途 `system_role` / `ProductionMember` で管理する
