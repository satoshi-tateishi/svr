このプロジェクトの引き継ぎコンテキストです。

# プロジェクト概要
Django / Docker で、社内向けの「公演手配管理システム」を開発しています。
目的は、人員手配・車両配車・工程管理の一元化です。

# 技術スタック
- Django
- MySQL
- Docker
- HTMX
- Alpine.js
- TailwindCSS

# 設計思想（重要）
- Request / Assignment / Operation を分離
- Lock後は再計算禁止
- スナップショット保存
- 過去データ上書き禁止
- 物理削除禁止（論理削除前提）

# 現在の主要構造
- Performance
- Process
- ProcessDay
- StaffRequest / StaffAssignment
- Vehicle
- VehicleRequest / VehicleOperation / VehicleAssignment

# VehicleRequest の設計
1レコード = 1便
主なフィールド:
- requested_vehicle
- request_kind
- requested_time
- route_from
- route_to
- note

request_kind:
- loading（荷積み）
- preload（積み置き）
- load_in（搬入）
- pickup（引き取り）
- unloading（荷降ろし）
- other（その他）

# UI構成
- ProcessDay 単位で HTMX モーダル編集
- Alpine.js で bulk edit
- hidden input の requests_json で送信

# 実装済み
- StaffRequest 一括編集
- VehicleRequest 一括編集
- 人員の前日コピー
- 車両の直近コピー
- route_from / route_to
- preload（積み置き）

# 次に相談したいこと
（ここに今回の相談内容を書く）

# 現在のディレクトリ構成
src
├── apps
│   ├── accounts
│   │   ├── admin.py
│   │   ├── context_processors.py
│   │   ├── middleware.py
│   │   ├── migrations
│   │   ├── models.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── performances
│   │   ├── admin.py
│   │   ├── exceptions.py
│   │   ├── migrations
│   │   ├── models
│   │   ├── services
│   │   ├── tests
│   │   ├── urls.py
│   │   └── views.py
│   └── productions
│       ├── admin.py
│       ├── apps.py
│       ├── forms.py
│       ├── migrations
│       ├── models.py
│       ├── templates.py
│       ├── tests
│       ├── urls.py
│       └── views.py
├── config
│   ├── settings.py
│   ├── settings_test.py
│   ├── urls.py
│   └── wsgi.py
├── manage.py
└── templates
    ├── base.html
    ├── performances
    │   ├── create.html
    │   ├── dashboard.html
    │   ├── detail.html
    │   ├── includes
    │   ├── list.html
    │   └── reports
    └── productions
        ├── partials
        ├── process_day_form.html
        ├── production_detail.html
        ├── production_form.html
        ├── production_list.html
        ├── production_setup.html
        ├── staff_request_bulk_form.html
        ├── staff_request_form.html
        └── vehicle_request_bulk_form.html