# fdc_lookup.py — USDA lookup with stable per-gram calories and better search ranking
from __future__ import annotations
from typing import Optional, Dict, Any, List
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


# ---------- helpers for ranking ----------
def _datatype_rank(dt: str) -> int:
    """Lower is better: prefer generic USDA sources over branded."""
    order = {
        "Survey (FNDDS)": 0,
        "SR Legacy": 1,
        "Foundation": 2,
        "Branded": 3,
    }
    return order.get(dt, 99)


def _best_food(foods: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    """
    Pick the most appropriate food:
    - Prefer non-branded USDA types (FNDDS → SR → Foundation → Branded)
    - Then by score descending when present.
    - Light heuristic: if query doesn't mention 'dried', prefer descriptions without 'dried'.
    """
    q = (query or "").lower()
    want_dried = "dried" in q

    def sort_key(f: Dict[str, Any]):
        desc = (f.get("description") or "").lower()
        dried_penalty = 0 if (want_dried == ("dried" in desc)) else 1
        return (_datatype_rank(f.get("dataType", "")), dried_penalty, -float(f.get("score", 0.0)))

    return sorted(foods, key=sort_key)[0] if foods else None


# ---------- calorie extraction ----------
def _nutrient_kcal_per100g(food: Dict[str, Any]) -> Optional[float]:
    """Energy (kcal) per 100 g from nutrient table. Nutrient number 1008."""
    for n in food.get("foodNutrients") or []:
        num = (n.get("nutrient") or {}).get("number") or n.get("nutrientNumber")
        if str(num) == "1008":
            val = n.get("amount")
            if isinstance(val, (int, float)):
                return float(val)
    return None


def _label_calories(food: Dict[str, Any]) -> Optional[float]:
    """Calories from Nutrition Facts label (per serving)."""
    lab = food.get("labelNutrients") or {}
    if isinstance(lab, dict):
        val = (lab.get("calories") or {}).get("value")
        if isinstance(val, (int, float)):
            return float(val)
    return None


def _serving_size_grams(food: Dict[str, Any]) -> Optional[float]:
    """Serving size in grams (explicit unit preferred, else first portion gramWeight)."""
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
    Return kcal per gram.
    Policy: prefer USDA nutrient table (per 100 g) for stability;
    fall back to label calories divided by serving-size grams.
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


# ---------- portion grams for request ----------
def _grams_for_request(food: Dict[str, Any], unit: str, amt: float, name: str) -> Optional[float]:
    unit = (unit or "").lower().strip()
    if unit in ("g", "oz"):
        return float(amt) * (1.0 if unit == "g" else FALLBACK_GRAMS["oz"])

    # Try USDA portions matching the requested household measure
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

    return None


# ---------- search & fetch ----------
def _search_food(query: str, api_key: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(
            FDC_SEARCH_URL,
            params={
                "api_key": api_key,
                "query": query,
                "pageSize": 25,  # fetch more and rank
                "dataType": ["Survey (FNDDS)", "SR Legacy", "Foundation", "Branded"],
            },
            timeout=20,
        )
        r.raise_for_status()
        foods = (r.json() or {}).get("foods") or []
        return _best_food(foods, query)
    except Exception as e:
        log.warning("FDC search failed: %s", e)
        return None


def _get_food(fdc_id: int, api_key: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(FDC_DETAILS_URL.format(fdcId=fdc_id), params={"api_key": api_key}, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("FDC details failed for %s: %s", fdc_id, e)
        return None


# ---------- public API ----------
def fdc_lookup_kcal(name: str, amt: float, unit: str, *, api_key: str) -> Optional[float]:
    """
    Return total kcal for (name, amt, unit).
    - Prefers generic USDA entries (FNDDS/SR/Foundation) over Branded.
    - Uses nutrient table kcal/100g when available.
    - Multiplies by computed grams for the requested portion.
    """
    if not name or not api_key:
        log.info("fdc_lookup_kcal: missing name/api_key")
        return None

    food = _search_food(name, api_key)
    if not food:
        log.info("fdc_lookup_kcal: no food found for query=%r", name)
        return None

    detail = _get_food(food.get("fdcId"), api_key)
    if not detail:
        log.info("fdc_lookup_kcal: no details for fdcId=%r",food.get("fdcId"))
        return None

    cal_per_g = _calories_per_gram(detail)
    grams_req = _grams_for_request(detail, unit, float(amt or 0.0), name)
    if cal_per_g is None or grams_req is None:
        return None

    return round(cal_per_g * grams_req, 0)

