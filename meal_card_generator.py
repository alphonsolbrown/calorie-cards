# meal_card_generator.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import os
import math
import textwrap

# --------- Fonts (use DejaVu if present, otherwise fall back) ----------
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
DEJAVU_SANS = os.path.join(FONT_DIR, "DejaVuSans.ttf")
DEJAVU_SANS_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

def _font(path: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        if bold and os.path.exists(DEJAVU_SANS_BOLD):
            return ImageFont.truetype(DEJAVU_SANS_BOLD, size=size)
        if os.path.exists(DEJAVU_SANS):
            return ImageFont.truetype(DEJAVU_SANS, size=size)
        # last resort
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()

# ----------------- Data models -----------------
@dataclass
class Theme:
    panel_color: Tuple[int, int, int] = (244, 244, 244)
    accent: Tuple[int, int, int] = (103, 43, 145)    # purple bar
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

# ----------------- helpers -----------------
def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    # getbbox is more accurate/newer PIL
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

def _fit_font_size(draw: ImageDraw.ImageDraw, text: str, target_w: int, base_px: int, min_px: int) -> int:
    """Decrease font size until the text fits the target width."""
    size = base_px
    while size > min_px:
        f = _font(DEJAVU_SANS, size)
        w, _ = _measure(draw, text, f)
        if w <= target_w:
            return size
        size -= 1
    return max(min_px, 10)

def _draw_header_text(draw, x, y, text, color, base_px, max_w, bold=False):
    size = _fit_font_size(draw, text, max_w, base_px, int(base_px*0.55))
    f = _font(DEJAVU_SANS, size, bold=bold)
    draw.text((x, y), text, fill=color, font=f)
    _, h = _measure(draw, text, f)
    return h, size

def _draw_rule(draw, x, y, w, color, h=14):
    draw.rectangle([x, y, x+w, y+h], fill=color)

def _draw_section_box(draw, x, y, w, h, theme: Theme):
    draw.rectangle([x, y, x+w, y+h], fill=theme.panel_color)

def _wrap_lines_to_fit(draw, lines: List[str], box_w: int, base_px: int, min_px: int) -> Tuple[List[Tuple[str,int]], int]:
    """Return [(line, chosen_px)], and the max chosen_px actually used."""
    fitted = []
    used_max = 0
    for line in lines:
        px = _fit_font_size(draw, line, box_w, base_px, min_px)
        used_max = max(used_max, px)
        fitted.append((line, px))
    return fitted, used_max

def _section_height(draw, lines_fitted: List[Tuple[str,int]], line_gap: int) -> int:
    total = 0
    for (line, px) in lines_fitted:
        f = _font(DEJAVU_SANS, px)
        _, hh = _measure(draw, line, f)
        total += hh + line_gap
    return total

# ----------------- renderer -----------------
def render_meal_card(
    card: MealCardData,
    photo_path: Optional[str],
    output_path: str = "meal_card.png",
    size: Tuple[int, int] = (1920, 1200),
    theme: Theme = Theme(),
    font_scale: float = 1.0,
    panel_ratio: float = 0.52,           # two-panel split; auto ignored for 4-panel
) -> str:

    W, H = size
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # pick layout: 4-panel if lots of lines; else two-panel
    line_count = (len(card.protein.items) + len(card.carb.items) + len(card.fat.items))
    use_four = line_count >= 8

    # panel sizes
    margin = int(24 * font_scale)
    gutter = int(18 * font_scale)

    left_x = margin
    left_y = margin
    if not use_four:
        # two-panel: photo left, everything right
        right_w = int((W - margin*2) * max(0.42, min(0.72, panel_ratio)))
        left_w = (W - (margin*3)) - right_w
        left_h = H - margin*2
        right_x = left_x + left_w + margin
        right_y = margin
        right_h = H - margin*2

        # photo panel
        _draw_section_box(draw, left_x, left_y, left_w, left_h, theme)
        if photo_path and os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            photo = photo.copy()
            photo.thumbnail((left_w, left_h))
            # cover: center crop
            pw, ph = photo.size
            canvas = Image.new("RGB", (left_w, left_h), (240,240,240))
            canvas.paste(photo, ((left_w - pw)//2, (left_h - ph)//2))
            img.paste(canvas, (left_x, left_y))

        # right content
        content_x = right_x
        content_w = right_w
        y = right_y

    else:
        # four-panel grid
        col_w = (W - margin*3)//2
        row_h = (H - margin*3)//2
        # top-left: photo
        _draw_section_box(draw, left_x, left_y, col_w, row_h, theme)
        if photo_path and os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            photo.thumbnail((col_w, row_h))
            pw, ph = photo.size
            canv = Image.new("RGB", (col_w, row_h), (240,240,240))
            canv.paste(photo, ((col_w - pw)//2, (row_h - ph)//2))
            img.paste(canv, (left_x, left_y))
        # set content start in the other half (top-right)
        content_x = left_x + col_w + margin
        content_w = col_w
        y = left_y

    # ------- Header (Program / Class / Meal / Date / Total Cal) -------
    title_px = int(84 * font_scale)
    sub_px = int(44 * font_scale)
    rule_h = int(16 * font_scale)
    pad_y = int(12 * font_scale)

    # Program title
    used_h, _ = _draw_header_text(draw, content_x, y, card.program_title, theme.text, title_px, content_w, bold=True)
    y += used_h + pad_y

    if card.class_name:
        h2, _ = _draw_header_text(draw, content_x, y, card.class_name, theme.faint, sub_px, content_w)
        y += h2 + pad_y

    # Meal + date line
    meal_line = f"{card.meal_title} - {card.date_str}"
    h3, _ = _draw_header_text(draw, content_x, y, meal_line, theme.text, int(60*font_scale), content_w, bold=True)
    y += h3 + int(6*font_scale)
    _draw_rule(draw, content_x, y, content_w, theme.accent, rule_h)
    y += rule_h + pad_y

    # Total calories (always shown)
    total_line = f"{int(round(card.total_cal))} Calorie Meal"
    h4, _ = _draw_header_text(draw, content_x, y, total_line, theme.text, int(58*font_scale), content_w, bold=True)
    y += h4 + int(10*font_scale)

    # ---------------- Sections ----------------
    def section_block(title: str, lines: List[str], start_y: int) -> int:
        # heading bar
        bar_h = int(54 * font_scale)
        draw.rectangle([content_x, start_y, content_x+content_w, start_y+bar_h], fill=theme.accent)
        # heading text
        head_px = int(40*font_scale)
        head_font = _font(DEJAVU_SANS_BOLD, head_px)
        tx, ty = _measure(draw, title, head_font)
        draw.text((content_x+int(16*font_scale), start_y + (bar_h-ty)//2), title, fill=(255,255,255), font=head_font)
        y2 = start_y + bar_h + int(12*font_scale)

        # lines, auto fit
        base_px = int(42 * font_scale)
        min_px = int(22 * font_scale)
        fitted, _ = _wrap_lines_to_fit(draw, lines, content_w - int(20*font_scale), base_px, min_px)
        line_gap = int(10*font_scale)

        for line, px in fitted:
            f = _font(DEJAVU_SANS, px)
            draw.text((content_x+int(10*font_scale), y2), line, fill=theme.text, font=f)
            _, hln = _measure(draw, line, f)
            y2 += hln + line_gap

        # bottom rule (light)
        _draw_rule(draw, content_x, y2, content_w, (230, 222, 235), int(10*font_scale))
        y2 += int(10*font_scale)
        return y2

    prot_lines = [f"{it.text} - {int(round(it.cal))} cal" for it in card.protein.items] or ["—"]
    carb_lines = [f"{it.text} - {int(round(it.cal))} cal" for it in card.carb.items] or ["—"]
    fat_lines  = [f"{it.text} - {int(round(it.cal))} cal" for it in card.fat.items] or ["—"]

    y = section_block("PROTEIN", prot_lines, y)
    if use_four:
        # continue in lower-left, then right column sections
        # lower-left box origin
        col_w = (W - margin*3)//2
        row_h = (H - margin*3)//2
        # move to lower-left (under photo)
        content_x = left_x
        content_w = col_w
        y = left_y + row_h + margin
        y = section_block("CARB", carb_lines, y)

        # move to right column (two stacked)
        content_x = left_x + col_w + margin
        content_w = col_w
        y = left_y
        y = section_block("FAT", fat_lines, y)
    else:
        # two-panel continues vertically
        y = section_block("CARB", carb_lines, y)
        y = section_block("FAT",  fat_lines,  y)

    # brand (tiny)
    if card.brand:
        brand_px = int(24*font_scale)
        f = _font(DEJAVU_SANS, brand_px, bold=False)
        bw, bh = _measure(draw, card.brand, f)
        draw.text((W - bw - margin, H - bh - margin//2), card.brand, fill=theme.faint, font=f)

    img.save(output_path, "PNG")
    return output_path

