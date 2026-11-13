"""Configured audit-only release validator.

validate(run_id) returns detached unsigned diagnostics after source rechecks.
It does not grant publication authority or write validation/release records.
audit(run_id) additionally signs and persists successful audit evidence using
explicit fixed signing configuration; it grants no publication authority.
recover(run_id) can complete only an existing, durable, signed publication tree
under the configured release root; it never initiates a fresh publication.
"""
from .formal_release_inputs import _ReleaseInputRefresh as FormalReleaseValidator

__all__ = ['FormalReleaseValidator']
