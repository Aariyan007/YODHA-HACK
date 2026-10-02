"""Old name kept so scripts and notes that import `ai.jev_client` still work. The code lives in `ai.safety`.

(There was never a Jev service: this module is plain-Python safety rules, now backed by the DDInter dataset.)
"""
from .safety import *  # noqa: F401,F403
from .safety import allergy_hit, analyse, check_pair, check_pair_level, to_generic  # noqa: F401
