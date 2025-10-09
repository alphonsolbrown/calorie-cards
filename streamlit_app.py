# streamlit_app.py (patched full version)
from __future__ import annotations
import os, io, datetime as dt
import pandas as pd
import streamlit as st
from pptx import Presentation
from pptx.util import Inches

from meal_card_generator import Theme, MealItem, MealSection, MealCardData, render_meal_card
from manual_rows_compat import manual_rows  # our safe component

st.set_page_config(page_title="Calorie Cards — Generator", layout="wide")

# ----------- Secrets / USDA key -----------
FDC_API_KEY = st.secrets.get("FDC_API_KEY", None) or os.getenv("FDC_API_KEY", None)
if not FDC_API_KEY:
    with st.expander("USDA Lookup API Key (developer - optional locally)"):
        st.info("Set FDC_API_KEY in Streamlit secrets or environment for Lookup to work.")

# ----------- Session bootstrapping -----------
if "foods" not in st.session_state:
    st.session_state["foods"] = pd.DataFrame(columns=["category","name","cal"])

foods_df: pd.DataFrame = st.session_state["foods"]

# ---------------- Header ----------------
st.title("🍽️ Calorie Card Builder")

# ---------------- Build a Single Meal Card ----------------
st.subheader("Build a Single Meal Card")
c1, c2 = st.columns([1,1])
with c1:
    program    = st.text_input("Program Title", "40 Day Turn Up")
    grp        = st.text_input("Class / Group (optional)", "I RISE")
    meal_title = st.text_input("Meal Title", "Meal 1")
    date_str   = st.date_input("Date", value=dt.date.today()).strftime("%-m/%-d/%y")
    brand      = st.text_input("Brand (footer)", "Alphonso Brown")
with c2:
    photo = st.file_uploader("Upload meal photo", type=["png","jpg","jpeg"])
    photo_path = None
    if photo:
        # Save uploaded photo to a temporary path Streamlit can read back
        photo_path = os.path.join(os.getcwd(), "uploaded_photo.png")
        with open(photo_path, "wb") as f:
            f.write(photo.getbuffer())

st.divider()
st.markdown("#### Add from your Food DB")
def from_db(category: str):
    opts = foods_df.query("category == @category")["name"].tolist() if not foods_df.empty else []
    return st.multiselect(f"Add {category} from DB", options=opts, key=f"db_{category}")

prot_sel = from_db("Protein")
carb_sel = from_db("Carb")
fat_sel  = from_db("Fat")

st.divider()
st.markdown("#### Enter Items Manually (Lookup populates calories)")

# Safe, consistent inputs that use callback-based Lookup
prot_rows = manual_rows("protein")
carb_rows = manual_rows("carb")
fat_rows  = manual_rows("fat")

def rows_to_items(rows):
    items = []
    for name, amt, unit, cal in rows:
        if name and (cal or 0) > 0:
            items.append(MealItem(name=name, amount=f"{amt:g} {unit}".strip(), calories=int(cal)))
    return items

# Resolve selected DB items (DB stores only total cal per entry; treat each as a single line)
def db_to_items(names, category):
    items = []
    if names:
        sub = foods_df[foods_df["name"].isin(names)]
        for _, r in sub.iterrows():
            items.append(MealItem(name=r["name"], amount="", calories=int(r["cal"])))
    return items

protein_items = db_to_items(prot_sel,"Protein") + rows_to_items(prot_rows)
carb_items    = db_to_items(carb_sel,"Carb")     + rows_to_items(carb_rows)
fat_items     = db_to_items(fat_sel,"Fat")       + rows_to_items(fat_rows)

theme = Theme()  # default card theme

if st.button("Generate Meal Card"):
    card = MealCardData(
        program=program,
        group=grp,
        meal_title=meal_title,
        date=date_str,
        brand=brand,
        protein=MealSection(items=protein_items),
        carb=MealSection(items=carb_items),
        fat=MealSection(items=fat_items),
        photo_path=photo_path
    )
    out = "meal_card.png"
    render_meal_card(card, theme, out)
    st.image(out, caption="Preview", use_column_width=True)

    with open(out, "rb") as f:
        st.download_button("Download PNG", data=f.read(), file_name="meal_card.png", mime="image/png")

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    pic = os.path.abspath(out)
    left = top = Inches(0.25)
    slide.shapes.add_picture(pic, left, top, width=Inches(9.5))
    bio = io.BytesIO(); prs.save(bio); bio.seek(0)
    st.download_button("Download PPTX", data=bio, file_name="meal_card.pptx",
                       mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")

# ---------------- Admin: view DB ----------------
st.divider()
st.subheader("Food DB (saved items)")
st.dataframe(st.session_state["foods"])

