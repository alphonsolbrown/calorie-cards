# streamlit_app.py
from __future__ import annotations
import os
import io
import json
import datetime as dt
import requests
import pandas as pd
import streamlit as st

from meal_card_generator import (
    Theme, MealItem, MealSection, MealCardData, render_meal_card
)

st.set_page_config(page_title="Calorie Cards — Generator", layout="wide")

# ----------------- Secrets / FDC KEY -----------------
# We DO NOT show the key anywhere in the UI.
FDC_API_KEY = st.secrets.get("FDC_API_KEY", None) or os.getenv("FDC_API_KEY", None)

# Only provide a collapsed dev expander if key missing
if not FDC_API_KEY:
    with st.expander("USDA Internet Lookup (developer – set key here for LOCAL ONLY)", expanded=False):
        FDC_API_KEY = st.text_input("FDC API Key (hidden)", type="password", value="", placeholder="Paste key…")

# ----------------- Sidebar: theme + size -----------------
with st.sidebar:
    st.header("Brand / Theme")
    panel = st.color_picker("Panel", "#F4F4F4")
    accent = st.color_picker("Accent", "#672B91")
    textc = st.color_picker("Text", "#141414")
    faint = st.color_picker("Muted", "#787878")
    theme = Theme(
        panel_color=tuple(int(panel[i:i+2], 16) for i in (1,3,5)),
        accent=tuple(int(accent[i:i+2], 16) for i in (1,3,5)),
        text=tuple(int(textc[i:i+2], 16) for i in (1,3,5)),
        faint=tuple(int(faint[i:i+2], 16) for i in (1,3,5)),
    )

    st.header("Typography & Size")
    base_scale = st.slider("Base font size scale", 0.8, 2.2, 1.20, 0.01)
    card_size = st.selectbox(
        "Card size",
        options=[(1920,1200), (2560,1600), (2880,1800), (3840,2400)],
        index=0,
        format_func=lambda s: f"{s[0]} x {s[1]}"
    )
    right_ratio = st.slider("Right panel width (two-panel only)", 0.42, 0.72, 0.52, 0.01)

# ----------------- DATA: simple csv or in-memory -----------------
# Persist foods in session (you can wire to sqlite as you had earlier)
if "foods" not in st.session_state:
    st.session_state["foods"] = pd.DataFrame(
        [
            # seed examples
            {"category":"Protein","name":"Grilled Chicken 4 oz","cal":170},
            {"category":"Carb","name":"Mixed Veggies 1 cup","cal":70},
            {"category":"Fat","name":"Olive Oil 1 tsp","cal":40},
        ]
    )

foods_df = st.session_state["foods"]

# ------------- Layout: three sections -------------
left, right = st.columns([1,1], gap="large")

with left:
    st.subheader("📚 Food Database")
    st.dataframe(foods_df, use_container_width=True, height=320)
    # add new quick row
    with st.form("new_food"):
        c1,c2,c3 = st.columns([1,2,1])
        cat = c1.selectbox("Category", ["Protein","Carb","Fat"])
        nm = c2.text_input("Name")
        cal = c3.number_input("Calories", min_value=0, step=1, value=0)
        ok = st.form_submit_button("Add")
        if ok and nm:
            st.session_state["foods"] = pd.concat([st.session_state["foods"],
                                                   pd.DataFrame([{"category":cat,"name":nm,"cal":int(cal)}])], ignore_index=True)
            st.rerun()

with right:
    st.subheader("🧾 Last Generated Card")
    ph_last = st.empty()
    ph_last.image("meal_card.png") if os.path.exists("meal_card.png") else st.info("No card generated yet")

# ----------------- Full-width: Build Single Card -----------------
st.markdown("## 🍽️ Build a Single Meal Card (full width)")
with st.container():
    c1, c2 = st.columns([1,1])
    with c1:
        program = st.text_input("Program Title", "40 Day Turn Up")
        grp = st.text_input("Class / Group (optional)", "I RISE")
        meal_title = st.text_input("Meal Title", "Meal 1")
        date_str = st.date_input("Date", value=dt.date.today()).strftime("%-m/%-d/%y")
        brand = st.text_input("Brand (tiny footer)", "Alphonso Brown")

    with c2:
        photo = st.file_uploader("Upload meal photo", type=["png","jpg","jpeg"])
        photo_path = None
        if photo:
            # save to tmp
            photo_path = "preview_photo.png"
            with open(photo_path, "wb") as f:
                f.write(photo.read())
            st.image(photo_path, caption="Photo", use_container_width=True)

# Inputs for PROTEIN / CARB / FAT (single line each; Lookup + Save aligned)
def _manual_row(label_prefix: str, key_prefix: str):
    r1, r2, r3, r4 = st.columns([2.4, 0.8, 1.0, 1.0])
    name = r1.text_input(f"{label_prefix} item (manual)", key=f"{key_prefix}_name")
    amt = r2.number_input("amt", key=f"{key_prefix}_amt", value=0.0, step=0.25)
    unit = r3.selectbox("unit", ["g","oz","cup","tbsp","tsp","each"], key=f"{key_prefix}_unit")
    cal = r4.number_input("cal", value=0, step=1, key=f"{key_prefix}_cal")
    cA, cB = st.columns([1,1])
    do_lookup = cA.button("Lookup", key=f"{key_prefix}_lk")
    do_save = cB.button("Save", key=f"{key_prefix}_sv")
    return name, amt, unit, cal, do_lookup, do_save

st.divider()
st.markdown("### PROTEIN")
prot_sel = st.multiselect("Add PROTEIN from DB", options=foods_df.query("category=='Protein'")["name"].tolist())
p_name, p_amt, p_unit, p_cal, p_lookup, p_save = _manual_row("PROTEIN", "P1")

st.markdown("### CARB")
carb_sel = st.multiselect("Add CARB from DB", options=foods_df.query("category=='Carb'")["name"].tolist())
c_name, c_amt, c_unit, c_cal, c_lookup, c_save = _manual_row("CARB", "C1")

st.markdown("### FAT")
fat_sel = st.multiselect("Add FAT from DB", options=foods_df.query("category=='Fat'")["name"].tolist())
f_name, f_amt, f_unit, f_cal, f_lookup, f_save = _manual_row("FAT", "F1")

# ----------------- USDA lookup (silent; key never shown) -----------------
def usda_lookup(name: str, amt: float, unit: str) -> int:
    """Basic FoodData Central lookup; returns integer calories."""
    if not FDC_API_KEY or not name:
        return 0
    try:
        # 1) search
        s = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"api_key": FDC_API_KEY, "query": name, "pageSize": 1}
        ).json()
        fdc_id = s["foods"][0]["fdcId"]

        # 2) details
        d = requests.get(
            f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}",
            params={"api_key": FDC_API_KEY}
        ).json()

        # naive extraction: try energy KCal per 100g; convert
        kcal_per_100g = None
        for n in d.get("labelNutrients", {}):
            pass
        # safer path
        for n in d.get("foodNutrients", []):
            if str(n.get("nutrient", {}).get("name","")).lower() in ("energy","energy (atwater general factors)"):
                if n.get("unitName","kcal").lower() == "kcal":
                    kcal_per_100g = n.get("value")
                    break

        if kcal_per_100g is None:
            return 0

        # unit translate (very rough)
        grams = amt
        unit = unit.lower()
        if unit in ("g","gram","grams"):
            grams = amt
        elif unit in ("oz","ounce","ounces"):
            grams = amt * 28.3495
        elif unit in ("tbsp","tablespoon"):
            grams = amt * 14.2
        elif unit in ("tsp","teaspoon"):
            grams = amt * 4.2
        elif unit in ("cup","cups"):
            grams = amt * 236.59  # extreme simplification; better map by food
        elif unit in ("each","item"):
            grams = amt * 100.0    # fallback assumption

        cal = (grams / 100.0) * float(kcal_per_100g)
        return int(round(cal))
    except Exception:
        return 0

# wire buttons
def _save_if_needed(category, name, amt, unit, cal, save_pressed):
    if save_pressed and name and cal > 0:
        pretty = f"{name} {amt:g} {unit}"
        st.session_state["foods"] = pd.concat([st.session_state["foods"],
            pd.DataFrame([{"category":category, "name":pretty, "cal":int(cal)}])], ignore_index=True)
        st.toast(f"Saved to DB: {category} • {pretty} • {int(cal)} cal")

if p_lookup and p_name:
    st.session_state["P1_cal"] = usda_lookup(p_name, p_amt, p_unit)
if c_lookup and c_name:
    st.session_state["C1_cal"] = usda_lookup(c_name, c_amt, c_unit)
if f_lookup and f_name:
    st.session_state["F1_cal"] = usda_lookup(f_name, f_amt, f_unit)

_save_if_needed("Protein", p_name, p_amt, p_unit, st.session_state.get("P1_cal", p_cal), p_save)
_save_if_needed("Carb", c_name, c_amt, c_unit, st.session_state.get("C1_cal", c_cal), c_save)
_save_if_needed("Fat", f_name, f_amt, f_unit, st.session_state.get("F1_cal", f_cal), f_save)

# Collect items
def _collect_items(category, selections, manual_name, manual_amt, manual_unit, manual_cal_key, foods_df):
    items = []
    for nm in selections:
        row = foods_df.query("name == @nm").iloc[0]
        items.append(MealItem(text=row["name"], cal=int(row["cal"])))
    # manual
    kcal = st.session_state.get(manual_cal_key, 0)
    if manual_name and (kcal > 0):
        items.append(MealItem(text=f"{manual_name} {manual_amt:g} {manual_unit}", cal=int(kcal)))
    return items

prot_items = _collect_items("Protein", prot_sel, p_name, p_amt, p_unit, "P1_cal", foods_df)
carb_items = _collect_items("Carb", carb_sel, c_name, c_amt, c_unit, "C1_cal", foods_df)
fat_items  = _collect_items("Fat",  fat_sel,  f_name, f_amt, f_unit, "F1_cal", foods_df)

# ---- Card build & render ----
st.divider()
total_cals = int(sum(i.cal for i in prot_items + carb_items + fat_items))
st.metric("Total Calories (auto; editable)", total_cals)

if st.button("Generate Card", type="primary", use_container_width=True):
    # Dynamic layout: 4-panel for many lines (done in renderer)
    card = MealCardData(
        program_title=program.strip() or "Program",
        class_name=(grp.strip() or None),
        meal_title=meal_title.strip() or "Meal 1",
        date_str=date_str,
        brand=brand.strip() or None,
        protein=MealSection("Protein", prot_items),
        carb=MealSection("Carb", carb_items),
        fat=MealSection("Fat", fat_items),
    )

    out = "meal_card.png"
    render_meal_card(
        card=card,
        photo_path=("preview_photo.png" if photo else None),
        output_path=out,
        size=card_size,
        theme=theme,
        font_scale=base_scale,
        panel_ratio=right_ratio,
    )
    st.success("Card generated.")
    st.image(out, use_container_width=True)

