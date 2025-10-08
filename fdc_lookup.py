# fdc_lookup.py
import os, re, requests
from typing import Any, Dict, List, Optional, Tuple

FDC_API_BASE = "https://api.nal.usda.gov/fdc"

FALLBACK_WHOLE_FRUIT_GRAMS = {
    "apple": 182, "orange": 131, "banana": 118, "pear": 178, "peach": 150, "plum": 66
}
GENERIC_MEASURE_GRAMS = {"tsp": 4.2, "tbsp": 14.0, "cup": 240.0}

def _safe_get(d: Dict, *keys, default=None):
    x = d
    for k in keys:
        if not isinstance(x, dict) or k not in x: return default
        x = x[k]
    return x

def _get_cal_per_100g(food_details: Dict[str, Any]) -> Optional[float]:
    for n in food_details.get("foodNutrients", []):
        if _safe_get(n, "nutrient", "number") == "1008":
            amount = n.get("amount")
            unit = _safe_get(n, "nutrient", "unitName") or n.get("unitName")
            if amount is not None and unit and unit.lower().startswith("kcal"):
                return float(amount)
    ln = food_details.get("labelNutrients") or {}
    if "calories" in ln and "value" in ln["calories"]:
        return float(ln["calories"]["value"])
    return None

def _find_portion_matches(food_details: Dict[str, Any]) -> List[Tuple[str, float]]:
    portions = []
    for p in food_details.get("foodPortions", []) or []:
        gw = p.get("gramWeight")
        desc = p.get("portionDescription") or p.get("modifier") or ""
        mu = _safe_get(p, "measureUnit", "name") or ""
        parts = []
        if desc: parts.append(desc)
        if mu and mu.lower() not in desc.lower(): parts.append(mu)
        description = ", ".join([s for s in parts if s]).lower()
        if gw and description:
            portions.append((description, float(gw)))
    return portions

def _best_each_grams(name: str, portions: List[Tuple[str,float]]) -> Optional[float]:
    name_key = name.lower().strip()
    for needle in (r"^1 (fruit|medium|whole)\b", r"^1\b"):
        rx = re.compile(needle)
        for desc, grams in portions:
            if rx.search(desc): return grams
    for k,g in FALLBACK_WHOLE_FRUIT_GRAMS.items():
        if k in name_key: return float(g)
    return None

def _portion_for_measure(measure: str, portions: List[Tuple[str,float]]) -> Optional[float]:
    measure = measure.lower()
    for desc, grams in portions:
        if re.search(rf"^1\s*{measure}\b", desc): return grams
        if measure in desc: return grams
    return None

def _to_grams(name: str, amt: float, unit: str, portions: List[Tuple[str,float]]) -> Optional[float]:
    unit = (unit or "").strip().lower()
    if unit in ("g", "gram", "grams"): return float(amt)
    if unit in ("oz", "ounce", "ounces"): return float(amt) * 28.3495
    if unit in ("tsp", "teaspoon", "teaspoons"):
        grams = _portion_for_measure("teaspoon", portions) or GENERIC_MEASURE_GRAMS["tsp"]
        return float(amt) * grams
    if unit in ("tbsp", "tablespoon", "tablespoons"):
        grams = _portion_for_measure("tablespoon", portions) or GENERIC_MEASURE_GRAMS["tbsp"]
        return float(amt) * grams
    if unit in ("cup", "cups"):
        grams = _portion_for_measure("cup", portions) or GENERIC_MEASURE_GRAMS["cup"]
        return float(amt) * grams
    if unit in ("each", "piece", "fruit", "whole"):
        if not amt: amt = 1.0
        one_g = _best_each_grams(name, portions)
        if one_g: return float(amt) * one_g
    if unit in ("half", "1/2"):
        if not amt: amt = 0.5
        one_g = _best_each_grams(name, portions)
        if one_g: return float(amt) * one_g
    return None

def fdc_lookup_kcal(food_name: str, amt: float, unit: str, api_key: str) -> Optional[float]:
    if not api_key or not (food_name or "").strip(): return None
    params = {
        "api_key": api_key, "query": food_name, "pageSize": 10,
        "dataType": "Foundation,SR Legacy,Survey (FNDDS),Branded",
    }
    r = requests.get(f"{FDC_API_BASE}/v1/foods/search", params=params, timeout=12)
    if r.status_code != 200: return None
    foods = (r.json() or {}).get("foods") or []
    if not foods: return None
    fdc_id = foods[0]["fdcId"]
    rd = requests.get(f"{FDC_API_BASE}/v1/food/{fdc_id}", params={"api_key": api_key}, timeout=12)
    if rd.status_code != 200: return None
    detail = rd.json()
    cal100 = _get_cal_per_100g(detail)
    if not cal100: return None
    portions = _find_portion_matches(detail)
    grams = _to_grams(food_name, float(amt or 0.0), unit, portions)
    if grams is None:
        grams = float(amt or 0.0)  # last resort: treat as grams
    return float(cal100) * (grams / 100.0)

