from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import textwrap, os, json

@dataclass
class MealItem:
    text: str
    cal: Optional[int] = None

@dataclass
class MealSection:
    name: str
    items: List[MealItem]

@dataclass
class MealCardData:
    journey_title: str = "JOURNEY 3.0"
    meal_title: str = "Meal"
    date_str: str = "MM/DD/YY"
    total_calories: int = 400
    sections: List[MealSection] = field(default_factory=list)
    footer_text: str = ""

def _get_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    try:
        if weight == "bold":
            return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)
        elif weight == "italic":
            return ImageFont.truetype("C:/Windows/Fonts/ariali.ttf", size)
        else:
            return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
    except Exception:
        return ImageFont.load_default()

def render_meal_card(
    card: MealCardData,
    photo_path: str,
    output_path: str = "meal_card.png",
    size: Tuple[int, int] = (1600, 1000),
    panel_color=(255, 255, 255),
    accent=(108, 50, 140),
    accent_light=(150, 90, 180),
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
        photo = photo.resize(new_size, Image.Resampling.LANCZOS)
        x0 = (photo.width - left_w) // 2
        y0 = (photo.height - H) // 2
        photo = photo.crop((x0, y0, x0 + left_w, y0 + H))
        img.paste(photo, (0, 0))
    else:
        draw.rectangle([0, 0, left_w, H], fill=(230, 230, 230))
        draw.text((pad, pad), "PHOTO NOT FOUND", font=_get_font(36, "bold"), fill=(120, 120, 120))

    draw.rectangle([right_x, 0, W, H], fill=panel_color)

    y = pad
    draw.text((right_x + pad, y), card.journey_title, font=_get_font(46, "bold"), fill=(20, 20, 20))
    y += 60

    meal_line = f"{card.meal_title} - {card.date_str}"
    draw.text((right_x + pad, y), meal_line, font=_get_font(36, "bold"), fill=(20, 20, 20))
    y += 26

    bar_h = 10
    draw.rectangle([right_x + pad, y + 16, W - pad, y + 16 + bar_h], fill=accent)
    y += 40

    kcal_line = f"{card.total_calories} Calorie Meal"
    draw.text((right_x + pad, y), kcal_line, font=_get_font(34, "bold"), fill=(40, 40, 40))
    y += 50

    section_title_font = _get_font(30, "bold")
    item_font = _get_font(26, "regular")

    for sec in card.sections:
        header_h = 42
        draw.rectangle([right_x, y, W, y + header_h], fill=accent)
        draw.text((right_x + pad, y + 7), sec.name.upper(), font=section_title_font, fill=(255, 255, 255))
        y += header_h + 10

        for it in sec.items:
            line = it.text + (f" - {it.cal} cal" if it.cal is not None else "")
            for wline in textwrap.wrap(line, width=40):
                draw.text((right_x + pad, y), wline, font=item_font, fill=(40, 40, 40))
                y += 36
        y += 8

    footer_h = 60
    draw.rectangle([right_x, H - footer_h, W, H], fill=(255, 255, 255))
    draw.rectangle([right_x, H - footer_h, W, H - footer_h + 6], fill=accent_light)
    footer_text = card.footer_text or ""
    ft_font = _get_font(28, "italic")
    try:
        w_ft = draw.textlength(footer_text, font=ft_font)
        h_bbox = ft_font.getbbox(footer_text)
        h_ft = h_bbox[3] - h_bbox[1]
    except Exception:
        w_ft, h_ft = 200, 28
    draw.text((W - pad - w_ft, H - footer_h + (footer_h - h_ft)//2), footer_text, font=ft_font, fill=accent_light)

    img.save(output_path)
    return output_path

def dict_to_card(d: dict) -> MealCardData:
    sections = []
    for sec in d.get("sections", []):
        items = [MealItem(**it) if isinstance(it, dict) else MealItem(text=str(it)) for it in sec.get("items", [])]
        sections.append(MealSection(name=sec.get("name", "SECTION"), items=items))
    return MealCardData(
        journey_title=d.get("journey_title", "JOURNEY 3.0"),
        meal_title=d.get("meal_title", "Meal"),
        date_str=d.get("date_str", "MM/DD/YY"),
        total_calories=int(d.get("total_calories", 400)),
        sections=sections,
        footer_text=d.get("footer_text", ""),
    )
