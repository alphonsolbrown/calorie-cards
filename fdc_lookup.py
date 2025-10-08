# fdc_lookup.py
# Robust USDA FDC lookup helpers for Streamlit calorie calculator.

from __future__ import annotations
from typing import Optional, Dict, Any
import requests

FDC_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
FDC_DETAILS_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdcId}"

FALLBACK_GRAMS = {
    "each": {
        "egg": 50, "eggs": 50,
        "apple": 182, "banana": 118, "orange": 131,
        "pear": 178, "peach": 150,
    },
    "tbsp": 14.2, "tsp": 4.2, "cup": 240.0,
    "oz": 28.3495, "g": 1.0,
}

def _first_or_none(xs): return xs[0] if xs else None

def _extract_kcal_from_food(food: Dict[str, Any]) -> Optional[float]:
    label = food.get("labelNutrients") or {}
    if "calories" in label and label["calories"]:
        val = label["calories"].get("value")
        if isinstance(val, (int, float)):
            return float(val)
    for n in food.get("foodNutrients") or []:
        if str(n.get("nutrient", {}).get("number")) == "1008" or n.get("nutrientNumber") == "1008":
            val = n.get("amount")
            if isinstance(val, (int, float)):
                return float(val)
    return None

def _pick_measure_grams(food: Dict[str, Any], unit: str, amt: float, name: str) -> Optional[float]:
    if unit in ("g", "oz"):
        base = FALLBACK_GRAMS["g"] if unit == "g" else FALLBACK_GRAMS["oz"]
        return amt * base

    for p in food.get("foodPortions") or []:
        gram = p.get("gramWeight")
        desc = (p.get("portionDescription") or "").lower()
        unit_name = (p.get("measureUnit", {}) or {}).get("name", "").lower()
        if gram and (
            unit in desc or unit in unit_name or (unit == "each" and ("each" in desc or "piece" in desc))
        ):
            return float(amt) * float(gram)

    if unit == "each":
        lower = name.lower().strip()
        for key, g in FALLBACK_GRAMS["each"].items():
            if key in lower:
                return amt * g
        return amt * 50.0

    if unit in ("tbsp", "tsp", "cup"):
        return amt * float(FALLBACK_GRAMS[unit])
    return None

def _search_food(query: str, api_key: str) -> Optional[Dict[str, Any]]:
    params = {
        "api_key": api_key,
        "query": query,
        "pageSize": 5,
        "dataType": ["Branded", "Survey (FNDDS)", "SR Legacy", "Foundation"],
    }
    r = requests.get(FDC_SEARCH_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json() or {}
    foods = data.get("foods") or []
    return _first_or_none(foods)

def _get_food(fdc_id: int, api_key: str) -> Dict[str, Any]:
    r = requests.get(FDC_DETAILS_URL.format(fdcId=fdc_id), params={"api_key": api_key}, timeout=15)
    r.raise_for_status()
    return r.json()

def fdc_lookup_kcal(name: str, amt: float, unit: str, *, api_key: str) -> Optional[float]:
    if not name or not api_key:
        return None
    food = _search_food(name, api_key)
    if not food:
        return None
    food = _get_food(food.get("fdcId"), api_key)
    per100_kcal = _extract_kcal_from_food(food)
    grams = _pick_measure_grams(food, unit.lower(), float(amt or 0.0), name)
    if per100_kcal is None or grams is None:
        return None
    return (per100_kcal / 100.0) * grams

