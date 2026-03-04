#!/usr/bin/env python
"""Django の manage.py エントリポイント"""

import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'Django が見つかりません。仮想環境が有効化されているか、'
            'requirements.txt がインストール済みか確認してください。'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
