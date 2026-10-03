"""Old name kept so scripts that import `ai.jev_client` still work. The real code is in `ai.safety`.

(There was never a Jev service. This is just the plain Python safety rules, now backed by DDInter.)
"""
from .safety import *  # noqa: F401,F403
from .safety import allergy_hit, analyse, check_pair, check_pair_level, to_generic  # noqa: F401
