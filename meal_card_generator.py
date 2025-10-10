# meal_card_generator.py (backward-compatible dynamic sections)
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
    text: str
    cal: int

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
    # Legacy fields (keep for back-compat)
    protein: Optional[MealSection]=None
    carb: Optional[MealSection]=None
    fat: Optional[MealSection]=None
    # New dynamic list: if provided, render only these sections (omit empties)
    sections: Optional[List[MealSection]]=None

# ---------- Rendering helpers (fonts/layout kept simple for brevity) ----------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()

def _draw_text(draw, xy, text, font, fill=(0,0,0)):
    draw.text(xy, text, font=font, fill=fill)

def _col_layout(n_cols: int, W: int, margin: int=48):
    pad = margin
    inner = W - (margin*2)
    col_w = int(inner / n_cols)
    xs = [margin + i*col_w for i in range(n_cols)]
    return xs, col_w, pad

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

    # Header
    H1 = _load_font(int(64*font_scale))
    H2 = _load_font(int(36*font_scale))
    T  = _load_font(int(28*font_scale))
    S  = _load_font(int(22*font_scale))

    _draw_text(draw, (48, 36), card.program_title, H1, theme.accent)
    _draw_text(draw, (48, 110), f"{card.meal_title}  •  {card.date_str}", H2, theme.text)
    y = 160
    if card.class_name:
        _draw_text(draw, (48, y), card.class_name, T, theme.faint); y += int(36*font_scale)
    if card.brand:
        _draw_text(draw, (48, y), card.brand, S, theme.faint)

    # Photo panel (right)
    panel_w = int(W * panel_ratio)
    panel_x = W - panel_w
    draw.rectangle([panel_x, 0, W, H], fill=theme.panel_color)
    if photo_path:
        try:
            ph = Image.open(photo_path).convert("RGB")
            # fit photo inside right panel with margins
            pad = 48
            box = (panel_x+pad, pad, W-pad, H-pad)
            ph.thumbnail((box[2]-box[0], box[3]-box[1]))
            # center
            px = panel_x + pad + ((box[2]-box[0]) - ph.width)//2
            py = pad + ((box[3]-box[1]) - ph.height)//2
            img.paste(ph, (px, py))
        except Exception:
            pass

    # Sections to render (dynamic if provided, else fall back to legacy)
    if card.sections and len(card.sections) > 0:
        sections = [s for s in card.sections if s.items]   # omit empty
    else:
        # Back-compat: show only non-empty of the legacy 3
        tmp = []
        if card.protein and card.protein.items: tmp.append(card.protein)
        if card.carb and card.carb.items:       tmp.append(card.carb)
        if card.fat and card.fat.items:         tmp.append(card.fat)
        sections = tmp

    # Left content area (everything except photo panel)
    content_w = panel_x
    n_cols = max(1, min(len(sections), 4))  # up to 4 columns so long lists stay readable
    xs, col_w, pad = _col_layout(n_cols, content_w, margin=48)
    top_y = 220

    # Render columns
    for idx, sec in enumerate(sections):
        x = xs[idx % n_cols]
        y = top_y + (idx // n_cols) * 0  # simple top alignment
        _draw_text(draw, (x, y), sec.title, H2, theme.accent); y += int(40*font_scale)
        # Items
        for it in sec.items:
            _draw_text(draw, (x, y), f"• {it.text}", T, theme.text)
            _draw_text(draw, (x + col_w - 140, y), f"{it.cal} kcal", T, theme.faint)
            y += int(34*font_scale)

    img.save(output_path, "PNG")

