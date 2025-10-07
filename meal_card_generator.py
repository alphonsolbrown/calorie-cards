# meal_card_generator.py
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import os, textwrap

# ---------- Data models ----------
@dataclass
class MealItem:
    text: str
    cal: Optional[int] = None

@dataclass
class MealSection:
    name: str
    items: List[MealItem]

@dataclass
class Theme:
    panel_color: Tuple[int, int, int] = (255, 255, 255)
    accent: Tuple[int, int, int] = (108, 50, 140)
    accent_light: Tuple[int, int, int] = (150, 90, 180)
    # Windows-safe defaults; we’ll fall back to PIL default if these aren’t found
    font_regular: str = "C:/Windows/Fonts/arial.ttf"
    font_bold:    str = "C:/Windows/Fonts/arialbd.ttf"
    font_italic:  str = "C:/Windows/Fonts/ariali.ttf"

@dataclass
class MealCardData:
    program_title: str = "Program"   # renamed from journey_title
    class_name: str = ""             # new
    meal_title: str = "Meal"
    date_str: str = "MM/DD/YY"
    total_calories: int = 400
    sections: List[MealSection] = field(default_factory=list)
    footer_text: str = ""
    logo_path: Optional[str] = None  # optional PNG with alpha

# ---------- Font helper ----------
def _get_font(theme: Theme, size: int, weight: str = "regular"):
    try:
        if weight == "bold":
            return ImageFont.truetype(theme.font_bold, size)
        if weight == "italic":
            return ImageFont.truetype(theme.font_italic, size)
        return ImageFont.truetype(theme.font_regular, size)
    except Exception:
        return ImageFont.load_default()

# ---------- Renderer ----------
def render_meal_card(
    card: MealCardData,
    photo_path: str,
    output_path: str = "meal_card.png",
    size: Tuple[int, int] = (2560, 1600),   # big by default (sharp PNG)
    theme: Theme = Theme(),
    font_scale: float = 1.7,                # large, readable default
) -> str:
    W, H = size
    img = Image.new("RGB", size, (245, 245, 245))
    draw = ImageDraw.Draw(img)
    pad = 36
    left_w = int(W * 0.62)   # slightly wider photo column for aesthetic balance
    right_x = left_w

    # ---- Left photo ----
    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGB")
        ratio = max(left_w / photo.width, H / photo.height)
        new_sz = (int(photo.width * ratio), int(photo.height * ratio))
        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS
        photo = photo.resize(new_sz, resample)
        x0 = max(0, (photo.width - left_w) // 2)
        y0 = max(0, (photo.height - H) // 2)
        img.paste(photo.crop((x0, y0, x0 + left_w, y0 + H)), (0, 0))
    else:
        draw.rectangle([0, 0, left_w, H], fill=(230, 230, 230))
        draw.text((pad, pad), "PHOTO NOT FOUND",
                  font=_get_font(theme, int(36*font_scale), "bold"),
                  fill=(120, 120, 120))

    # ---- Right panel ----
    draw.rectangle([right_x, 0, W, H], fill=theme.panel_color)

    y = pad

    # Program title
    draw.text((right_x + pad, y),
              card.program_title,
              font=_get_font(theme, int(68*font_scale), "bold"),
              fill=(20, 20, 20))
    y += int(78 * font_scale)

    # Class / Group name (optional)
    if card.class_name:
        draw.text((right_x + pad, y),
                  card.class_name,
                  font=_get_font(theme, int(40*font_scale), "italic"),
                  fill=(60, 60, 60))
        y += int(46 * font_scale)

    # Meal + date
    meal_line = f"{card.meal_title} - {card.date_str}"
    draw.text((right_x + pad, y),
              meal_line,
              font=_get_font(theme, int(48*font_scale), "bold"),
              fill=(20, 20, 20))
    y += int(36 * font_scale)

    # Divider
    bar_h = int(14 * font_scale)
    draw.rectangle([right_x + pad,
                    y + int(16 * font_scale),
                    W - pad,
                    y + int(16 * font_scale) + bar_h],
                   fill=theme.accent)
    y += int(48 * font_scale)

    # Calories line
    kcal_line = f"{card.total_calories} Calorie Meal"
    draw.text((right_x + pad, y),
              kcal_line,
              font=_get_font(theme, int(46*font_scale), "bold"),
              fill=(40, 40, 40))
    y += int(64 * font_scale)

    # Sections
    section_title_font = _get_font(theme, int(42*font_scale), "bold")
    item_font          = _get_font(theme, int(34*font_scale), "regular")

    WRAP_CHARS = 44  # slightly wider lines on the larger canvas
    for sec in card.sections:
        header_h = int(54 * font_scale)
        draw.rectangle([right_x, y, W, y + header_h], fill=theme.accent)
        draw.text((right_x + pad, y + int(10*font_scale)),
                  sec.name.upper(), font=section_title_font, fill=(255, 255, 255))
        y += header_h + int(14 * font_scale)

        for it in sec.items:
            line = it.text + (f" - {it.cal} cal" if it.cal is not None else "")
            for wline in textwrap.wrap(line, width=WRAP_CHARS):
                draw.text((right_x + pad, y), wline, font=item_font, fill=(40, 40, 40))
                y += int(44 * font_scale)
        y += int(12 * font_scale)

    # Footer strip + text
    footer_h = int(78 * font_scale)
    draw.rectangle([right_x, H - footer_h, W, H], fill=(255, 255, 255))
    draw.rectangle([right_x, H - footer_h, W, H - footer_h + int(8*font_scale)], fill=theme.accent_light)

    ft_font = _get_font(theme, int(34*font_scale), "italic")
    footer_text = card.footer_text or ""
    try:
        w_ft = draw.textlength(footer_text, font=ft_font)
        h_bbox = ft_font.getbbox(footer_text)
        h_ft = h_bbox[3] - h_bbox[1]
    except Exception:
        w_ft, h_ft = 200, int(34 * font_scale)
    draw.text((W - pad - w_ft, H - footer_h + (footer_h - h_ft)//2),
              footer_text, font=ft_font, fill=theme.accent_light)

    # Optional logo
    if card.logo_path and os.path.exists(card.logo_path):
        try:
            logo = Image.open(card.logo_path).convert("RGBA")
            target_w = int(240 * font_scale)
            scale = target_w / max(1, logo.width)
            logo = logo.resize((int(logo.width*scale), int(logo.height*scale)), resample=Image.LANCZOS)
            lx = W - pad - logo.width
            ly = pad
            img.paste(logo, (lx, ly), logo)
        except Exception:
            pass

    img.save(output_path)
    return output_path

