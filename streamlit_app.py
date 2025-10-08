# streamlit_app.py
from __future__ import annotations
import os, io, datetime as dt, requests
import pandas as pd
import streamlit as st
from pptx import Presentation
from pptx.util import Inches

from meal_card_generator import Theme, MealItem, MealSection, MealCardData, render_meal_card

st.set_page_config(page_title="Calorie Cards — Generator", layout="wide")

# ----------- Secrets / USDA key (never displayed) -----------
FDC_API_KEY = st.secrets.get("FDC_API_KEY", None) or os.getenv("FDC_API_KEY", None)
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
    if not FDC_API_KEY or not name:
        return 0
    try:
        s = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"api_key": FDC_API_KEY, "query": name, "pageSize": 1}
        ).json()
        fdc_id = s["foods"][0]["fdcId"]
        d = requests.get(
            f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}",
            params={"api_key": FDC_API_KEY}
        ).json()

        kcal_per_100g = None
        # prefer labelNutrients.energy, fallback to foodNutrients
        ln = d.get("labelNutrients", {})
        if "calories" in ln and "value" in ln["calories"]:
            kcal_per_100g = float(ln["calories"]["value"])
        else:
            for n in d.get("foodNutrients", []):
                nm = str(n.get("nutrient", {}).get("name","")).lower()
                if "energy" in nm and str(n.get("unitName","kcal")).lower() == "kcal":
                    kcal_per_100g = float(n.get("value"))
                    break
        if kcal_per_100g is None:
            return 0

        unit = unit.lower()
        grams = amt
        if unit in ("g","gram","grams"):
            grams = amt
        elif unit in ("oz","ounce","ounces"):
            grams = amt * 28.3495
        elif unit in ("tbsp","tablespoon"):
            grams = amt * 14.2
        elif unit in ("tsp","teaspoon"):
            grams = amt * 4.2
        elif unit in ("cup","cups"):
            grams = amt * 236.59   # generic fallback
        elif unit in ("each","item"):
            grams = amt * 100.0    # rough fallback

        return int(round((grams/100.0) * kcal_per_100g))
    except Exception:
        return 0

# ---------- Section inputs ----------
UNITS = ["g","oz","cup","tbsp","tsp","each"]
MAX_LINES = 4

# ---------- Manual Rows ----------
def manual_rows(section_key: str):
    """Return list of (name, amt, unit, cal) for up to MAX_LINES rows in a section."""
    rows = []
    for i in range(1, MAX_LINES+1):
        k = f"{section_key}{i}"
        cA, cB, cC, cD, cE = st.columns([2.3, 0.9, 1.0, 1.0, 0.8])
        name = cA.text_input(f"item {i}", key=f"{k}_name")
        amt  = cB.number_input("amt",  key=f"{k}_amt", value=0.0, step=0.25)
        unit = cC.selectbox("unit", UNITS, key=f"{k}_unit")
        cal  = cD.number_input("cal",  key=f"{k}_cal", value=0, step=1)
        lk   = cE.button("Lookup", key=f"{k}_lk")

        # do lookup -> write to session_state cal, then rerun so the box updates
        if lk and name and FDC_API_KEY:
            st.session_state[f"{k}_cal"] = usda_lookup(name, amt, unit)
            st.rerun()

        sv = st.button("Save", key=f"{k}_sv")
        if sv and name and st.session_state.get(f"{k}_cal", cal) > 0:
            pretty = f"{name} {amt:g} {unit}"
            kcal   = int(st.session_state.get(f"{k}_cal", cal))
            st.session_state["foods"] = pd.concat(
                [st.session_state["foods"], pd.DataFrame([{
                    "category": section_key[0].upper()+section_key[1:],  # "Protein"/"Carb"/"Fat"
                    "name": pretty, "cal": kcal
                }])], ignore_index=True
            )
            st.toast(f"Saved: {pretty} — {kcal} cal")

        rows.append((name, amt, unit, int(st.session_state.get(f"{k}_cal", cal))))
    return rows

def from_db(category: str):
    return st.multiselect(f"Add {category.upper()} from DB",
        options=foods_df.query("category == @category")["name"].tolist())

st.divider()
st.markdown("### PROTEIN")
prot_sel = from_db("Protein")
prot_rows = manual_rows("protein")

st.markdown("### CARB")
carb_sel = from_db("Carb")
carb_rows = manual_rows("carb")

st.markdown("### FAT")
fat_sel = from_db("Fat")
fat_rows = manual_rows("fat")

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

