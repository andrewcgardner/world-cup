"""
Supabase client helpers.

Two clients are exposed:
  - anon_client()   – uses the PUBLISHABLE key; safe to use for public reads.
  - admin_client()  – uses the SECRET key; required for writes / privileged ops.
"""

from functools import lru_cache

from supabase import create_client, Client

from config import get_settings


@lru_cache
def anon_client() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_publishable_key)


@lru_cache
def admin_client() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_secret_key)
