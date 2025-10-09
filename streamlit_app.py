import streamlit as st
import pandas as pd
import sqlite3, os, json, datetime as dt, io
from PIL import Image
from meal_card_generator import MealCardData, MealSection, MealItem, render_meal_card, Theme

DB_PATH = "calorie_app.db"
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            meal_title TEXT NOT NULL,
            total_calories INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            image_path TEXT
        )
        """)
init_db()

st.set_page_config(page_title="Calorie Cards", layout="wide")
st.title("🍽️ Calorie Cards — Tracker + Card Generator")

with st.sidebar:
    st.header("🎨 Brand / Theme")
    c1, c2, c3 = st.columns(3)
    panel = c1.color_picker("Panel", "#FFFFFF")
    accent = c2.color_picker("Accent", "#6C328C")
    accent2 = c3.color_picker("Accent Light", "#965AB4")
    logo_file = st.file_uploader("Upload logo (PNG)", type=["png"], key="logo")
    font_scale = st.slider("🅰️ Font size scale", 0.8, 2.0, 1.3, 0.05)
    logo_path = None
    if logo_file:
        logo_path = os.path.join(OUTPUT_DIR, "brand_logo.png")
        Image.open(logo_file).save(logo_path)

    theme = Theme(
        panel_color=tuple(int(panel.lstrip("#")[i:i+2], 16) for i in (0,2,4)),
        accent=tuple(int(accent.lstrip("#")[i:i+2], 16) for i in (0,2,4)),
        accent_light=tuple(int(accent2.lstrip("#")[i:i+2], 16) for i in (0,2,4)),
    )

    st.header("🎯 Daily Target")
    daily_target = st.number_input("Calories/day", value=2000, step=50)

st.subheader("📚 Food Database (click to add)")
@st.cache_data
def load_foods():
    path = "foods.csv"
    if not os.path.exists(path):
        pd.DataFrame([
            {"category":"Protein","name":"Baked Cod 4 oz","cal":138},
            {"category":"Protein","name":"Grilled Chicken 4 oz","cal":170},
            {"category":"Protein","name":"Salmon 4 oz","cal":233},
            {"category":"Carb","name":"Mixed Veggies 1 cup","cal":70},
            {"category":"Carb","name":"Cucumber chopped 1 cup","cal":16},
            {"category":"Carb","name":"Tomatoes chopped 1/2 cup","cal":8},
            {"category":"Carb","name":"Nectarine 1","cal":60},
            {"category":"Fat","name":"Olive Oil 1 tsp","cal":40},
            {"category":"Fat","name":"Butter 1 tsp","cal":33},
        ]).to_csv(path, index=False)
    return pd.read_csv(path)

foods_df = load_foods()
left, right = st.columns([1,1])
with left:
    st.dataframe(foods_df)
with right:
    st.caption("Tip: use the DB to add items to your card quickly.")

st.subheader("🖼️ Build a Single Meal Card")
col_form, col_preview = st.columns([1,1])

with col_form:
    journey_title = st.text_input("Journey Title", value="JOURNEY 3.0")
    meal_title = st.text_input("Meal Title", value="Meal 1")
    date_str = st.text_input("Date", value=dt.date.today().strftime("%-m/%-d/%y"))
    footer_text = st.text_input("Footer (Brand/Name)", value="")
    sections_data = []
    total_calories_calc = 0

    for sec_name in ["PROTEIN","CARB","FAT"]:
        st.markdown(f"**{sec_name}**")
        items = []
        pick = st.multiselect(f"Add {sec_name} from DB",
            foods_df[foods_df["category"].str.lower()==sec_name.lower()]["name"].tolist(),
            key=f"pick_{sec_name}")
        for p in pick:
            cal = int(foods_df.loc[foods_df["name"]==p,"cal"].iloc[0])
            items.append({"text": p, "cal": cal}); total_calories_calc += cal
        for i in range(1,5):
            c1,c2 = st.columns([3,1])
            with c1:
                text = st.text_input(f"{sec_name} item {i} (manual)", value="", key=f"{sec_name}_text_{i}")
            with c2:
                cal = st.number_input("cal", value=0, min_value=0, step=1, key=f"{sec_name}_cal_{i}")
            if text or cal:
                items.append({"text": text, "cal": int(cal) if cal else None})
                if cal: total_calories_calc += int(cal)
        sections_data.append({"name": sec_name, "items": items})

    uploaded_img = st.file_uploader("Upload meal photo", type=["jpg","jpeg","png"], key="single_photo")
    total_override = st.number_input("Total Calories (auto; editable)", value=total_calories_calc or 0, step=1)

    if st.button("Generate Card", type="primary"):
        if not uploaded_img:
            st.warning("Please upload a photo.")
        else:
            img = Image.open(uploaded_img).convert("RGB")
            img_path = os.path.join(OUTPUT_DIR, f"photo_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            img.save(img_path, "JPEG", quality=92)
            card = MealCardData(
                journey_title=journey_title,
                meal_title=meal_title,
                date_str=date_str,
                total_calories=int(total_override or total_calories_calc or 0),
                sections=[MealSection(name=s["name"], items=[MealItem(text=i["text"], cal=i.get("cal")) for i in s["items"]]) for s in sections_data],
                footer_text=footer_text,
                logo_path=logo_path
            )
            out_path = os.path.join(OUTPUT_DIR, f"card_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            render_meal_card(card, img_path, out_path, theme=theme, font_scale=font_scale)

            data_json = json.dumps({
                "journey_title": journey_title,
                "meal_title": meal_title,
                "date_str": date_str,
                "total_calories": int(total_override or total_calories_calc or 0),
                "footer_text": footer_text,
                "sections": sections_data
            })
            with get_conn() as con:
                con.execute("INSERT INTO entries(date, meal_title, total_calories, data_json, image_path) VALUES (?, ?, ?, ?, ?)",
                            (date_str, meal_title, int(total_override or total_calories_calc or 0), data_json, out_path))

            st.success(f"Saved card: {out_path}")
            with open(out_path, "rb") as f:
                st.download_button("⬇️ Download Card PNG", f, file_name=os.path.basename(out_path), mime="image/png")

with col_preview:
    st.subheader("Latest Card")
    df_all = pd.read_sql_query("SELECT * FROM entries ORDER BY date DESC, id DESC", get_conn())
    if len(df_all) > 0 and os.path.exists(df_all.iloc[0]["image_path"]):
        st.image(df_all.iloc[0]["image_path"], use_column_width=True, caption=df_all.iloc[0]["meal_title"])
    else:
        st.info("Generate your first card to see it here.")

st.subheader("🗂️ Batch Card Generation")
st.caption("Upload a CSV with columns: date, meal_title, photo_path, section, item_text, item_cal.")
sample = """date,meal_title,photo_path,section,item_text,item_cal
7/3/24,Meal 4,photos/cod.jpg,PROTEIN,4 oz Baked Cod,138
7/3/24,Meal 4,photos/cod.jpg,CARB,1 Cup Raw Mixed Veggies,70
7/3/24,Meal 4,photos/cod.jpg,CARB,1 Cup Chopped Cucumber,16
7/3/24,Meal 4,photos/cod.jpg,CARB,1/2 Cup Chopped Tomatoes,8
7/3/24,Meal 4,photos/cod.jpg,FAT,1 teaspoon Olive Oil,40
"""
st.download_button("Download CSV template", sample, file_name="batch_template.csv", mime="text/csv")

batch_file = st.file_uploader("Upload batch CSV", type=["csv"], key="batchcsv")
if batch_file is not None:
    dfb = pd.read_csv(batch_file)
    st.dataframe(dfb.head())
    if st.button("Generate All Cards"):
        for (date_str, meal_title), sdf in dfb.groupby(["date","meal_title"]):
            photo_path = sdf["photo_path"].iloc[0]
            sections = []
            total = 0
            for sec_name, sub in sdf.groupby("section"):
                items = []
                for _, row in sub.iterrows():
                    cal = int(row["item_cal"]) if not pd.isna(row["item_cal"]) else None
                    if cal: total += cal
                    items.append(MealItem(text=row["item_text"], cal=cal))
                sections.append(MealSection(name=sec_name, items=items))
            card = MealCardData(journey_title="JOURNEY 3.0", meal_title=meal_title, date_str=date_str, total_calories=total, sections=sections, logo_path=logo_path)
            out_path = os.path.join(OUTPUT_DIR, f"card_{meal_title}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            render_meal_card(card, photo_path, out_path, theme=theme, font_scale=font_scale)
        st.success("Batch generated. Check the outputs/ folder below.")

st.subheader("📽️ Export Cards to PowerPoint (.pptx)")
try:
    from pptx import Presentation
    from pptx.util import Inches
    ppt_ok = True
except Exception:
    ppt_ok = False
    st.warning("python-pptx not installed. Add it to requirements.txt to enable PPTX export.")

if ppt_ok:
    existing = [os.path.join(OUTPUT_DIR, f) for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".png")]
    if len(existing) == 0:
        st.info("Generate some cards first. They will appear here for export.")
    else:
        st.write(f"Found {len(existing)} card(s) in outputs/.")
        if st.button("Create PowerPoint from all cards"):
            prs = Presentation()
            blank = prs.slide_layouts[6]
            for img_path in existing:
                slide = prs.slides.add_slide(blank)
                slide.shapes.add_picture(img_path, Inches(0.5), Inches(0.5), width=Inches(9))
            ppt_path = os.path.join(OUTPUT_DIR, f"cards_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx")
            prs.save(ppt_path)
            with open(ppt_path, "rb") as f:
                st.download_button("⬇️ Download PPTX", f, file_name=os.path.basename(ppt_path), mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")

st.markdown("---")
st.caption("Calorie Cards • Built with Streamlit")
