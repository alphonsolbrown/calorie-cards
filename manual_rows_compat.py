
# manual_rows_compat.py
# Backward-compatible wrapper so existing code that calls manual_rows("protein")
# keeps working without changing call sites. Internally forwards to the new
# manual_rows(section_key, fdc_api_key=...).
from __future__ import annotations
import os
import streamlit as st
from manual_rows_fix import manual_rows as _manual_rows_new

# Resolve API key once
_FDC_API_KEY = st.secrets.get("FDC_API_KEY", None) or os.getenv("FDC_API_KEY", "")

def manual_rows(section_key: str):
    """
    Back-compat signature: manual_rows(section_key) -> list of (name, amt, unit, cal)
    Uses the new safe implementation under the hood.
    """
    return _manual_rows_new(section_key, fdc_api_key=_FDC_API_KEY or "")
