# 工程テンプレートの定義（実務準拠版 v5）

# ロケーションのグループ定義
LOCATION_GROUPS = {
    'rehearsal': {'label': '稽古場', 'default_slots': 2},
    'venue': {'label': '劇場', 'default_slots': 2},
    'warehouse': {'label': '倉庫', 'default_slots': 1},
    'other': {'label': 'その他', 'default_slots': 1},
}

# 基本ブロック（汎用的な「型」）
BASIC_BLOCKS = [
    {
        'key': 'rehearsal_setup',
        'label': '稽古場仕込み',
        'mode': 'date_range_same_task',
        'location_group': 'rehearsal',
        'tasks': ['rehearsal-setup'],
        'default_enabled': True,
    },
    {
        'key': 'rehearsal',
        'label': '稽古',
        'mode': 'date_range_same_task',
        'location_group': 'rehearsal',
        'tasks': ['rehearsal'],
        'default_enabled': True,
    },
    {
        'key': 'rehearsal_strike',
        'label': '稽古場バラシ',
        'mode': 'single_day',
        'location_group': 'rehearsal',
        'tasks': ['rehearsal-strike'],
        'default_enabled': True,
    },
    {
        'key': 'theatre_setup',
        'label': '劇場仕込み',
        'mode': 'date_range_same_task',
        'location_group': 'venue',
        'tasks': ['theatre-setup'],
        'default_enabled': True,
    },
    {
        'key': 'stage_rehearsal',
        'label': '劇場舞台稽古',
        'mode': 'date_range_same_task',
        'location_group': 'venue',
        'tasks': ['stage-rehearsal'],
        'default_enabled': True,
    },
    {
        'key': 'performance',
        'label': '本番',
        'mode': 'date_range_performance',
        'location_group': 'venue',
        'tasks': ['performance'],
        'default_enabled': True,
    },
    {
        'key': 'theatre_strike',
        'label': '劇場バラシ',
        'mode': 'single_day',
        'location_group': 'venue',
        'tasks': ['theatre-strike'],
        'default_enabled': True,
    },
]

# 補助ブロック（任意追加・物流・イベント）
AUXILIARY_BLOCKS = [
    {
        'key': 'kizai_standby_rehearsal',
        'label': '機材スタンバイ(稽古)',
        'mode': 'single_day',
        'location_group': 'rehearsal',
        'tasks': ['kizai-standby'],
        'default_enabled': False,
    },
    {
        'key': 'kizai_standby_performance',
        'label': '機材スタンバイ(本番)',
        'mode': 'single_day',
        'location_group': 'venue',
        'tasks': ['kizai-standby'],
        'default_enabled': False,
    },
    {
        'key': 'kizai_standby_travel',
        'label': '機材スタンバイ(旅)',
        'mode': 'single_day',
        'location_group': 'other',
        'tasks': ['kizai-standby'],
        'default_enabled': False,
    },
    {
        'key': 'warehouse_load',
        'label': '倉庫荷積み',
        'mode': 'single_day',
        'location_group': 'warehouse',
        'tasks': ['warehouse-load'],
        'default_enabled': False,
    },
    {
        'key': 'warehouse_unload',
        'label': '倉庫荷降ろし',
        'mode': 'single_day',
        'location_group': 'warehouse',
        'tasks': ['warehouse-unload'],
        'default_enabled': False,
    },
    {
        'key': 'theatre_unload',
        'label': '劇場荷降ろし',
        'mode': 'single_day',
        'location_group': 'venue',
        'tasks': ['theatre-unload'],
        'default_enabled': False,
    },
    {
        'key': 'transport',
        'label': '移動',
        'mode': 'single_day',
        'location_group': 'other',
        'tasks': ['transport'],
        'default_enabled': False,
    },
    {
        'key': 'recording',
        'label': '録音',
        'mode': 'single_day',
        'location_group': 'rehearsal',
        'tasks': ['recording'],
        'default_enabled': False,
    },
    {
        'key': 'press_conference',
        'label': '記者会見',
        'mode': 'single_day',
        'location_group': 'other',
        'tasks': ['press'],
        'default_enabled': False,
    },
    {
        'key': 'reload',
        'label': '積み替え',
        'mode': 'single_day',
        'location_group': 'other',
        'tasks': ['reload'],
        'default_enabled': False,
    },
    {
        'key': 'final_unload',
        'label': '最終荷降ろし',
        'mode': 'single_day',
        'location_group': 'warehouse',
        'tasks': ['final-unload'],
        'default_enabled': False,
    },
]

PRODUCTION_TEMPLATES = {
    'standard': {
        'label': '標準公演テンプレート',
        'blocks': BASIC_BLOCKS + AUXILIARY_BLOCKS,
    }
}
