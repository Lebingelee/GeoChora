"""Opt-in bounded provider-neutral lifecycle; no root facade or production rewrite."""
from .api import RuntimeSession, materialize, provider_manifest

__all__ = ['RuntimeSession', 'materialize', 'provider_manifest']
