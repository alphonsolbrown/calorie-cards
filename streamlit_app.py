# streamlit_app.py
import os, json, sqlite3, datetime as dt
import pandas as pd
import streamlit as st
from PIL import Image
from meal_card_generator import MealCardData, MealSection, MealItem, render_meal_card, Theme
from fdc_lookup import fdc_lookup_kcal

DB_PATH = "calorie_app.db"
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_conn(): return sqlite3.connect(DB_PATH)
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

st.set_page_config(page_title="Calorie Cards — Builder + Tracker", layout="wide")
st.title("🍽️ Calorie Cards — Tracker + Card Generator")

# ---------- helpers ----------

def ensure_row_state(prefix: str):
    st.session_state.setdefault(f"{prefix}_txt", "")
    st.session_state.setdefault(f"{prefix}_amt", 0.0)
    st.session_state.setdefault(f"{prefix}_unit", "g")
    st.session_state.setdefault(f"{prefix}_cal", 0)

def do_lookup(prefix: str, api_key: str):
    try:
        txt  = st.session_state.get(f"{prefix}_txt", "") or ""
        amt  = float(st.session_state.get(f"{prefix}_amt", 0.0) or 0.0)
        unit = st.session_state.get(f"{prefix}_unit", "g") or "g"
        if api_key and txt.strip():
            est = fdc_lookup_kcal(txt, amt, unit, api_key)
            if est is not None:
                st.session_state[f"{prefix}_cal"] = int(est)
    except Exception:
        pass
    finally:
        st.rerun()

def save_food_to_db(category: str, prefix: str, foods_csv_path="foods.csv"):
    txt  = (st.session_state.get(f"{prefix}_txt") or "").strip()
    amt  = st.session_state.get(f"{prefix}_amt") or 0.0
    unit = (st.session_state.get(f"{prefix}_unit") or "g").strip()
    cal  = int(st.session_state.get(f"{prefix}_cal") or 0)
    if not txt or cal <= 0:
        st.warning("Add a name and calories first.")
        return
    nice_amt = f"{float(amt):g}"
    name = f"{txt} {nice_amt} {unit}"

    if os.path.exists(foods_csv_path):
        df = pd.read_csv(foods_csv_path)
    else:
        df = pd.DataFrame(columns=["category", "name", "cal"])

    if (df["name"] == name).any():
        df.loc[df["name"] == name, "cal"] = cal
    else:
        df = pd.concat([df, pd.DataFrame([{"category": category.title(), "name": name, "cal": cal}])]],
                       ignore_index=True)
    df.to_csv(foods_csv_path, index=False)
    st.toast(f"Saved: {name} = {cal} cal")
    try:
        load_foods.clear()
    except Exception:
        pass
    st.rerun()

# ---------- Sidebar: brand & size -----------

with st.sidebar:
    st.header("🎨 Brand / Theme")
    c1, c2, c3 = st.columns(3)
    panel_hex  = c1.color_picker("Panel", "#FFFFFF", label_visibility="collapsed"); c1.caption("Panel")
    accent_hex = c2.color_picker("Accent", "#6C328C", label_visibility="collapsed"); c2.caption("Accent")
    light_hex  = c3.color_picker("Accent Light", "#965AB4", label_visibility="collapsed"); c3.caption("Accent Light")

    def hex_to_rgb(h): return tuple(int(h.lstrip("#")[i:i+2], 16) for i in (0,2,4))
    theme = Theme(
        panel_color=hex_to_rgb(panel_hex),
        accent=hex_to_rgb(accent_hex),
        accent_light=hex_to_rgb(light_hex),
    )

    logo_file = st.file_uploader("Brand logo (PNG w/ transparency best)", type=["png"])
    logo_path = None
    if logo_file:
        logo_path = os.path.join(OUTPUT_DIR, "brand_logo.png")
        Image.open(logo_file).save(logo_path)

    st.header("🅰️ Typography & Size")
    font_scale = st.slider("Base font size scale", 1.8, 3.2, 2.4, 0.05)
    size_label = st.selectbox("Card size", ["2560 x 1600 (2.5K)", "1920 x 1200 (HD+)", "1600 x 1000"], index=1)
    card_size = (2560,1600) if size_label.startswith("2560") else (1920,1200) if size_label.startswith("1920") else (1600,1000)
    panel_ratio = st.slider("Right panel width (two-panel only)", 0.40, 0.55, 0.48, 0.01)

    st.header("🔌 USDA Internet Lookup")
    def _read_secret(key: str):
        try:
            return st.secrets.get(key, None)
        except Exception:
            return None
    FDC_API_KEY = _read_secret("FDC_API_KEY") or os.getenv("FDC_API_KEY") \
                  or st.text_input("FDC API Key (optional)", type="password")

# ---------- Foods DB ----------

st.subheader("📚 Food Database (click to add)")
@st.cache_data
def load_foods():
    path = "foods.csv"
    if not os.path.exists(path):
        pd.DataFrame([
            {"category": "Protein", "name": "Baked Cod 4 oz",           "cal": 138},
            {"category": "Protein", "name": "Grilled Chicken 4 oz",     "cal": 170},
            {"category": "Protein", "name": "Salmon 4 oz",              "cal": 233},
            {"category": "Carb",    "name": "Mixed Veggies 1 cup",      "cal": 70},
            {"category": "Carb",    "name": "Cucumber chopped 1 cup",   "cal": 16},
            {"category": "Carb",    "name": "Tomatoes chopped 1/2 cup", "cal": 8},
            {"category": "Carb",    "name": "Nectarine 1",              "cal": 60},
            {"category": "Fat",     "name": "Olive Oil 1 tsp",          "cal": 40},
            {"category": "Fat",     "name": "Butter 1 tsp",             "cal": 33},
        ]).to_csv(path, index=False)
    return pd.read_csv(path)

foods_df = load_foods()
lcol, rcol = st.columns([1,1])
with lcol:
    st.dataframe(foods_df, width="stretch")
with rcol:
    st.caption("Search/filter, then add picks in the card builder below.")

# ---------- Card Builder ----------

st.subheader("🖼️ Build a Single Meal Card")
form_col, preview_col = st.columns([1,1])

with form_col:
    program_title = st.text_input("Program Title", value="40 Day Turn Up")
    class_name    = st.text_input("Class / Group (optional)", value="I RISE")
    meal_title    = st.text_input("Meal Title", value="Meal 1")
    date_str      = st.text_input("Date (e.g., 10/06/25)", value=dt.date.today().strftime("%-m/%-d/%y"))
    footer_text   = st.text_input("Footer (Brand/Name)", value="Alphonso Brown")

    sections_data = []
    total_calories_calc = 0

    for sec_name in ["PROTEIN", "CARB", "FAT"]:
        st.markdown(f"**{sec_name}**")
        items = []

        options = foods_df[foods_df["category"].str.lower()==sec_name.lower()]["name"].tolist()
        picks = st.multiselect(f"Add {sec_name} from DB", options, key=f"picks_{sec_name}")
        for p in picks:
            cal = int(foods_df.loc[foods_df["name"]==p, "cal"].iloc[0])
            items.append({"text": p, "cal": cal})
            total_calories_calc += cal

        # cleaner single-row layout
        for i in range(1, 5):
            prefix = f"{sec_name}_{i}"
            ensure_row_state(prefix)

            # name | amt | unit | cal | lookup | save
            c1, c2, c3, c4, c5, c6 = st.columns([4.5, 1.0, 1.2, 1.0, 1.2, 1.2])

            with c1:
                st.text_input(f"{sec_name} item {i} (manual)", key=f"{prefix}_txt", placeholder="e.g., Grilled Lamb")

            with c2:
                st.number_input("amt", key=f"{prefix}_amt", min_value=0.0, step=1.0, label_visibility="visible")

            with c3:
                st.selectbox("unit", ["g","oz","tsp","tbsp","cup"], key=f"{prefix}_unit", label_visibility="visible")

            with c4:
                st.number_input("cal", key=f"{prefix}_cal", min_value=0, step=1, label_visibility="visible")

            with c5:
                st.button("Lookup", key=f"lookup_{prefix}", on_click=do_lookup,
                          args=(prefix, FDC_API_KEY), use_container_width=True)

            with c6:
                st.button("Save", key=f"save_{prefix}", on_click=save_food_to_db,
                          args=(sec_name, prefix), use_container_width=True)

            txt  = st.session_state.get(f"{prefix}_txt", "")
            calv = st.session_state.get(f"{prefix}_cal", 0)
            if txt or calv:
                items.append({
                    "text": txt if txt else f"{st.session_state.get(f'{prefix}_amt',0)} {st.session_state.get(f'{prefix}_unit','g')}",
                    "cal": int(calv) if calv else None
                })
                if calv:
                    total_calories_calc += int(calv)

        sections_data.append({"name": sec_name, "items": items})

    uploaded_photo = st.file_uploader("Upload meal photo", type=["jpg","jpeg","png"])
    total_override = st.number_input("Total Calories (auto; editable)",
                                     value=int(total_calories_calc or 0), step=1)

    if st.button("Generate Card", type="primary"):
        if not uploaded_photo:
            st.warning("Please upload a photo.")
        else:
            img = Image.open(uploaded_photo).convert("RGB")
            photo_path = os.path.join(OUTPUT_DIR, f"photo_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            img.save(photo_path, "JPEG", quality=95)

            card = MealCardData(
                program_title=program_title,
                class_name=class_name,
                meal_title=meal_title,
                date_str=date_str,
                total_calories=int(total_override or total_calories_calc or 0),
                sections=[MealSection(name=s["name"],
                                      items=[MealItem(text=i["text"], cal=i.get("cal"))
                                             for i in s["items"]]) for s in sections_data],
                footer_text=footer_text,
                logo_path=logo_path
            )
            out_path = os.path.join(OUTPUT_DIR, f"card_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

            render_meal_card(card, photo_path, out_path,
                             theme=theme, font_scale=font_scale, size=card_size,
                             panel_ratio=panel_ratio)

            data_json = json.dumps({
                "program_title": program_title, "class_name": class_name,
                "meal_title": meal_title, "date_str": date_str,
                "total_calories": int(total_override or total_calories_calc or 0),
                "footer_text": footer_text, "sections": sections_data
            })
            with get_conn() as con:
                con.execute("INSERT INTO entries(date, meal_title, total_calories, data_json, image_path) VALUES (?, ?, ?, ?, ?)",
                            (date_str, meal_title, int(total_override or total_calories_calc or 0), data_json, out_path))

            st.success(f"Saved card: {out_path}")
            with open(out_path, "rb") as f:
                st.download_button("⬇️ Download Card PNG", f,
                    file_name=os.path.basename(out_path), mime="image/png")

            st.image(out_path, width="stretch", caption=meal_title)

with preview_col:
    st.subheader("Latest Card")
    df_all = pd.read_sql_query("SELECT * FROM entries ORDER BY date DESC, id DESC", get_conn())
    if len(df_all) and df_all.iloc[0]["image_path"] and os.path.exists(df_all.iloc[0]["image_path"]):
        st.image(df_all.iloc[0]["image_path"], width="stretch", caption=df_all.iloc[0]["meal_title"])
    else:
        st.info("Generate your first card to see it here.")

# ---------- Daily Log ----------

st.subheader("📅 Daily Log & Totals")
date_filter = st.text_input("Filter by date (e.g., 10/06/25). Leave blank for all.", value="")
if date_filter.strip():
    df_log = pd.read_sql_query("SELECT * FROM entries WHERE date = ? ORDER BY id DESC",
                               get_conn(), params=(date_filter,))
else:
    df_log = pd.read_sql_query("SELECT * FROM entries ORDER BY date DESC, id DESC", get_conn())
st.dataframe(df_log[["date","meal_title","total_calories"]], width="stretch")
if date_filter.strip():
    total_day = int(df_log["total_calories"].sum()) if len(df_log) else 0
    st.metric(f"Total calories on {date_filter}", total_day)

