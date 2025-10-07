from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import textwrap, os

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
    panel_color: Tuple[int,int,int] = (255,255,255)
    accent: Tuple[int,int,int] = (108,50,140)
    accent_light: Tuple[int,int,int] = (150,90,180)
    font_regular: str = "C:/Windows/Fonts/arial.ttf"
    font_bold: str = "C:/Windows/Fonts/arialbd.ttf"
    font_italic: str = "C:/Windows/Fonts/ariali.ttf"

@dataclass
class MealCardData:
    journey_title: str = "JOURNEY 3.0"
    meal_title: str = "Meal"
    date_str: str = "MM/DD/YY"
    total_calories: int = 400
    sections: List[MealSection] = field(default_factory=list)
    footer_text: str = ""
    logo_path: Optional[str] = None

def _get_font(theme: Theme, size: int, weight: str = "regular"):
    try:
        if weight == "bold":
            return ImageFont.truetype(theme.font_bold, size)
        elif weight == "italic":
            return ImageFont.truetype(theme.font_italic, size)
        else:
            return ImageFont.truetype(theme.font_regular, size)
    except Exception:
        return ImageFont.load_default()

def render_meal_card(
    card: MealCardData,
    photo_path: str,
    output_path: str = "meal_card.png",
    size: Tuple[int, int] = (1600, 1000),
    theme: Theme = Theme(),
    font_scale: float = 1.3,
) -> str:
    W, H = size
    img = Image.new("RGB", size, color=(245, 245, 245))
    draw = ImageDraw.Draw(img)

    left_w = int(W * 0.64)
    right_x = left_w
    pad = 30

    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGB")
        ratio = max(left_w / photo.width, H / photo.height)
        new_size = (int(photo.width * ratio), int(photo.height * ratio))
        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS
        photo = photo.resize(new_size, resample)
        x0 = (photo.width - left_w) // 2
        y0 = (photo.height - H) // 2
        photo = photo.crop((x0, y0, x0 + left_w, y0 + H))
        img.paste(photo, (0, 0))
    else:
        draw.rectangle([0, 0, left_w, H], fill=(230, 230, 230))
        draw.text((pad, pad), "PHOTO NOT FOUND", font=_get_font(theme,36,"bold"), fill=(120, 120, 120))

    draw.rectangle([right_x, 0, W, H], fill=theme.panel_color)

    y = pad
    draw.text((right_x + pad, y), card.journey_title, font=_get_font(theme, int(46*font_scale),"bold"), fill=(20,20,20))
    y += int(60*font_scale)

    meal_line = f"{card.meal_title} - {card.date_str}"
    draw.text((right_x + pad, y), meal_line, font=_get_font(theme, int(36*font_scale),"bold"), fill=(20,20,20))
    y += int(26*font_scale)

    bar_h = int(10*font_scale)
    draw.rectangle([right_x + pad, y + int(16*font_scale), W - pad, y + int(16*font_scale) + bar_h], fill=theme.accent)
    y += int(40*font_scale)

    kcal_line = f"{card.total_calories} Calorie Meal"
    draw.text((right_x + pad, y), kcal_line, font=_get_font(theme, int(42*font_scale),"bold"), fill=(40,40,40))
    y += int(50*font_scale)

    section_title_font = _get_font(theme, int(30*font_scale),"bold")
    item_font = _get_font(theme, int(26*font_scale),"regular")

    for sec in card.sections:
        header_h = int(42*font_scale)
        draw.rectangle([right_x, y, W, y + header_h], fill=theme.accent)
        draw.text((right_x + pad, y + int(7*font_scale)), sec.name.upper(), font=section_title_font, fill=(255,255,255))
        y += header_h + int(10*font_scale)
        for it in sec.items:
            line = it.text + (f" - {it.cal} cal" if it.cal is not None else "")
            import textwrap as _tw
            for wline in _tw.wrap(line, width=40):
                draw.text((right_x + pad, y), wline, font=item_font, fill=(40,40,40))
                y += int(36*font_scale)
        y += int(8*font_scale)

    footer_h = int(60*font_scale)
    draw.rectangle([right_x, H - footer_h, W, H], fill=(255,255,255))
    draw.rectangle([right_x, H - footer_h, W, H - footer_h + int(6*font_scale)], fill=theme.accent_light)
    footer_text = card.footer_text or ""
    ft_font = _get_font(theme, int(32*font_scale),"italic")
    try:
        w_ft = draw.textlength(footer_text, font=ft_font)
        h_bbox = ft_font.getbbox(footer_text)
        h_ft = h_bbox[3] - h_bbox[1]
    except Exception:
        w_ft, h_ft = 200, 28
    draw.text((W - pad - w_ft, H - footer_h + (footer_h - h_ft)//2), footer_text, font=ft_font, fill=theme.accent_light)

    if card.logo_path and os.path.exists(card.logo_path):
        try:
            logo = Image.open(card.logo_path).convert("RGBA")
            scale = 200 / max(1, logo.width)
            logo = logo.resize((int(logo.width*scale), int(logo.height*scale)), resample=resample)
            lx = W - pad - logo.width
            ly = pad
            img.paste(logo, (lx, ly), logo)
        except Exception:
            pass

    img.save(output_path)
    return output_path
