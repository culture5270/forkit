import os
import random

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import bcrypt
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from database import create_db_and_tables, engine, get_session
from models import Comment, Favorite, User

load_dotenv()

FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-production")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    if engine is None:
        return
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_username or not admin_password:
        return
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == admin_username)).first()
        if not existing:
            user = User(
                username=admin_username,
                password_hash=hash_password(admin_password),
            )
            session.add(user)
            session.commit()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = request.session.get("user_id")
    is_logged_in = user_id is not None
    username = request.session.get("username", "")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "is_logged_in": is_logged_in,
        "username": username,
    })


@app.get("/feedback", response_class=HTMLResponse)
async def feedback(request: Request):
    return templates.TemplateResponse("feedback.html", {"request": request})


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    session: Session = Depends(get_session),
):
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Passwords do not match"
        })
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Username already taken"
        })
    user = User(username=username[:100], password_hash=hash_password(password))
    session.add(user)
    session.commit()
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def user_login_get(request: Request):
    if request.session.get("user_id") is not None:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("user_login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def user_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    user = session.exec(select(User).where(User.username == username)).first()
    if user and verify_password(password, user.password_hash):
        request.session["user_id"] = user.id
        request.session["username"] = user.username
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("user_login.html", {
        "request": request, "error": "Invalid username or password"
    })


@app.get("/logout")
async def user_logout(request: Request):
    request.session.pop("user_id", None)
    request.session.pop("username", None)
    return RedirectResponse("/", status_code=302)


@app.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request, session: Session = Depends(get_session)):
    user_id = request.session.get("user_id")
    if user_id is None:
        return RedirectResponse("/login", status_code=302)
    favorites = session.exec(
        select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.saved_at.desc())
    ).all()
    return templates.TemplateResponse("favorites.html", {
        "request": request,
        "favorites": favorites,
        "username": request.session.get("username", ""),
    })


@app.get("/api/favorites")
async def get_favorites(request: Request, session: Session = Depends(get_session)):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    favorites = session.exec(
        select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.saved_at.desc())
    ).all()
    return [{"id": f.id, "name": f.name, "address": f.address, "categories": f.categories, "website": f.website} for f in favorites]


@app.post("/api/favorites")
async def save_favorite(request: Request, session: Session = Depends(get_session)):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    body = await request.json()
    name = (body.get("name") or "").strip()[:200]
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    existing = session.exec(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.name == name)
    ).first()
    if existing:
        return {"ok": True, "already_saved": True}
    fav = Favorite(
        user_id=user_id,
        name=name,
        address=(body.get("address") or "")[:500],
        categories=(body.get("categories") or "")[:200],
        website=(body.get("website") or "")[:500],
    )
    session.add(fav)
    session.commit()
    return {"ok": True}


@app.delete("/api/favorites/{name}")
async def delete_favorite(name: str, request: Request, session: Session = Depends(get_session)):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    fav = session.exec(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.name == name)
    ).first()
    if not fav:
        raise HTTPException(status_code=404)
    session.delete(fav)
    session.commit()
    return {"ok": True}


@app.get("/api/nearby")
@limiter.limit("10/minute")
async def nearby_restaurants(request: Request, lat: float, lng: float, radius: int = 1500, exclude: str = "", types: str = ""):
    type_keywords = [t.strip().lower() for t in types.split(",") if t.strip()] if types else []
    query = type_keywords[0] if len(type_keywords) == 1 else "restaurant"

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
                "query": query,
                "limit": 50,
                "fields": "name,categories,location,website,distance",
            },
        )
    response.raise_for_status()
    data = response.json()
    all_results = data.get("results", [])

    FOOD_KEYWORDS = {
        "restaurant", "food", "diner", "bistro", "kitchen", "grill", "café", "cafe",
        "bakery", "pizzeria", "sushi", "taco", "noodle", "ramen", "pho", "curry",
        "steakhouse", "eatery", "dining", "brasserie", "gastropub", "buffet",
        "burger", "pizza", "seafood", "sandwich", "deli", "wings", "bbq", "barbecue",
        "smokehouse", "rotisserie", "bowl", "fast food", "food truck", "dim sum",
        "japanese", "chinese", "italian", "mexican", "indian", "thai", "korean",
        "vietnamese", "mediterranean", "greek", "french", "american",
    }

    def cat_text(r):
        return " ".join(
            f"{c.get('name', '')} {c.get('short_name', '')}"
            for c in r.get("categories", [])
        ).lower()

    food_results = [r for r in all_results if any(kw in cat_text(r) for kw in FOOD_KEYWORDS)]

    if type_keywords:
        results = [r for r in food_results if any(kw in cat_text(r) or kw in r.get("name", "").lower() for kw in type_keywords)]
    else:
        results = food_results

    if not results:
        return {"pick": None, "restaurants": []}
    names = [r["name"] for r in results]
    exclude_set = {e.strip() for e in exclude.split(",") if e.strip()}
    candidates = [r for r in results if r["name"] not in exclude_set] or results
    pick = random.choice(candidates)
    categories = " · ".join(c["short_name"] for c in pick.get("categories", []))
    address = pick.get("location", {}).get("formatted_address", "")
    website = pick.get("website", "")
    distance_miles = round(pick.get("distance", 0) / 1609.34, 1)
    try:
        price = "$" * int(pick["price"]) if pick.get("price") else ""
    except (TypeError, ValueError):
        price = ""
    return {
        "pick": pick["name"],
        "description": {"categories": categories, "price": price, "address": address, "website": website, "distance_miles": distance_miles},
        "restaurants": names,
    }


@app.post("/api/comments")
@limiter.limit("5/minute")
async def post_comment(
    request: Request,
    name: str = Form(default="Anonymous"),
    message: str = Form(...),
    session: Session = Depends(get_session),
):
    if engine is None:
        return {"error": "Database not configured"}, 503
    name = name.strip() or "Anonymous"
    message = message.strip()
    if not message:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Message is required")
    comment = Comment(name=name[:100], message=message[:1000])
    session.add(comment)
    session.commit()
    return {"ok": True}


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/admin/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    user = session.exec(select(User).where(User.username == username)).first()
    if user and verify_password(password, user.password_hash):
        request.session["user"] = username
        return RedirectResponse("/admin/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})


@app.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, session: Session = Depends(get_session)):
    if not request.session.get("user"):
        return RedirectResponse("/admin/login", status_code=302)
    comments = session.exec(select(Comment).order_by(Comment.created_at.desc())).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "comments": comments})


@app.delete("/admin/comments/{comment_id}")
async def delete_comment(comment_id: int, request: Request, session: Session = Depends(get_session)):
    if not request.session.get("user"):
        from fastapi import HTTPException
        raise HTTPException(status_code=401)
    comment = session.get(Comment, comment_id)
    if not comment:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    session.delete(comment)
    session.commit()
    return {"ok": True}
