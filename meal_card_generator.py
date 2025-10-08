# meal_card_generator.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import os

# ---------- Fonts ----------
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
DEJAVU_SANS = os.path.join(FONT_DIR, "DejaVuSans.ttf")
DEJAVU_SANS_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

def _font(path: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        if bold and os.path.exists(DEJAVU_SANS_BOLD):
            return ImageFont.truetype(DEJAVU_SANS_BOLD, size=size)
        if os.path.exists(DEJAVU_SANS):
            return ImageFont.truetype(DEJAVU_SANS, size=size)
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()

# ---------- Data ----------
@dataclass
class Theme:
    panel_color: Tuple[int, int, int] = (244, 244, 244)
    accent: Tuple[int, int, int] = (103, 43, 145)
    text: Tuple[int, int, int] = (20, 20, 20)
    faint: Tuple[int, int, int] = (120, 120, 120)

@dataclass
class MealItem:
    text: str
    cal: float

@dataclass
class MealSection:
    name: str
    items: List[MealItem] = field(default_factory=list)

    @property
    def total(self) -> float:
        return float(sum(i.cal for i in self.items))

@dataclass
class MealCardData:
    program_title: str
    class_name: Optional[str]
    meal_title: str
    date_str: str
    brand: Optional[str]
    protein: MealSection
    carb: MealSection
    fat: MealSection

    @property
    def total_cal(self) -> float:
        return float(self.protein.total + self.carb.total + self.fat.total)

# ---------- helpers ----------
def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont):
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

def _fit_font_size(draw, text, max_w, base_px, min_px):
    size = base_px
    while size > min_px:
        f = _font(DEJAVU_SANS, size)
        w, _ = _measure(draw, text, f)
        if w <= max_w:
            return size
        size -= 1
    return max(min_px, 10)

def _draw_header_text(draw, x, y, text, color, base_px, max_w, bold=False):
    size = _fit_font_size(draw, text, max_w, base_px, int(base_px*0.55))
    f = _font(DEJAVU_SANS, size, bold=bold)
    draw.text((x, y), text, fill=color, font=f)
    _, h = _measure(draw, text, f)
    return h

def _draw_rule(draw, x, y, w, color, h=14):
    draw.rectangle([x, y, x+w, y+h], fill=color)

# ---------- renderer ----------
def render_meal_card(
    card: MealCardData,
    photo_path: Optional[str],
    output_path: str = "meal_card.png",
    size: Tuple[int, int] = (1920, 1200),
    theme: Theme = Theme(),
    font_scale: float = 1.0,
    panel_ratio: float = 0.52,
) -> str:

    W, H = size
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # decide layout
    lines_ct = len(card.protein.items) + len(card.carb.items) + len(card.fat.items)
    use_four = lines_ct >= 8

    margin = int(24 * font_scale)
    left_x = margin
    left_y = margin

    if not use_four:
        right_w = int((W - margin*2) * max(0.42, min(0.72, panel_ratio)))
        left_w = (W - (margin*3)) - right_w
        left_h = H - margin*2
        right_x = left_x + left_w + margin
        right_y = margin
        right_h = H - margin*2

        # photo left
        if photo_path and os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            photo.thumbnail((left_w, left_h))
            pw, ph = photo.size
            canvas = Image.new("RGB", (left_w, left_h), (240,240,240))
            canvas.paste(photo, ((left_w - pw)//2, (left_h - ph)//2))
            img.paste(canvas, (left_x, left_y))

        content_x, content_w, y = right_x, right_w, right_y

    else:
        col_w = (W - margin*3)//2
        row_h = (H - margin*3)//2
        # photo top-left
        if photo_path and os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            photo.thumbnail((col_w, row_h))
            pw, ph = photo.size
            canv = Image.new("RGB", (col_w, row_h), (240,240,240))
            canv.paste(photo, ((col_w - pw)//2, (row_h - ph)//2))
            img.paste(canv, (left_x, left_y))
        content_x, content_w, y = left_x + col_w + margin, col_w, left_y

    # header
    title_px = int(84 * font_scale)
    sub_px   = int(44 * font_scale)
    rule_h   = int(16 * font_scale)
    pad_y    = int(12 * font_scale)

    y += _draw_header_text(draw, content_x, y, card.program_title, theme.text, title_px, content_w, True) + pad_y
    if card.class_name:
        y += _draw_header_text(draw, content_x, y, card.class_name, theme.faint, sub_px, content_w) + pad_y

    meal_line = f"{card.meal_title} - {card.date_str}"
    y += _draw_header_text(draw, content_x, y, meal_line, theme.text, int(60*font_scale), content_w, True) + int(6*font_scale)
    _draw_rule(draw, content_x, y, content_w, theme.accent, rule_h)
    y += rule_h + pad_y

    total_line = f"{int(round(card.total_cal))} Calorie Meal"
    y += _draw_header_text(draw, content_x, y, total_line, theme.text, int(58*font_scale), content_w, True) + int(10*font_scale)

    def section_block(title: str, lines):
        nonlocal y, content_x, content_w
        bar_h = int(54 * font_scale)
        draw.rectangle([content_x, y, content_x+content_w, y+bar_h], fill=theme.accent)
        head_px = int(40*font_scale)
        head_f  = _font(DEJAVU_SANS_BOLD, head_px)
        tx, th  = _measure(draw, title, head_f)
        draw.text((content_x+int(16*font_scale), y + (bar_h-th)//2), title, fill=(255,255,255), font=head_f)
        y += bar_h + int(12*font_scale)

        base_px = int(42 * font_scale)
        min_px  = int(22 * font_scale)
        for line in (lines or ["—"]):
            px = _fit_font_size(draw, line, content_w - int(20*font_scale), base_px, min_px)
            f  = _font(DEJAVU_SANS, px)
            draw.text((content_x+int(10*font_scale), y), line, fill=theme.text, font=f)
            _, hln = _measure(draw, line, f)
            y += hln + int(10*font_scale)
        _draw_rule(draw, content_x, y, content_w, (230, 222, 235), int(10*font_scale))
        y += int(10*font_scale)

    prot_lines = [f"{i.text} - {int(round(i.cal))} cal" for i in card.protein.items]
    carb_lines = [f"{i.text} - {int(round(i.cal))} cal" for i in card.carb.items]
    fat_lines  = [f"{i.text} - {int(round(i.cal))} cal" for i in card.fat.items]

    if not use_four:
        section_block("PROTEIN", prot_lines)
        section_block("CARB", carb_lines)
        section_block("FAT",  fat_lines)
    else:
        section_block("PROTEIN", prot_lines)
        # move to lower-left
        col_w = (W - margin*3)//2
        row_h = (H - margin*3)//2
        content_x, content_w, y = left_x, col_w, left_y + row_h + margin
        section_block("CARB", carb_lines)
        # right column
        content_x, content_w, y = left_x + col_w + margin, col_w, left_y
        section_block("FAT", fat_lines)

    if card.brand:
        bpx = int(24*font_scale)
        bf  = _font(DEJAVU_SANS, bpx)
        bw, bh = _measure(draw, card.brand, bf)
        draw.text((W - bw - margin, H - bh - margin//2), card.brand, fill=theme.faint, font=bf)

    img.save(output_path, "PNG")
    return output_path

