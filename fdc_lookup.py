# fdc_lookup.py — USDA lookup with robust fallbacks + 5-kcal rounding
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import logging
import requests

log = logging.getLogger(__name__)

FDC_SEARCH_URL  = "https://api.nal.usda.gov/fdc/v1/foods/search"
FDC_DETAILS_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdcId}"

# Auto-rounding granularity (kcal). Set to None to disable.
ROUND_TO_KCAL = 5

# Basic fallbacks for household measures if USDA portion matching fails
FALLBACK_GRAMS = {
    "each": {"egg": 50, "eggs": 50, "apple": 182, "banana": 118, "orange": 131, "pear": 178, "peach": 150},
    "tbsp": 14.2, "tsp": 4.2, "cup": 240.0, "oz": 28.349523125, "g": 1.0,
}

# ----------------------- small diagnostics helpers -----------------------
_last_error: Dict[str, Any] = {}

def last_error() -> Dict[str, Any]:
    """Expose last HTTP/parse error for the UI."""
    return _last_error.copy()

def _set_err(stage: str, **kw):
    _last_error.clear()
    _last_error.update({"stage": stage, **kw})

def _round_kcal(v: float) -> float:
    if not ROUND_TO_KCAL:
        return round(v, 0)
    step = float(ROUND_TO_KCAL)
    return float(int(round(v / step)) * ROUND_TO_KCAL)

# ----------------------- ranking & parsing helpers -----------------------
def _datatype_rank(dt: str) -> int:
    return {"Survey (FNDDS)": 0, "SR Legacy": 1, "Foundation": 2, "Branded": 3}.get(dt, 99)

def _best_food(foods: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").lower()
    want_dried = "dried" in q
    def sort_key(f: Dict[str, Any]):
        desc = (f.get("description") or "").lower()
        dried_penalty = 0 if (want_dried == ("dried" in desc)) else 1
        return (_datatype_rank(f.get("dataType", "")), dried_penalty, -float(f.get("score", 0.0)))
    return sorted(foods, key=sort_key)[0] if foods else None

def _nutrient_kcal_per100g(food: Dict[str, Any]) -> Optional[float]:
    """
    Return kcal per 100 g if possible.
    Handles both USDA nutrient.number == 1008 and nutrient.name == 'Energy'.
    """
    for n in food.get("foodNutrients") or []:
        nutrient = n.get("nutrient") or {}
        num = nutrient.get("number") or n.get("nutrientNumber")
        name = (nutrient.get("name") or "").lower()
        val = n.get("amount")
        if isinstance(val, (int, float)) and (
            str(num) == "1008" or "energy" in name or "kcal" in name
        ):
            return float(val)
    return None

def _label_calories(food: Dict[str, Any]) -> Optional[float]:
    lab = food.get("labelNutrients") or {}
    if isinstance(lab, dict):
        v = (lab.get("calories") or {}).get("value")
        if isinstance(v, (int, float)):
            return float(v)
    return None

def _serving_size_grams(food: Dict[str, Any]) -> Optional[float]:
    size = food.get("servingSize")
    unit = (food.get("servingSizeUnit") or "").lower()
    if isinstance(size, (int, float)) and unit in ("g", "gram", "grams"):
        return float(size)
    for p in food.get("foodPortions") or []:
        gw = p.get("gramWeight")
        if isinstance(gw, (int, float)) and gw > 0:
            return float(gw)
    return None

def _calories_per_gram(food: Dict[str, Any]) -> Optional[float]:
    """
    Try nutrient table (per 100 g), then label calories divided by serving size grams.
    """
    per100 = _nutrient_kcal_per100g(food)
    if isinstance(per100, (int, float)):
        return per100 / 100.0
    label = _label_calories(food)
    if isinstance(label, (int, float)):
        g = _serving_size_grams(food)
        if isinstance(g, (int, float)) and g > 0:
            return label / g
    return None

def _grams_for_request(food: Dict[str, Any], unit: str, amt: float, name: str) -> Optional[float]:
    unit = (unit or "g").lower().strip()
    if unit in ("g", "oz"):
        return float(amt) * (1.0 if unit == "g" else FALLBACK_GRAMS["oz"])

    # Try USDA portions that mention the requested measure
    for p in food.get("foodPortions") or []:
        gram = p.get("gramWeight")
        desc = (p.get("portionDescription") or "").lower()
        unit_name = (p.get("measureUnit", {}) or {}).get("name", "").lower()
        if isinstance(gram, (int, float)) and (
            unit in desc
            or unit in unit_name
            or (unit == "each" and ("each" in desc or "piece" in desc or "unit" in desc))
        ):
            return float(amt) * float(gram)

    # Heuristics if no portion found
    if unit == "each":
        lower = (name or "").lower().strip()
        for key, g in FALLBACK_GRAMS["each"].items():
            if key in lower:
                return float(amt) * float(g)
        return float(amt) * 50.0  # generic fallback
    if unit in ("tbsp", "tsp", "cup"):
        return float(amt) * float(FALLBACK_GRAMS[unit])

    # Treat empty/unknown units as grams if amt looks like grams (UI usually sends unit)
    return None

# ----------------------- HTTP calls (with diagnostics) -----------------------
def _http_json(url: str, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
    try:
        r = requests.get(url, params=params, timeout=20)
        status = r.status_code
        if status != 200:
            try:
                return None, status, r.json()
            except Exception:
                return None, status, r.text
        return r.json(), status, None
    except Exception as e:
        return None, None, repr(e)

def _search_food(query: str, api_key: str) -> Optional[Dict[str, Any]]:
    params = {"api_key": api_key, "query": query, "pageSize": 25,
              "dataType": ["Survey (FNDDS)", "SR Legacy", "Foundation", "Branded"]}
    data, status, err = _http_json(FDC_SEARCH_URL, params)
    if data is None:
        _set_err("search", status=status, error=err, params=params)
        return None
    foods = (data or {}).get("foods") or []
    if not foods:
        params.pop("dataType", None)
        data2, status2, err2 = _http_json(FDC_SEARCH_URL, params)
        if data2 is None:
            _set_err("search", status=status2, error=err2, params=params)
            return None
        foods = (data2 or {}).get("foods") or []
        if not foods:
            _set_err("search_empty", status=status2, error="no foods", params=params)
            return None
    return _best_food(foods, query)

def _get_food(fdc_id: int, api_key: str) -> Optional[Dict[str, Any]]:
    params = {"api_key": api_key}
    data, status, err = _http_json(FDC_DETAILS_URL.format(fdcId=fdc_id), params)
    if data is None:
        _set_err("details", status=status, error=err, fdc_id=fdc_id)
        return None
    return data

# ----------------------- public API -----------------------
def fdc_lookup_kcal(name: str, amt: float, unit: str, *, api_key: str) -> Optional[float]:
    """
    Return total kcal for (name, amt, unit). Never returns None if we can at least
    use a label-per-serving fallback.

    Priority:
      1) per-gram from nutrients/label ÷ grams * requested grams/oz/household
      2) if per-gram unavailable but label calories exist and unit is 'serving(s)',
         use amt * label_calories
    """
    if not name or not api_key:
        _set_err("input", error="missing name or api_key", name=name, has_key=bool(api_key))
        return None

    food = _search_food(name, api_key)
    if not food:
        return None

    detail = _get_food(food.get("fdcId"), api_key)
    if not detail:
        return None

    cal_per_g = _calories_per_gram(detail)
    grams_req = _grams_for_request(detail, unit, float(amt or 0.0), name)

    # Preferred path: per-gram available AND we can compute grams for the request
    if cal_per_g is not None and grams_req is not None:
        total = cal_per_g * grams_req
        total = _round_kcal(total)
        log.info("FDC OK: %r x %s %s => %s kcal (per_g=%.4f, grams=%.2f, fdcId=%s)",
                 name, amt, unit, total, cal_per_g, grams_req, food.get("fdcId"))
        _set_err("ok", fdc_id=food.get("fdcId"), total=total)
        return total

    # --- Fallback: label calories per serving ---
    label_cals = _label_calories(detail)
    unit_lower = (unit or "").lower().strip()
    if isinstance(label_cals, (int, float)) and unit_lower in {"serving", "servings"}:
        total = float(amt) * float(label_cals)
        total = _round_kcal(total)
        log.info("FDC OK (label fallback servings): %r x %s serving(s) => %s kcal (fdcId=%s)",
                 name, amt, total, food.get("fdcId"))
        _set_err("ok_fallback_label", fdc_id=food.get("fdcId"), total=total)
        return total

    # If we had label calories but no grams (and unit isn't servings), try once more:
    # if user typed grams/oz but grams_req is None, we already attempted; nothing more to do.
    if cal_per_g is None:
        _set_err("parse", error="no per-gram calories", fdc_id=food.get("fdcId"))
    elif grams_req is None:
        _set_err("parse", error=f"no gram match for unit={unit}", fdc_id=food.get("fdcId"))
    return None

