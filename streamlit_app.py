import streamlit as st
import pandas as pd
import sqlite3, os, json, datetime as dt
from PIL import Image
from meal_card_generator import MealCardData, MealSection, MealItem, render_meal_card

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
        )""")
init_db()

st.set_page_config(page_title="Calorie Cards", layout="wide")
st.title("🍽️ Calorie Cards — Tracker + Card Generator")

with st.sidebar:
    st.header("Daily Targets")
    daily_target = st.number_input("Daily Calorie Target", value=2000, step=50)

st.subheader("1) Build a Meal Card")
col_form, col_preview = st.columns([1,1])

with col_form:
    journey_title = st.text_input("Journey Title", value="JOURNEY 3.0")
    meal_title = st.text_input("Meal Title", value="Meal 1")
    date_str = st.text_input("Date (e.g., 7/3/24)", value=dt.date.today().strftime("%-m/%-d/%y"))
    footer_text = st.text_input("Footer (Brand/Name)", value="")

    sections_data = []
    total_calories_calc = 0
    for sec_name in ["PROTEIN", "CARB", "FAT"]:
        st.markdown(f"**{sec_name}**")
        items = []
        for i in range(1, 5):
            c1, c2 = st.columns([3,1])
            with c1:
                text = st.text_input(f"{sec_name} item {i} name", value="", key=f"{sec_name}_text_{i}")
            with c2:
                cal = st.number_input(f"cal", value=0, min_value=0, step=1, key=f"{sec_name}_cal_{i}")
            if text or cal:
                items.append({"text": text, "cal": int(cal) if cal else None})
                if cal: total_calories_calc += int(cal)
        sections_data.append({"name": sec_name, "items": items})

    uploaded_img = st.file_uploader("Upload meal photo", type=["jpg","jpeg","png"])
    total_override = st.number_input("Total Calories", value=total_calories_calc or 0, step=1)

    if st.button("Generate Card"):
        if not uploaded_img:
            st.warning("Please upload a photo.")
        else:
            img = Image.open(uploaded_img).convert("RGB")
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            img_path = os.path.join(OUTPUT_DIR, f"photo_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            img.save(img_path, "JPEG", quality=92)
            card = MealCardData(
                journey_title=journey_title,
                meal_title=meal_title,
                date_str=date_str,
                total_calories=int(total_override or total_calories_calc or 0),
                sections=[
                    MealSection(name=s["name"], items=[MealItem(text=i["text"], cal=i.get("cal")) for i in s["items"]])
                    for s in sections_data
                ],
                footer_text=footer_text
            )
            out_path = os.path.join(OUTPUT_DIR, f"card_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            render_meal_card(card, img_path, out_path)

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
    st.subheader("Live Preview (after generation)")
    df_all = pd.read_sql_query("SELECT * FROM entries ORDER BY date DESC, id DESC", get_conn())
    if len(df_all) > 0 and os.path.exists(df_all.iloc[0]["image_path"]):
        st.image(df_all.iloc[0]["image_path"], use_column_width=True, caption=df_all.iloc[0]["meal_title"])
    else:
        st.info("Generate your first card to see it here.")

st.subheader("2) Daily Log & Totals")
date_filter = st.text_input("Filter by date (e.g., 7/3/24). Leave blank for all.", value="")
if date_filter.strip():
    df = pd.read_sql_query("SELECT * FROM entries WHERE date = ? ORDER BY id DESC", get_conn(), params=(date_filter,))
else:
    df = pd.read_sql_query("SELECT * FROM entries ORDER BY date DESC, id DESC", get_conn())
st.dataframe(df[["date","meal_title","total_calories"]])
if date_filter.strip():
    total_day = int(df["total_calories"].sum()) if len(df)>0 else 0
    st.metric(f"Total calories on {date_filter}", total_day)
