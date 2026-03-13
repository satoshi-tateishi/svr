# 工程テンプレートの定義（紙フォーム「車及び人員手配書」準拠版）

# ブロック定義
# mode:
#   'single_day'    : 単日工程（日付・人員・車両を持つ）
#   'sumida_check'  : すみだ便必要/不要フラグのみ
#   'kizai_standby' : 機材スタンバイ助っ人フラグ + 人数
#   'memo'          : 自由備考テキストのみ
SETUP_BLOCKS = [
    {
        'key': 'rehearsal_setup',
        'label': '稽古場仕込み',
        'mode': 'single_day',
        'icon': 'fa-solid fa-screwdriver-wrench',
        'color': 'indigo',
        'description': '車両申請・積み込み・搬入・仕込み人員',
        'default_enabled': True,
    },
    {
        'key': 'sumida_check',
        'label': 'すみだものチェック',
        'mode': 'sumida_check',
        'icon': 'fa-solid fa-warehouse',
        'color': 'sky',
        'description': 'すみだ便必要/不要',
        'default_enabled': True,
    },
    {
        'key': 'kizai_standby',
        'label': '本番機材スタンバイ',
        'mode': 'kizai_standby',
        'icon': 'fa-solid fa-person-digging',
        'color': 'amber',
        'description': '助っ人必要/不要・人数',
        'default_enabled': True,
    },
    {
        'key': 'rehearsal_strike',
        'label': '稽古場バラシ',
        'mode': 'single_day',
        'icon': 'fa-solid fa-box-open',
        'color': 'gray',
        'description': 'バラシ人員・車両申請',
        'default_enabled': True,
    },
    {
        'key': 'theatre_setup',
        'label': '劇場仕込み',
        'mode': 'single_day',
        'icon': 'fa-solid fa-building-columns',
        'color': 'purple',
        'description': '車両申請・搬入・仕込み・舞台稽古・初日人員',
        'default_enabled': True,
    },
    {
        'key': 'theatre_strike',
        'label': '劇場バラシ',
        'mode': 'single_day',
        'icon': 'fa-solid fa-truck-ramp-box',
        'color': 'gray',
        'description': 'バラシ人員・車両申請',
        'default_enabled': True,
    },
    {
        'key': 'travel_load',
        'label': '旅荷積み',
        'mode': 'single_day',
        'icon': 'fa-solid fa-train',
        'color': 'teal',
        'description': '旅行荷物の積み込み・車両申請',
        'default_enabled': False,
    },
    {
        'key': 'travel_unload',
        'label': '旅荷降ろし',
        'mode': 'single_day',
        'icon': 'fa-solid fa-dolly',
        'color': 'teal',
        'description': '旅行荷物の荷降ろし・車両申請',
        'default_enabled': False,
    },
]

PRODUCTION_TEMPLATES = {
    'standard': {
        'label': '標準公演テンプレート',
        'blocks': SETUP_BLOCKS,
    }
}

# ProcessBlockEditView で各ブロックが生成する ProcessType スラッグのマッピング
BLOCK_PROCESS_TYPE_MAP = {
    'rehearsal_setup': 'rehearsal-setup',
    'rehearsal_strike': 'rehearsal-strike',
    'theatre_setup': 'theatre-setup',
    'theatre_strike': 'theatre-strike',
    'travel_load': 'warehouse-load',
    'travel_unload': 'warehouse-unload',
}

# ProcessBlockEditView で使用する Position スラッグのマッピング
BLOCK_POSITION_MAP = {
    'rehearsal_setup': {
        'setup-crew': '仕込み',  # 稽古場仕込み人員
    },
    'rehearsal_strike': {
        'strike-crew': 'バラシ',  # 稽古場バラシ人員
        'loading': '積み込み',  # 稽古場搬出人員
        'unloading': '荷降ろし',  # 倉庫荷降ろし人員
    },
    'theatre_setup': {
        'setup-crew': '仕込み',  # 劇場仕込み人員
    },
    'theatre_strike': {
        'strike-crew': 'バラシ',  # 劇場バラシ人員
        'loading': '積み込み',  # 劇場搬出人員
        'unloading': '荷降ろし',  # 倉庫荷降ろし人員
    },
    'travel_load': {
        'loading': '積み込み',  # 旅荷積み人員
    },
    'travel_unload': {
        'unloading': '荷降ろし',  # 旅荷降ろし人員
    },
    'kizai_standby': {
        'helper': '助っ人',
    },
}
