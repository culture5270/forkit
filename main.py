import os
import random

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/nearby")
@limiter.limit("10/minute")
async def nearby_restaurants(request: Request, lat: float, lng: float, radius: int = 1500, exclude: str = "", types: str = ""):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://places-api.foursquare.com/places/search",
            headers={
                "Authorization": f"Bearer {FOURSQUARE_API_KEY}",
                "X-Places-Api-Version": "2025-06-17",
            },
            params={
                "ll": f"{lat},{lng}",
                "radius": radius,
                "categories": "13065",
                "limit": 50,
                "fields": "name,categories,location,website",
            },
        )
    response.raise_for_status()
    data = response.json()
    all_results = data.get("results", [])
    if types:
        # Cuisine filter is active — search all 50 results so non-food venues
        # (parks, theaters, bars) are checked but won't match cuisine keywords.
        type_keywords = [t.strip().lower() for t in types.split(",")]
        def matches_type(r):
            names = " ".join(c.get("short_name", "").lower() for c in r.get("categories", []))
            return any(kw in names for kw in type_keywords)
        results = [r for r in all_results if matches_type(r)]
    else:
        # No cuisine filter — use the icon path to exclude non-food venues.
        results = [
            r for r in all_results
            if any("/food/" in c.get("icon", {}).get("prefix", "") for c in r.get("categories", []))
        ]
    if not results:
        return {"pick": None, "restaurants": []}
    names = [r["name"] for r in results]
    candidates = [r for r in results if r["name"] != exclude] or results
    pick = random.choice(candidates)
    categories = " · ".join(c["short_name"] for c in pick.get("categories", []))
    address = pick.get("location", {}).get("formatted_address", "")
    website = pick.get("website", "")
    return {
        "pick": pick["name"],
        "description": {"categories": categories, "address": address, "website": website},
        "restaurants": names,
    }
