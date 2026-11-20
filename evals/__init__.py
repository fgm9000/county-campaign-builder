"""LLM evaluation suite (DeepEval). Importing this package silences DeepEval's side effects.

The variables are set here, before any DeepEval import, so they also hold when `evals` modules
are imported by tests. Existing values from the environment are respected (`setdefault`).
"""

import os
from collections.abc import Mapping
from types import MappingProxyType

DEEPEVAL_ENVIRONMENT: Mapping[str, str] = MappingProxyType(
    {
        "DEEPEVAL_TELEMETRY_OPT_OUT": "1",
        "DEEPEVAL_DISABLE_DOTENV": "1",
        "DEEPEVAL_UPDATE_WARNING_OPT_IN": "0",
        "DEEPEVAL_GRPC_LOGGING": "0",
        "ENABLE_DEEPEVAL_CACHE": "0",
        "CONFIDENT_OPEN_BROWSER": "0",
        "CONFIDENT_TRACE_FLUSH": "0",
    }
)


def apply_deepeval_environment() -> None:
    """Apply non-intrusive DeepEval environment defaults without overriding explicit settings."""
    for name, value in DEEPEVAL_ENVIRONMENT.items():
        os.environ.setdefault(name, value)


apply_deepeval_environment()
