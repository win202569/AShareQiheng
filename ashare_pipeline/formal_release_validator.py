"""Configured audit-only release validator.

validate(run_id) returns detached unsigned diagnostics after source rechecks.
It does not grant publication authority or write validation/release records.
"""
from .formal_release_inputs import _ReleaseInputRefresh as FormalReleaseValidator

__all__ = ['FormalReleaseValidator']
