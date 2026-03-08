from django import forms

from .models import Position, ProcessDay, ProcessType, StaffRequest

_CSS_SELECT = (
    'form-select block w-full rounded-md border-gray-300 shadow-sm '
    'focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
)
_CSS_INPUT = (
    'form-input block w-full rounded-md border-gray-300 shadow-sm '
    'focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
)
_CSS_TEXTAREA = (
    'form-textarea block w-full rounded-md border-gray-300 shadow-sm '
    'focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
)


class StaffRequestForm(forms.ModelForm):
    class Meta:
        model = StaffRequest
        fields = ['position', 'quantity', 'note']
        widgets = {
            'position': forms.Select(attrs={'class': _CSS_SELECT}),
            'quantity': forms.NumberInput(attrs={'min': 1, 'class': _CSS_INPUT}),
            'note': forms.Textarea(
                attrs={'rows': 2, 'placeholder': '備考（任意）', 'class': _CSS_TEXTAREA}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['position'].queryset = Position.objects.all().order_by('order')


class ProcessDayForm(forms.ModelForm):
    class Meta:
        model = ProcessDay
        fields = [
            'process_type',
            'date',
            'location',
            'start_time',
            'end_time',
            'order',
            'note',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': _CSS_INPUT}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': _CSS_INPUT}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': _CSS_INPUT}),
            'location': forms.TextInput(attrs={'class': _CSS_INPUT}),
            'process_type': forms.Select(attrs={'class': _CSS_SELECT}),
            'order': forms.NumberInput(attrs={'class': _CSS_INPUT}),
            'note': forms.Textarea(attrs={'rows': 3, 'class': _CSS_TEXTAREA}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # カテゴリーの定義（順序とラベル）
        category_defs = {
            'rehearsal': '稽古場関連',
            'venue': '劇場関連',
            'warehouse': '倉庫関連',
            'logistics': '荷積み荷降ろし・輸送関連',
            'performance': '本番関連',
            'other': 'その他',
        }

        # 一度のループで振り分けるためのバケットを作成
        buckets = {key: [] for key in category_defs.keys()}

        # 有効な工程タイプを一度のクエリで取得
        pts = ProcessType.objects.filter(is_active=True).order_by('order')
        for pt in pts:
            cat = pt.category if pt.category in buckets else 'other'
            buckets[cat].append((pt.id, pt.name))

        # 定義された順序に従って choices を組み立て
        grouped_choices = []
        for cat_key, cat_label in category_defs.items():
            if buckets[cat_key]:
                grouped_choices.append((cat_label, buckets[cat_key]))

        self.fields['process_type'].choices = grouped_choices
