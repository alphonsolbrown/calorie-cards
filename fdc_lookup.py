# fdc_lookup.py — robust USDA lookups (manual retries, no urllib3 import)
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import logging, time, random
import requests

log = logging.getLogger(__name__)

FDC_SEARCH_URL  = "https://api.nal.usda.gov/fdc/v1/foods/search"
FDC_DETAILS_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdcId}"

# --- behavior knobs ---
HTTP_TIMEOUT_S = 45
HTTP_RETRIES   = 3
BACKOFF_FACTOR = 0.6
JITTER_RANGE   = (0.05, 0.25)
ROUND_TO_KCAL  = 5  # set to None to disable rounding

FALLBACK_GRAMS = {
    "each": {"egg": 50, "eggs": 50, "apple": 182, "banana": 118, "orange": 131, "pear": 178, "peach": 150},
    "tbsp": 14.2, "tsp": 4.2, "cup": 240.0, "oz": 28.349523125, "g": 1.0,
}

_last_error: Dict[str, Any] = {}
def last_error() -> Dict[str, Any]: return _last_error.copy()
def _set_err(stage: str, **kw):
    _last_error.clear()
    _last_error.update({"stage": stage, **kw})

def _round_kcal(v: float) -> float:
    if not ROUND_TO_KCAL:
        return round(v, 0)
    step = float(ROUND_TO_KCAL)
    return float(int(round(v / step)) * ROUND_TO_KCAL)

# ----------------------- HTTP helpers (manual retries) -----------------------
def _sleep_backoff(n: int):
    time.sleep(BACKOFF_FACTOR * (2 ** n) + random.uniform(*JITTER_RANGE))

def _http_json(url: str, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
    for attempt in range(HTTP_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=HTTP_TIMEOUT_S)
            if r.status_code != 200:
                # return body as json or text for diagnostics
                try:
                    return None, r.status_code, r.json()
                except Exception:
                    return None, r.status_code, r.text
            return r.json(), r.status_code, None
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as e:
            if attempt < HTTP_RETRIES:
                _sleep_backoff(attempt)
                continue
            return None, None, f"{type(e).__name__}: {e!s}"
        except Exception as e:
            if attempt < HTTP_RETRIES:
                _sleep_backoff(attempt)
                continue
            return None, None, repr(e)

# ----------------------- search + ranking -----------------------
def _datatype_rank(dt: str) -> int:
    return {"Survey (FNDDS)": 0, "SR Legacy": 1, "Foundation": 2, "Branded": 3}.get(dt, 99)

def _best_food(foods: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    want_dried = "dried" in (query or "").lower()
    def key(f: Dict[str, Any]):
        desc = (f.get("description") or "").lower()
        dried_penalty = 0 if (want_dried == ("dried" in desc)) else 1
        return (_datatype_rank(f.get("dataType", "")), dried_penalty, -float(f.get("score", 0.0)))
    return sorted(foods, key=key)[0] if foods else None

def _simplify_query(q: str) -> str:
    q = (q or "").lower()
    cut = {"grilled","baked","roasted","skinless","boneless","cooked","raw","chopped"}
    words = [w for w in q.split() if w not in cut]
    return " ".join(words) if words else q

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
            # last try: simplified query
            simp = _simplify_query(query)
            if simp != query:
                params = {"api_key": api_key, "query": simp, "pageSize": 25}
                data3, status3, err3 = _http_json(FDC_SEARCH_URL, params)
                if data3 is None:
                    _set_err("search", status=status3, error=err3, params=params)
                    return None
                foods = (data3 or {}).get("foods") or []
                if foods:
                    return _best_food(foods, simp)
            _set_err("search_empty", status=200, error="no foods", params={"query": query})
            return None
    return _best_food(foods, query)

# ----------------------- calorie parsing -----------------------
def _nutrient_kcal_per100g(food: Dict[str, Any]) -> Optional[float]:
    for n in food.get("foodNutrients") or []:
        nutrient = n.get("nutrient") or {}
        num = nutrient.get("number") or n.get("nutrientNumber")
        name = (nutrient.get("name") or "").lower()
        val = n.get("amount")
        if isinstance(val, (int, float)) and (str(num) == "1008" or "energy" in name or "kcal" in name):
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
    if isinstance(size, (int, float)) and unit in ("g","gram","grams"):
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
    if unit in ("g","oz"):
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
        return float(amt) * 50.0
    if unit in ("tbsp","tsp","cup"):
        return float(amt) * float(FALLBACK_GRAMS[unit])
    return None

# ----------------------- public API -----------------------
def fdc_lookup_kcal(name: str, amt: float, unit: str, *, api_key: str) -> Optional[float]:
    if not name or not api_key:
        _set_err("input", error="missing name or api_key", name=name, has_key=bool(api_key))
        return None

    food = _search_food(name, api_key)
    if not food: return None

    data, status, err = _http_json(FDC_DETAILS_URL.format(fdcId=food.get("fdcId")), {"api_key": api_key})
    if data is None:
        _set_err("details", status=status, error=err, fdc_id=food.get("fdcId"))
        return None

    cal_per_g = _calories_per_gram(data)
    grams_req = _grams_for_request(data, unit, float(amt or 0.0), name)

    if cal_per_g is not None and grams_req is not None:
        total = _round_kcal(cal_per_g * grams_req)
        log.info("FDC OK: %r x %s %s => %s kcal (per_g=%.4f, grams=%.2f, fdcId=%s)",
                 name, amt, unit, total, cal_per_g, grams_req, food.get("fdcId"))
        _set_err("ok", fdc_id=food.get("fdcId"), total=total)
        return total

    label_cals = _label_calories(data)
    unit_lower = (unit or "").lower().strip()
    if isinstance(label_cals, (int, float)) and unit_lower in {"serving","servings"}:
        total = _round_kcal(float(amt) * float(label_cals))
        _set_err("ok_fallback_label", fdc_id=food.get("fdcId"), total=total)
        return total

    if cal_per_g is None:
        _set_err("parse", error="no per-gram calories", fdc_id=food.get("fdcId"))
    elif grams_req is None:
        _set_err("parse", error=f"no gram match for unit={unit}", fdc_id=food.get("fdcId"))
    return None

