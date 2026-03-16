from django import forms
from django.contrib.auth.models import User

from apps.performances.models.vehicle import Vehicle

from .models import (
    Position,
    ProcessDay,
    ProcessType,
    Production,
    ProductionMember,
    StaffRequest,
    VehicleAssignment,
)

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
            'note',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': _CSS_INPUT}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': _CSS_INPUT}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': _CSS_INPUT}),
            'location': forms.TextInput(attrs={'class': _CSS_INPUT}),
            'process_type': forms.Select(attrs={'class': _CSS_SELECT}),
            'note': forms.Textarea(attrs={'rows': 3, 'class': _CSS_TEXTAREA}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].required = False

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


class VehicleAssignmentForm(forms.ModelForm):
    """車両手配フォーム（per-production モーダル用）

    arranged_departure/arrival_time は含めない。
    VehicleAssignmentEditView で使用しており、新フィールドの誤上書きを防ぐ。
    """

    class Meta:
        model = VehicleAssignment
        fields = ['status', 'assigned_vehicle', 'note']
        widgets = {
            'status': forms.Select(attrs={'class': _CSS_SELECT}),
            'assigned_vehicle': forms.Select(attrs={'class': _CSS_SELECT}),
            'note': forms.Textarea(
                attrs={'rows': 3, 'placeholder': '管理メモ（任意）', 'class': _CSS_TEXTAREA}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_vehicle'].queryset = Vehicle.objects.filter(is_active=True).order_by(
            'order', 'name'
        )
        self.fields['assigned_vehicle'].empty_label = '--- 未設定 ---'


class VehicleAssignmentAssignForm(forms.ModelForm):
    """車両割当フォーム（配車編集UI のインライン割当用）"""

    class Meta:
        model = VehicleAssignment
        fields = ['arranged_departure_time', 'arranged_arrival_time', 'status', 'assigned_vehicle']
        widgets = {
            'arranged_departure_time': forms.TimeInput(
                format='%H:%M',
                attrs={'type': 'time', 'class': _CSS_INPUT},
            ),
            'arranged_arrival_time': forms.TimeInput(
                format='%H:%M',
                attrs={'type': 'time', 'class': _CSS_INPUT},
            ),
            'status': forms.Select(attrs={'class': _CSS_SELECT}),
            'assigned_vehicle': forms.Select(attrs={'class': _CSS_SELECT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_vehicle'].queryset = Vehicle.objects.filter(is_active=True).order_by(
            'order', 'name'
        )
        self.fields['assigned_vehicle'].empty_label = '--- 未設定 ---'


class ProductionForm(forms.ModelForm):
    class Meta:
        model = Production
        fields = ['title', 'note']
        widgets = {
            'title': forms.TextInput(
                attrs={
                    'class': _CSS_INPUT,
                    'placeholder': '公演名を入力（例: ハムレット）',
                }
            ),
            'note': forms.Textarea(
                attrs={
                    'rows': 4,
                    'placeholder': '補足事項があれば入力',
                    'class': _CSS_TEXTAREA,
                }
            ),
        }


class ProductionMemberForm(forms.ModelForm):
    class Meta:
        model = ProductionMember
        fields = ['user', 'role', 'start_date', 'end_date', 'note']
        widgets = {
            'user': forms.Select(attrs={'class': _CSS_SELECT}),
            'role': forms.Select(attrs={'class': _CSS_SELECT}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': _CSS_INPUT}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': _CSS_INPUT}),
            'note': forms.Textarea(
                attrs={'rows': 2, 'placeholder': '備考（任意）', 'class': _CSS_TEXTAREA}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import UserProfile

        # is_active_staff=True のユーザーのみ選択肢に表示
        active_user_ids = UserProfile.objects.filter(is_active_staff=True).values_list(
            'user_id', flat=True
        )
        self.fields['user'].queryset = User.objects.filter(pk__in=active_user_ids).order_by(
            'profile__order', 'last_name', 'first_name'
        )
        # 表示ラベルを姓名で上書き
        self.fields['user'].label_from_instance = lambda u: (
            u.profile.full_name if hasattr(u, 'profile') else u.username
        )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')
        if start and end and start > end:
            raise forms.ValidationError('担当開始日は担当終了日より前に設定してください。')
        return cleaned_data
