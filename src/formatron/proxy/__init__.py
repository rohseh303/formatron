"""GrammarGuard admission proxy for vLLM / OpenAI-compatible inference servers.

Install with ``pip install formatron[proxy]`` and run ``python -m formatron.proxy --help``.
See ``README.md`` in this package for the error contract and policy tuning.
"""

from .admission import AdmissionService, Decision, DecisionCache, Stats
from .app import create_app
from .constraints import Constraint, ConstraintError, ConstraintRejected, extract_constraints
from .policy import EffectivePolicy, ProxySettings, resolve_policy

__all__ = [
    "AdmissionService",
    "Constraint",
    "ConstraintError",
    "ConstraintRejected",
    "Decision",
    "DecisionCache",
    "EffectivePolicy",
    "ProxySettings",
    "Stats",
    "create_app",
    "extract_constraints",
    "resolve_policy",
]
