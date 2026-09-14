# -*- coding: utf-8 -*-
"""EOJ 站点交互层。"""

from .client import EOJClient, SubmitResult, PROBLEM_STATUS_MAP, parse_verdict

__all__ = ["EOJClient", "SubmitResult", "PROBLEM_STATUS_MAP", "parse_verdict"]
