# meal_card_generator.py
# Classic, readable layout: stacked sections with band headers; full item text + " - ### cal"
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

# ---------- Data models ----------
@dataclass
class Theme:
    panel_color: Tuple[int,int,int]=(244,244,244)
    accent: Tuple[int,int,int]=(103,43,145)
    text: Tuple[int,int,int]=(20,20,20)
    faint: Tuple[int,int,int]=(120,120,120)

@dataclass
class MealItem:
    text: str           # full text as typed (e.g., "Eggs 2 each")
    cal: int            # integer calories

@dataclass
class MealSection:
    title: str
    items: List[MealItem]=field(default_factory=list)

@dataclass
class MealCardData:
    program_title: str
    meal_title: str
    date_str: str
    class_name: Optional[str]=None
    brand: Optional[str]=None
    # Legacy fields (back-compat)
    protein: Optional[MealSection]=None
    carb: Optional[MealSection]=None
    fat: Optional[MealSection]=None
    # Preferred dynamic list: render these if present; empty sections omitted automatically
    sections: Optional[List[MealSection]]=None

# ---------- Font helpers ----------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()

def _text_size(draw: ImageDraw.ImageDraw, txt: str, font: ImageFont.FreeTypeFont) -> Tuple[int,int]:
    bbox = draw.textbbox((0,0), txt, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

# simple word-wrap that preserves the full text (no ellipsis)
def _wrap(draw, text: str, font, max_w: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], ""
    for w in words:
        cand = w if not cur else f"{cur} {w}"
        if _text_size(draw, cand, font)[0] <= max_w:
            cur = cand
        else:
            lines.append(cur or w)
            cur = w if cur else ""
    if cur:
        lines.append(cur)
    return lines

# draw one item: • <full text> - ### cal  (wraps if needed; calories on the first line)
def _draw_item(draw, x: int, y: int, text: str, kcal: int, font, color_text, color_kcal, line_h: int, max_w: int) -> int:
    bullet = "• "
    kcal_str = f"{kcal} cal"
    first_line_text = f"{bullet}{text} - {kcal_str}"
    lines = _wrap(draw, first_line_text, font, max_w)

    for i, ln in enumerate(lines):
        # Indent continuation lines under text (no extra bullet)
        if i > 0 and ln.startswith(bullet):
            ln = ln[len(bullet):]
        draw.text((x, y), ln, font=font, fill=color_text)
        y += line_h
    return y

# ---------- Main render ----------
def render_meal_card(card: MealCardData,
                     photo_path: Optional[str]=None,
                     output_path: str="meal_card.png",
                     size: Tuple[int,int]=(1920,1200),
                     theme: Theme=Theme(),
                     font_scale: float=1.2,
                     panel_ratio: float=0.52):
    W, H = size
    img = Image.new("RGB", (W, H), (255,255,255))
    draw = ImageDraw.Draw(img)

    # Fonts
    H1  = _load_font(int(88*font_scale))  # program title
    H2  = _load_font(int(52*font_scale))  # "Meal 1 - 10/10/25"
    TAG = _load_font(int(40*font_scale))  # group/brand
    HC  = _load_font(int(60*font_scale))  # TOTAL CALORIE headline
    SEC = _load_font(int(40*font_scale))  # section header
    T   = _load_font(int(36*font_scale))  # items

    margin = 48

    # Right photo panel
    panel_w = int(W * panel_ratio)
    panel_x = W - panel_w
    draw.rectangle([panel_x, 0, W, H], fill=theme.panel_color)
    if photo_path:
        try:
            ph = Image.open(photo_path).convert("RGB")
            pad = 48
            max_w = panel_w - pad*2
            max_h = H - pad*2
            ph.thumbnail((max_w, max_h))
            px = panel_x + pad + (max_w - ph.width)//2
            py = pad + (max_h - ph.height)//2
            img.paste(ph, (px, py))
        except Exception:
            pass

    # Header (left)
    x0 = margin
    y  = margin
    draw.text((x0, y), card.program_title, font=H1, fill=theme.accent)
    y += _text_size(draw, card.program_title, H1)[1] + int(12*font_scale)

    meal_line = f"{card.meal_title} - {card.date_str}"
    draw.text((x0, y), meal_line, font=H2, fill=theme.text)
    y += _text_size(draw, meal_line, H2)[1] + int(8*font_scale)

    if card.class_name:
        draw.text((x0, y), card.class_name, font=TAG, fill=theme.faint)
        y += _text_size(draw, card.class_name, TAG)[1] + int(8*font_scale)

    # Sections to render (dynamic if provided, else legacy non-empty)
    if card.sections:
        sections = [s for s in card.sections if s.items]
    else:
        sections = []
        if card.protein and card.protein.items: sections.append(card.protein)
        if card.carb and card.carb.items:       sections.append(card.carb)
        if card.fat and card.fat.items:         sections.append(card.fat)

    # If nothing to render, save header/photo and return
    if not sections:
        img.save(output_path, "PNG"); return

    # ---- NEW: Total Calories headline + thin accent rule ----
    total_kcal = sum(it.cal for s in sections for it in s.items)
    cal_line = f"{total_kcal} Calorie Meal"
    draw.text((x0, y), cal_line, font=HC, fill=theme.text)
    y += _text_size(draw, cal_line, HC)[1] + int(10*font_scale)

    # thin accent rule
    content_w = (panel_x - margin)  # left content width
    rule_h = max(2, int(6 * font_scale))
    draw.rectangle([x0, y, x0 + content_w, y + rule_h], fill=theme.accent)
    y += rule_h + int(14*font_scale)
    # ---- /NEW ----

    # Section blocks
    band_h = int(48 * font_scale)
    item_line_h = int(44 * font_scale)
    box_gap = int(16 * font_scale)
    inner_pad = int(14 * font_scale)

    for sec in sections:
        # Section band
        band_text = sec.title.upper()
        draw.rectangle([x0, y, x0 + content_w, y + band_h], fill=theme.accent)
        ty = y + (band_h - _text_size(draw, band_text, SEC)[1]) // 2
        draw.text((x0 + inner_pad, ty), band_text, font=SEC, fill=(255,255,255))
        y += band_h + int(10*font_scale)

        # Items (full text + " - ### cal"), wrapped as needed
        max_w = content_w - inner_pad*2
        for it in sec.items:
            y = _draw_item(
                draw=draw,
                x=x0 + inner_pad,
                y=y,
                text=it.text,
                kcal=int(it.cal),
                font=T,
                color_text=theme.text,
                color_kcal=theme.faint,
                line_h=item_line_h,
                max_w=max_w
            )
        y += box_gap

    # Footer brand (bottom-right of left area), if present
    if card.brand:
        bw, bh = _text_size(draw, card.brand, TAG)
        bx = x0 + content_w - bw
        by = H - bh - margin
        draw.text((bx, by), card.brand, font=TAG, fill=theme.faint)

    img.save(output_path, "PNG")

