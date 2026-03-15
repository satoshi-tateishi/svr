from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required(login_url='accounts:login')
def performance_root(request):
    """旧 /performances/ 導線はダッシュボードへ集約"""
    return redirect('productions:dashboard')
