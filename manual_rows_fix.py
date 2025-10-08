# manual_rows_fix.py
# Drop-in component to make USDA "Lookup" deterministic & Streamlit-Cloud safe.
# - Uses a button callback to mutate session_state
# - Initializes *_cal state before widget creation
# - Calls fdc_lookup_kcal from fdc_lookup.py for robust portion handling

from __future__ import annotations
import streamlit as st
import pandas as pd
from fdc_lookup import fdc_lookup_kcal  # must exist in your project root
from typing import List, Tuple

UNITS: List[str] = ["g", "oz", "cup", "tbsp", "tsp", "each"]
MAX_LINES: int = 4


def _do_lookup(cal_key: str, name_key: str, amt_key: str, unit_key: str, api_key: str):
    """Runs inside the Lookup button callback; safe place to update session_state."""
    name = st.session_state.get(name_key, "") or ""
    amt  = float(st.session_state.get(amt_key, 0.0) or 0.0)
    unit = st.session_state.get(unit_key, "") or ""
    if not api_key or not name:
        return
    try:
        kcal = fdc_lookup_kcal(name, amt, unit, api_key=api_key)
        st.session_state[cal_key] = int(round(kcal or 0))
    except Exception:
        pass


def manual_rows(section_key: str, *, fdc_api_key: str, foods_state_key: str = "foods") -> List[Tuple[str, float, str, int]]:
    """Render inputs for up to MAX_LINES rows and return list of tuples.
    Each tuple: (name, amt, unit, cal)
    """
    rows: List[Tuple[str, float, str, int]] = []

    if foods_state_key not in st.session_state:
        st.session_state[foods_state_key] = pd.DataFrame(columns=["category", "name", "cal"])

    for i in range(1, MAX_LINES + 1):
        k       = f"{section_key}{i}"
        name_k  = f"{k}_name"
        amt_k   = f"{k}_amt"
        unit_k  = f"{k}_unit"
        cal_k   = f"{k}_cal"
        lk_k    = f"{k}_lk"
        sv_k    = f"{k}_sv"

        st.session_state.setdefault(cal_k, 0)

        cA, cB, cC, cD, cE, cF = st.columns([2.6, 1.0, 1.1, 1.1, 1.1, 1.2])

        name = cA.text_input(f"item {i}", key=name_k, placeholder="e.g., Eggs")
        amt  = cB.number_input("amt", key=amt_k, value=float(st.session_state.get(amt_k, 0.0) or 0.0), step=0.25, min_value=0.0)
        unit = cC.selectbox("unit", UNITS, key=unit_k)
        cal  = cD.number_input("cal", key=cal_k, value=int(st.session_state[cal_k]), step=1, min_value=0)

        cE.button(
            "Lookup",
            key=lk_k,
            on_click=_do_lookup,
            kwargs=dict(cal_key=cal_k, name_key=name_k, amt_key=amt_k, unit_key=unit_k, api_key=fdc_api_key or "")
        )

        if cF.button("Save", key=sv_k) and name and st.session_state.get(cal_k, 0) > 0:
            pretty = f"{name} {amt:g} {unit}".strip()
            kcal   = int(st.session_state.get(cal_k, 0))
            st.session_state[foods_state_key] = pd.concat(
                [st.session_state[foods_state_key], pd.DataFrame([{
                    "category": section_key.capitalize(),
                    "name": pretty,
                    "cal": kcal
                }])],
                ignore_index=True,
            )
            st.toast(f"Saved: {pretty} — {kcal} cal")

        rows.append((name, float(amt or 0.0), unit, int(st.session_state.get(cal_k, 0))))
    return rows

