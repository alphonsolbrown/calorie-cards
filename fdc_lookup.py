# fdc_lookup.py — USDA lookup with explicit HTTP diagnostics and robust fallbacks
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import logging
import requests

log = logging.getLogger(__name__)

FDC_SEARCH_URL  = "https://api.nal.usda.gov/fdc/v1/foods/search"
FDC_DETAILS_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdcId}"

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
    # Nutrient number 1008 (kcal). Can appear as nutrient.number or nutrientNumber.
    for n in food.get("foodNutrients") or []:
        num = (n.get("nutrient") or {}).get("number") or n.get("nutrientNumber")
        if str(num) == "1008":
            val = n.get("amount")
            if isinstance(val, (int, float)):
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

    for p in food.get("foodPortions") or []:
        gram = p.get("gramWeight")
        desc = (p.get("portionDescription") or "").lower()
        unit_name = (p.get("measureUnit", {}) or {}).get("name", "").lower()
        if isinstance(gram, (int, float)) and (
            unit in desc or unit in unit_name or (unit == "each" and ("each" in desc or "piece" in desc or "unit" in desc))
        ):
            return float(amt) * float(gram)

    if unit == "each":
        lower = (name or "").lower().strip()
        for key, g in FALLBACK_GRAMS["each"].items():
            if key in lower:
                return float(amt) * float(g)
        return float(amt) * 50.0  # generic each
    if unit in ("tbsp", "tsp", "cup"):
        return float(amt) * float(FALLBACK_GRAMS[unit])

    return None

# ----------------------- HTTP calls (with diagnostics) -----------------------
def _http_json(url: str, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
    try:
        r = requests.get(url, params=params, timeout=20)
        status = r.status_code
        if status != 200:
            # Try to capture USDA error structure if present
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
        # Retry without dataType filter (some queries only hit one source)
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
    Return total kcal for (name, amt, unit). If something fails, returns None
    and records details retrievable via last_error().
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

    if cal_per_g is None:
        _set_err("parse", error="no per-gram calories", fdc_id=food.get("fdcId"))
        return None
    if grams_req is None:
        _set_err("parse", error=f"no gram match for unit={unit}", fdc_id=food.get("fdcId"))
        return None

    total = round(cal_per_g * grams_req, 0)
    log.info("FDC OK: %r x %s %s => %s kcal (per_g=%.4f, grams=%.2f, fdcId=%s)",
             name, amt, unit, total, cal_per_g, grams_req, food.get("fdcId"))
    _set_err("ok", fdc_id=food.get("fdcId"), total=total)
    return total

