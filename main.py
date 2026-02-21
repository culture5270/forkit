import os
import random

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from foods import foods

load_dotenv()

FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/random")
async def random_food():
    return {"food": random.choice(foods)}


@app.get("/api/nearby")
async def nearby_restaurants(lat: float, lng: float, radius: int = 1500, exclude: str = ""):
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
    data = response.json()
    all_results = data.get("results", [])
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
