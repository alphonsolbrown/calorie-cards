# fdc_lookup.py
import requests

def grams_from(amount: float, unit: str) -> float | None:
    u = (unit or "").strip().lower()
    if u in ("g", "gram", "grams"):
        return amount
    if u == "kg":
        return amount * 1000
    if u in ("oz", "ounce", "ounces"):
        return amount * 28.3495
    if u in ("lb", "pound", "pounds"):
        return amount * 453.592
    if u in ("tsp", "teaspoon"):
        return amount * 4.5   # heuristic (oil ~4.5 g/tsp)
    if u in ("tbsp", "tablespoon"):
        return amount * 13.5
    if u in ("cup", "cups"):
        return amount * 240.0 # rough; grams preferred for accuracy
    return None

def fdc_lookup_kcal(query: str, amount: float, unit: str, api_key: str) -> int | None:
    """
    Estimate kcal for a food 'query' at the given amount+unit using USDA FoodData Central.
    """
    if not api_key or not query.strip():
        return None
    try:
        # 1) search
        r = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"api_key": api_key, "query": query, "pageSize": 1},
            timeout=10
        )
        r.raise_for_status()
        result = r.json()
        foods = result.get("foods") or []
        if not foods:
            return None
        fdc_id = foods[0]["fdcId"]

        # 2) detail
        r2 = requests.get(f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}",
                          params={"api_key": api_key},
                          timeout=10)
        r2.raise_for_status()
        food = r2.json()

        kcal_per_100g = None
        for n in food.get("foodNutrients", []):
            name = (n.get("nutrient", {}).get("name") or "").lower()
            if "energy" in name:
                amt = n.get("amount")
                if amt is not None:
                    kcal_per_100g = float(amt)   # commonly per 100 g
                    break
        if kcal_per_100g is None:
            return None

        grams = grams_from(amount, unit)
        if grams is None:
            return None

        kcal = grams * (kcal_per_100g / 100.0)
        return int(round(kcal))
    except Exception:
        return None

