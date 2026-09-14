# -*- coding: utf-8 -*-
"""pytest 配置：把仓库根目录加入 ``sys.path``，使 ``import eojkit`` 生效。"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
