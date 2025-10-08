# meal_card_generator.py
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os, textwrap

def _first_existing(paths):
    for p in paths:
        if p and Path(p).exists():
            return str(p)
    return None

def _resolve_font_path(kind: str) -> str | None:
    here = Path(__file__).parent
    bundled = {
        "regular": here / "fonts" / "DejaVuSans.ttf",
        "bold":    here / "fonts" / "DejaVuSans-Bold.ttf",
        "italic":  here / "fonts" / "DejaVuSans-Oblique.ttf",
    }[kind]
    linux = "/usr/share/fonts/truetype/dejavu"
    linux_candidates = {
        "regular": [f"{linux}/DejaVuSans.ttf"],
        "bold":    [f"{linux}/DejaVuSans-Bold.ttf"],
        "italic":  [f"{linux}/DejaVuSans-Oblique.ttf"],
    }[kind]
    win = Path("C:/Windows/Fonts")
    win_candidates = {
        "regular": [win / "arial.ttf"],
        "bold":    [win / "arialbd.ttf"],
        "italic":  [win / "ariali.ttf"],
    }[kind]
    return _first_existing([bundled, *linux_candidates, *win_candidates])

@dataclass
class Theme:
    panel_color: Tuple[int,int,int] = (255,255,255)
    accent: Tuple[int,int,int] = (108,50,140)
    accent_light: Tuple[int,int,int] = (150,90,180)
    font_regular: str = _resolve_font_path("regular") or ""
    font_bold:    str = _resolve_font_path("bold") or ""
    font_italic:  str = _resolve_font_path("italic") or ""

def _get_font(theme: Theme, size: int, weight: str = "regular"):
    path = theme.font_regular
    if weight == "bold" and theme.font_bold: path = theme.font_bold
    elif weight == "italic" and theme.font_italic: path = theme.font_italic
    if path:
        try: return ImageFont.truetype(path, size)
        except Exception: pass
    return ImageFont.load_default()

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
    program_title: str = "Program"
    class_name: str = ""
    meal_title: str = "Meal"
    date_str: str = "MM/DD/YY"
    total_calories: int = 400
    sections: List[MealSection] = field(default_factory=list)
    footer_text: str = ""
    logo_path: Optional[str] = None

def _wrap_lines(text: str, width_chars: int) -> List[str]:
    width_chars = max(12, width_chars)
    return textwrap.wrap(text, width=width_chars)

def _draw_photo_to_rect(canvas: Image.Image, photo_path: str, rect: Tuple[int,int,int,int]):
    x0,y0,x1,y1 = rect
    w,h = x1-x0, y1-y0
    draw = ImageDraw.Draw(canvas)
    if not os.path.exists(photo_path):
        draw.rectangle(rect, fill=(230,230,230))
        return
    photo = Image.open(photo_path).convert("RGB")
    try: resample = Image.Resampling.LANCZOS
    except Exception: resample = Image.LANCZOS
    ratio = max(w/photo.width, h/photo.height)
    new_sz = (max(1,int(photo.width*ratio)), max(1,int(photo.height*ratio)))
    photo = photo.resize(new_sz, resample)
    px0 = max(0,(photo.width-w)//2); py0 = max(0,(photo.height-h)//2)
    crop = photo.crop((px0,py0,px0+w,py0+h))
    canvas.paste(crop,(x0,y0))

def _estimate_section_height(sec: MealSection, right_w_px: int, fscale: float) -> int:
    header_h = int(64*fscale)
    item_line_h = int(50*fscale)
    avg_char_px = max(1, int(19*fscale))
    chars = max(28, min(70, right_w_px // avg_char_px))
    lines = 0
    for it in sec.items:
        line = it.text + (f" - {it.cal} cal" if it.cal is not None else "")
        lines += max(1, len(_wrap_lines(line, chars)))
    content_h = lines * item_line_h + int(16*fscale)
    return header_h + int(20*fscale) + content_h

def _fit_font_scale_for_panels(panel_heights: Dict[str,int],
                               sections_by_panel: Dict[str,List[MealSection]],
                               right_w_px: int,
                               base_scale: float) -> float:
    scale = base_scale
    for _ in range(24):
        ok = True
        for key, h in panel_heights.items():
            secs = sections_by_panel.get(key, [])
            need = sum(_estimate_section_height(s, right_w_px, scale) for s in secs)
            if need > h:
                ok = False
                ratio = h / max(1, need)
                scale = max(1.2, scale * (0.7 + 0.3*ratio))
        if ok: break
    return scale

def _draw_sections_block(draw: ImageDraw.ImageDraw, theme: Theme,
                         x: int, y: int, w: int, h: int,
                         sections: List[MealSection], fscale: float):
    # Safety guard: if height is invalid, quietly do nothing (prevents crashes).
    if h <= 2 or w <= 2: return
    x2, y2 = x + w, y + h
    if x2 <= x + 1 or y2 <= y + 1: return

    draw.rectangle([x, y, x2, y2], fill=theme.panel_color)

    section_title_font = _get_font(theme, int(52*fscale), "bold")
    item_font          = _get_font(theme, int(42*fscale), "regular")
    pad = int(30*fscale)
    yy = y + pad
    bar_h = int(64*fscale)

    avg_char_px = max(1, int(19*fscale))
    WRAP = max(28, min(70, (w - 2*pad)//avg_char_px))

    for sec in sections:
        draw.rectangle([x, yy, x + w, yy + bar_h], fill=theme.accent)
        draw.text((x + pad, yy + int(12*fscale)), sec.name.upper(),
                  font=section_title_font, fill=(255,255,255))
        yy += bar_h + int(20*fscale)

        for it in sec.items:
            line = it.text + (f" - {it.cal} cal" if it.cal is not None else "")
            for wline in _wrap_lines(line, WRAP):
                draw.text((x + pad, yy), wline, font=item_font, fill=(40,40,40))
                yy += int(50*fscale)
        yy += int(10*fscale)

def _draw_header_block(draw: ImageDraw.ImageDraw, theme: Theme,
                       x: int, y: int, w: int, fscale: float,
                       program_title: str, class_name: str,
                       meal_line: str, total_kcal: int):
    pad = int(30*fscale)
    yy = y + pad

    draw.text((x + pad, yy), program_title,
              font=_get_font(theme, int(84*fscale), "bold"), fill=(20,20,20))
    yy += int(98*fscale)

    if class_name:
        draw.text((x + pad, yy), class_name,
                  font=_get_font(theme, int(50*fscale), "italic"), fill=(60,60,60))
        yy += int(60*fscale)

    draw.text((x + pad, yy), meal_line,
              font=_get_font(theme, int(62*fscale), "bold"), fill=(20,20,20))
    yy += int(44*fscale)
    draw.rectangle([x + pad, yy + int(16*fscale), x + w - pad, yy + int(16*fscale) + int(18*fscale)],
                   fill=theme.accent)
    yy += int(60*fscale)

    kcal_line = f"{total_kcal} Calorie Meal"
    draw.text((x + pad, yy), kcal_line,
              font=_get_font(theme, int(60*fscale), "bold"), fill=(40,40,40))

def render_meal_card(
    card: MealCardData,
    photo_path: str,
    output_path: str = "meal_card.png",
    size: Tuple[int,int] = (2560,1600),
    theme: Theme = Theme(),
    font_scale: float = 2.4,
    panel_ratio: float = 0.52,         # photo smaller (text wider)
    items_threshold_for_grid: int = 8  # only switch to grid when LOTS of items
) -> str:
    W,H = size
    img = Image.new("RGB", size, (245,245,245))
    draw = ImageDraw.Draw(img)
    pad = int(36 * (W/2560))

    total_items = sum(len(s.items) for s in card.sections)

    def _render_two_panel():
        left_w  = int(W * (1 - panel_ratio))
        right_x = left_w
        right_w = W - right_x
        _draw_photo_to_rect(img, photo_path, (0,0,left_w,H))

        est_header = int(240*font_scale) + int(60*font_scale)
        est_footer = int(86*font_scale)
        avail_h = H - est_header - est_footer - pad

        fitted = _fit_font_scale_for_panels(
            {"right": avail_h}, {"right": card.sections}, right_w - 2*pad, font_scale
        )
        header_space = int(240*fitted) + int(60*fitted)
        footer_h     = int(86*fitted)
        avail_h = max(int(120*fitted), H - header_space - footer_h - pad)

        fitted = _fit_font_scale_for_panels(
            {"right": avail_h}, {"right": card.sections}, right_w - 2*pad, fitted
        )

        _draw_header_block(draw, theme, right_x, 0, right_w, fitted,
                           card.program_title, card.class_name,
                           f"{card.meal_title} - {card.date_str}",
                           card.total_calories)

        _draw_sections_block(draw, theme, right_x, header_space, right_w, avail_h,
                             card.sections, fitted)

        draw.rectangle([right_x, H - footer_h, W, H], fill=(255,255,255))
        draw.rectangle([right_x, H - footer_h, W, H - footer_h + int(12*fitted)],
                       fill=theme.accent_light)
        if card.footer_text:
            ft_font = _get_font(theme, int(40*fitted), "italic")
            try: w_ft = draw.textlength(card.footer_text, font=ft_font)
            except Exception: w_ft = 220
            draw.text((W - pad - w_ft, H - footer_h + int(footer_h*0.35)),
                      card.footer_text, font=ft_font, fill=theme.accent_light)

    def _render_four_panel():
        gutter = int(24 * (W/2560))
        col_w = (W - 3*gutter) // 2
        row_h = (H - 3*gutter) // 2

        secs = {s.name.strip().upper(): s for s in card.sections}
        sec_prot = secs.get("PROTEIN", MealSection("PROTEIN", []))
        sec_carb = secs.get("CARB",    MealSection("CARB",    []))
        sec_fat  = secs.get("FAT",     MealSection("FAT",     []))

        # TL: photo
        x0 = gutter; y0 = gutter
        x1 = x0 + col_w; y1 = y0 + row_h
        _draw_photo_to_rect(img, photo_path, (x0,y0,x1,y1))

        # BL: header + protein, with header auto-shrink if needed
        bl_x = gutter; bl_y = 2*gutter + row_h

        # start with same header recipe as two-panel, but shrink if needed
        header_h_guess = int(240*font_scale) + int(60*font_scale)
        min_section_h  = int(140*font_scale)     # ensure space for some items
        sec_area_h     = row_h - header_h_guess
        if sec_area_h < min_section_h:
            # shrink header to make room
            header_h = max(row_h - min_section_h, int(120*font_scale))
        else:
            header_h = header_h_guess
        sec_area_h = max(min_section_h, row_h - header_h)

        # still impossible? bail to 2-panel fallback
        if sec_area_h <= 4:
            _render_two_panel(); return

        _draw_header_block(draw, theme, bl_x, bl_y, col_w, font_scale,
                           card.program_title, card.class_name,
                           f"{card.meal_title} - {card.date_str}",
                           card.total_calories)

        fitted_bl = _fit_font_scale_for_panels(
            {"bl": sec_area_h}, {"bl": [sec_prot]},
            col_w - 2*int(30*font_scale), font_scale
        )
        _draw_sections_block(draw, theme, bl_x, bl_y + header_h, col_w, sec_area_h,
                             [sec_prot], fitted_bl)

        # TR: carbs
        tr_x = 2*gutter + col_w; tr_y = gutter
        fitted_tr = _fit_font_scale_for_panels(
            {"tr": row_h - 2*int(30*font_scale)}, {"tr": [sec_carb]},
            col_w - 2*int(30*font_scale), font_scale
        )
        _draw_sections_block(draw, theme, tr_x, tr_y, col_w, row_h, [sec_carb], fitted_tr)

        # BR: fats
        br_x = 2*gutter + col_w; br_y = 2*gutter + row_h
        fitted_br = _fit_font_scale_for_panels(
            {"br": row_h - 2*int(30*font_scale)}, {"br": [sec_fat]},
            col_w - 2*int(30*font_scale), font_scale
        )
        _draw_sections_block(draw, theme, br_x, br_y, col_w, row_h, [sec_fat], fitted_br)

    if total_items <= items_threshold_for_grid:
        _render_two_panel()
    else:
        try:
            _render_four_panel()
        except Exception:
            # ultimate safety: never fail; draw two-panel instead
            _render_two_panel()

    if card.logo_path and os.path.exists(card.logo_path):
        try:
            logo = Image.open(card.logo_path).convert("RGBA")
            target_w = int(280*font_scale)
            scale = target_w / max(1, logo.width)
            logo = logo.resize((int(logo.width*scale), int(logo.height*scale)), resample=Image.LANCZOS)
            img.paste(logo, (W - logo.width - pad, pad), logo)
        except Exception:
            pass

    img.save(output_path)
    return output_path

