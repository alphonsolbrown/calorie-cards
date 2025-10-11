# fdc_lookup.py — adds robust HTTP retries, longer timeouts, and query fallback
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import logging, random, time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

log = logging.getLogger(__name__)

FDC_SEARCH_URL  = "https://api.nal.usda.gov/fdc/v1/foods/search"
FDC_DETAILS_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdcId}"

# ---- tunables for flaky networks ----
HTTP_TIMEOUT_S = 45          # was 20 — USDA can be slow at times
HTTP_RETRIES   = 3           # retry count for GETs
BACKOFF_FACTOR = 0.6         # exponential backoff base (0.6, 1.2, 2.4s...) + jitter
JITTER_RANGE   = (0.05, 0.25)

# (keep your ROUND_TO_KCAL, FALLBACK_GRAMS, and all parsing helpers as-is)

# ----------------------- session with retries -----------------------
_session: Optional[requests.Session] = None

def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(
            total=HTTP_RETRIES,
            read=HTTP_RETRIES,
            connect=HTTP_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        s.headers.update({"Accept": "application/json"})
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session

# ----------------------- small diagnostics store -----------------------
_last_error: Dict[str, Any] = {}
def last_error() -> Dict[str, Any]: return _last_error.copy()
def _set_err(stage: str, **kw):
    _last_error.clear()
    _last_error.update({"stage": stage, **kw})

# ----------------------- HTTP with explicit diagnostics -----------------------
def _http_json(url: str, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
    s = _get_session()
    try:
        r = s.get(url, params=params, timeout=HTTP_TIMEOUT_S)
        status = r.status_code
        if status != 200:
            try:
                return None, status, r.json()
            except Exception:
                return None, status, r.text
        return r.json(), status, None
    except requests.exceptions.ReadTimeout as e:
        return None, None, f"ReadTimeout: {e!s}"
    except requests.exceptions.ConnectTimeout as e:
        return None, None, f"ConnectTimeout: {e!s}"
    except Exception as e:
        return None, None, repr(e)

def _sleep_backoff(n: int):
    # n = attempt index (0-based)
    base = (BACKOFF_FACTOR * (2 ** n))
    jitter = random.uniform(*JITTER_RANGE)
    time.sleep(base + jitter)

# ----------------------- search with resilient fallbacks -----------------------
def _search_food(query: str, api_key: str) -> Optional[Dict[str, Any]]:
    # 1) primary query with dataType filter
    params = {"api_key": api_key, "query": query, "pageSize": 25,
              "dataType": ["Survey (FNDDS)", "SR Legacy", "Foundation", "Branded"]}

    for attempt in range(HTTP_RETRIES + 1):
        data, status, err = _http_json(FDC_SEARCH_URL, params)
        if data is not None:
            foods = (data or {}).get("foods") or []
            if foods:
                return _best_food(foods, query)
            # empty: try without dataType filter once
            params.pop("dataType", None)
        else:
            # network/status problem — backoff and retry
            if attempt < HTTP_RETRIES:
                _sleep_backoff(attempt)
                continue
            _set_err("search", status=status, error=err, params=params)
            return None

    # 2) fallback: simplify the query (strip adjectives like 'grilled', 'raw', etc.)
    simplified = _simplify_query(query)
    if simplified != query:
        params = {"api_key": api_key, "query": simplified, "pageSize": 25}
        data2, status2, err2 = _http_json(FDC_SEARCH_URL, params)
        if data2 is None:
            _set_err("search", status=status2, error=err2, params=params)
            return None
        foods2 = (data2 or {}).get("foods") or []
        if foods2:
            return _best_food(foods2, simplified)

    _set_err("search_empty", status=200, error="no foods", params={"query": query})
    return None

def _simplify_query(q: str) -> str:
    q = (q or "").lower()
    # trim cooking adjectives; USDA often indexes base item better
    cut = ("grilled", "baked", "roasted", "boneless", "skinless", "cooked", "raw", "chopped")
    words = [w for w in q.split() if w not in cut]
    return " ".join(words) if words else q

# ----------------------- details call uses the same HTTP stack -----------------------
def _get_food(fdc_id: int, api_key: str) -> Optional[Dict[str, Any]]:
    params = {"api_key": api_key}
    for attempt in range(HTTP_RETRIES + 1):
        data, status, err = _http_json(FDC_DETAILS_URL.format(fdcId=fdc_id), params)
        if data is not None:
            return data
        if attempt < HTTP_RETRIES:
            _sleep_backoff(attempt)
        else:
            _set_err("details", status=status, error=err, fdc_id=fdc_id)
            return None

# (keep the rest of your file the same: parsing helpers, _round_kcal, fdc_lookup_kcal, etc.)

