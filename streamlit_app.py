# streamlit_app.py
# Programmer: Alphonso Brown
# Date: 10/9/2025
# Notes:
#        10.9.25 @10:42 AM - Fixed manual_rows issue

from __future__ import annotations
import os, io, datetime as dt, requests
import pandas as pd
import streamlit as st
from pptx import Presentation
from pptx.util import Inches

from meal_card_generator import Theme, MealItem, MealSection, MealCardData, render_meal_card
from fdc_lookup import fdc_lookup_kcal
# from manual_rows_fix import manual_rows

st.set_page_config(page_title="Calorie Cards — Generator", layout="wide")

# ----------- Secrets / USDA key (never displayed) -----------
FDC_API_KEY = st.secrets.get("FDC_API_KEY", os.getenv("FDC_API_KEY", ""))
if not FDC_API_KEY:
    with st.expander("USDA Internet Lookup (developer only – set key for local testing)"):
        FDC_API_KEY = st.text_input("FDC API Key", type="password")

# ---------------- Sidebar: compact theme + size ----------------
with st.sidebar:
    st.header("Brand / Theme")
    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    panel_hex  = c1.color_picker("Panel", "#F4F4F4")
    accent_hex = c2.color_picker("Accent", "#672B91")
    text_hex   = c3.color_picker("Text", "#141414")
    faint_hex  = c4.color_picker("Muted", "#787878")

    to_rgb = lambda hx: tuple(int(hx[i:i+2], 16) for i in (1,3,5))
    theme = Theme(
        panel_color=to_rgb(panel_hex),
        accent=to_rgb(accent_hex),
        text=to_rgb(text_hex),
        faint=to_rgb(faint_hex),
    )

    st.header("Typography & Size")
    base_scale = st.slider("Base font size scale", 0.8, 2.2, 1.20, 0.01)
    card_size = st.selectbox(
        "Card size",
        options=[(1920,1200), (2560,1600), (2880,1800), (3840,2400)],
        index=0, format_func=lambda s: f"{s[0]} x {s[1]}"
    )
    right_ratio = st.slider("Right panel width (two-panel only)", 0.42, 0.72, 0.52, 0.01)

# ---------------- Food DB (in-session; you can swap to sqlite) ----------------
if "foods" not in st.session_state:
    st.session_state["foods"] = pd.DataFrame(
        [
            {"category":"Protein","name":"Grilled Chicken 4 oz","cal":170},
            {"category":"Carb","name":"Mixed Veggies 1 cup","cal":70},
            {"category":"Fat","name":"Olive Oil 1 tsp","cal":40},
        ]
    )
foods_df = st.session_state["foods"]

# --------------- Top: left DB / right last card ----------------
left, right = st.columns([1,1], gap="large")

with left:
    st.subheader("📚 Food Database (add items here)")
    st.dataframe(foods_df, use_container_width=True, height=320)

    with st.form("new_food"):
        c1, c2, c3 = st.columns([1,2,1])
        cat = c1.selectbox("Category", ["Protein","Carb","Fat"])
        nm  = c2.text_input("Name")
        cal = c3.number_input("Calories", min_value=0, step=1, value=0)
        if st.form_submit_button("Add"):
            if nm:
                st.session_state["foods"] = pd.concat(
                    [st.session_state["foods"], pd.DataFrame([{"category":cat,"name":nm,"cal":int(cal)}])],
                    ignore_index=True
                )
                st.rerun()

    # DB CSV download
    csv = foods_df.to_csv(index=False).encode()
    st.download_button("Download DB CSV", data=csv, file_name="foods.csv", mime="text/csv")

with right:
    st.subheader("🧾 Last Generated Card")
    if os.path.exists("meal_card.png"):
        st.image("meal_card.png")
    else:
        st.info("No card generated yet")

# ---------------- Build a Single Meal Card (full width) ----------------
st.markdown("## 🍽️ Build a Single Meal Card (full width)")
c1, c2 = st.columns([1,1])
with c1:
    program    = st.text_input("Program Title", "40 Day Turn Up")
    grp        = st.text_input("Class / Group (optional)", "I RISE")
    meal_title = st.text_input("Meal Title", "Meal 1")
    date_str   = st.date_input("Date", value=dt.date.today()).strftime("%-m/%-d/%y")
    brand      = st.text_input("Brand (tiny footer)", "Alphonso Brown")
with c2:
    photo = st.file_uploader("Upload meal photo", type=["png","jpg","jpeg"])
    photo_path = None
    if photo:
        photo_path = "preview_photo.png"
        with open(photo_path, "wb") as f:
            f.write(photo.read())
        st.image(photo_path, caption="Photo", use_container_width=True)

# ---------- USDA lookup ----------
def usda_lookup(name: str, amt: float, unit: str) -> int:
    kcal = fdc_lookup_kcal(name, amt, unit, api_key=FDC_API_KEY or "")
    return int(round(kcal or 0))

# ---------- Section inputs ----------
UNITS = ["g","oz","cup","tbsp","tsp","each"]
MAX_LINES = 4

# put this near the top of the file (or above manual_rows):
def _do_lookup(cal_key: str, name: str, amt: float, unit: str, api_key: str):
    if name and api_key:
        # use your existing usda_lookup; returns int calories
        st.session_state[cal_key] = usda_lookup(name, amt, unit)

def manual_rows(section_key: str):
    """Return list of (name, amt, unit, cal) for up to MAX_LINES rows in a section."""
    rows = []
    for i in range(1, MAX_LINES+1):
        k = f"{section_key}{i}"
        name_key = f"{k}_name"
        amt_key  = f"{k}_amt"
        unit_key = f"{k}_unit"
        cal_key  = f"{k}_cal"
        lk_key   = f"{k}_lk"
        sv_key   = f"{k}_sv"

        # 1) ensure cal key exists *before* building the widget
        if cal_key not in st.session_state:
            st.session_state[cal_key] = 0

        cA, cB, cC, cD, cE = st.columns([2.3, 0.9, 1.0, 1.0, 0.8])

        # 2) build widgets
        name = cA.text_input(f"item {i}", key=name_key)
        amt  = cB.number_input("amt",  key=amt_key,  value=0.0, step=0.25)
        unit = cC.selectbox("unit",    UNITS,        key=unit_key)

        # bind the number_input to session state key; don't overwrite it directly later
        cal  = cD.number_input("cal",  key=cal_key,  value=st.session_state[cal_key], step=1)

        # 3) button runs a callback that sets session_state and triggers rerun automatically
        cE.button(
            "Lookup", key=lk_key,
            on_click=_do_lookup,
            kwargs=dict(cal_key=cal_key, name=name, amt=amt, unit=unit, api_key=FDC_API_KEY),
        )

        # 4) explicit Save (unchanged)
        sv = st.button("Save", key=sv_key)
        if sv and name and st.session_state.get(cal_key, cal) > 0:
            pretty = f"{name} {amt:g} {unit}"
            kcal   = int(st.session_state.get(cal_key, cal))
            st.session_state["foods"] = pd.concat(
                [st.session_state["foods"], pd.DataFrame([{
                    "category": section_key.capitalize(),
                    "name": pretty, "cal": kcal
                }])],
                ignore_index=True,
            )
            st.toast(f"Saved: {pretty} — {kcal} cal")

        rows.append((name, amt, unit, int(st.session_state.get(cal_key, 0))))
    return rows

def from_db(category: str):
    return st.multiselect(f"Add {category.upper()} from DB",
        options=foods_df.query("category == @category")["name"].tolist())

st.divider()
st.markdown("### PROTEIN")
prot_sel = from_db("Protein")
#prot_rows = manual_rows("protein", fdc_api_key=FDC_API_KEY)
prot_rows = manual_rows("protein")

st.markdown("### CARB")
carb_sel = from_db("Carb")
#carb_rows = manual_rows("carb", fdc_api_key=FDC_API_KEY)
carb_rows = manual_rows("carb")

st.markdown("### FAT")
fat_sel = from_db("Fat")
#fat_rows = manual_rows("fat", fdc_api_key=FDC_API_KEY)
fat_rows  = manual_rows("fat")

# ---------- Collect items (DB + manual) ----------
def collect_items(db_names, manual_rows):
    items = []
    for nm in db_names:
        row = foods_df.query("name == @nm").iloc[0]
        items.append(MealItem(text=row["name"], cal=int(row["cal"])))
    for (name, amt, unit, cal) in manual_rows:
        if name and cal > 0:
            items.append(MealItem(text=f"{name} {amt:g} {unit}", cal=int(cal)))
    return items

prot_items = collect_items(prot_sel, prot_rows)
carb_items = collect_items(carb_sel, carb_rows)
fat_items  = collect_items(fat_sel,  fat_rows)

# ---------- Render ----------
st.divider()
total_cals = int(sum(i.cal for i in prot_items+carb_items+fat_items))
st.metric("Total Calories (auto; updates when you Lookup/Save)", total_cals)

if st.button("Generate Card", type="primary", use_container_width=True):
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
    render_meal_card(card, photo_path=photo_path, output_path=out,
                     size=card_size, theme=theme, font_scale=base_scale, panel_ratio=right_ratio)
    st.success("Card generated.")
    st.image(out, use_container_width=True)

    # download PNG
    with open(out, "rb") as f:
        st.download_button("Download PNG", data=f.read(), file_name="meal_card.png", mime="image/png")

    # download PPTX with the card as one slide
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    pic = os.path.abspath(out)
    left = top = Inches(0.25)
    slide.shapes.add_picture(pic, left, top, width=Inches(9.5))
    bio = io.BytesIO()
    prs.save(bio); bio.seek(0)
    st.download_button("Download PPTX", data=bio, file_name="meal_card.pptx",
                       mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")

