"""Admin dashboard: login, daftar kasus vector store, koreksi label."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.memory import memory
from app.prompts import ITEM_CATEGORY

router = APIRouter(prefix="/admin", tags=["admin"])
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ITEMS_BY_CATEGORY: dict[str, list[str]] = {"organic": [], "anorganic": [], "other": []}
for _item, _cat in ITEM_CATEGORY.items():
    ITEMS_BY_CATEGORY.setdefault(_cat, []).append(_item)


def _logged_in(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _check_password(username: str, password: str) -> bool:
    user_ok = hmac.compare_digest(username, config.ADMIN_USERNAME)
    pass_ok = hmac.compare_digest(password, config.ADMIN_PASSWORD)
    return user_ok and pass_ok


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    return RedirectResponse("/admin/cases", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    if _logged_in(request):
        return RedirectResponse("/admin/cases", status_code=303)
    return TEMPLATES.TemplateResponse(
        request,
        "login.html",
        {"error": error},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    if not _check_password(username.strip(), password):
        return TEMPLATES.TemplateResponse(
            request,
            "login.html",
            {"error": "Username atau password salah"},
            status_code=401,
        )
    request.session["admin"] = True
    request.session["admin_user"] = username.strip()
    return RedirectResponse("/admin/cases", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/cases", response_class=HTMLResponse)
async def cases_page(
    request: Request,
    category: str | None = Query(None),
    corrected: str | None = Query(None),
    item: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)

    per_page = 24
    corrected_filter: bool | None = None
    if corrected == "1":
        corrected_filter = True
    elif corrected == "0":
        corrected_filter = False

    cat = category if category in ("organic", "anorganic", "other") else None
    item_filter = item if item in ITEM_CATEGORY else None

    try:
        rows, total = memory.list_cases(
            limit=per_page,
            offset=(page - 1) * per_page,
            category=cat,
            corrected=corrected_filter,
            item=item_filter,
        )
        stats = memory.stats()
    except Exception as exc:  # noqa: BLE001
        return TEMPLATES.TemplateResponse(
            request,
            "cases.html",
            {
                "cases": [],
                "total": 0,
                "page": 1,
                "pages": 1,
                "stats": {"enabled": False, "error": str(exc)},
                "category": cat or "",
                "corrected": corrected or "",
                "item": item_filter or "",
                "items_by_category": ITEMS_BY_CATEGORY,
                "all_items": ITEM_CATEGORY,
                "message": None,
                "error": f"Gagal membaca vector store: {exc}",
            },
        )

    pages = max(1, (total + per_page - 1) // per_page)
    return TEMPLATES.TemplateResponse(
        request,
        "cases.html",
        {
            "cases": rows,
            "total": total,
            "page": page,
            "pages": pages,
            "stats": stats,
            "category": cat or "",
            "corrected": corrected or "",
            "item": item_filter or "",
            "items_by_category": ITEMS_BY_CATEGORY,
            "all_items": ITEM_CATEGORY,
            "message": request.query_params.get("ok"),
            "error": request.query_params.get("err"),
        },
    )


@router.get("/cases/{case_id}/image")
async def case_image(request: Request, case_id: str):
    if not _logged_in(request):
        raise HTTPException(status_code=401, detail="Login dulu")
    path = memory.image_path_for(case_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Gambar tidak ditemukan")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/cases/{case_id}/correct")
async def correct_case(
    request: Request,
    case_id: str,
    item: Annotated[str, Form()],
    category: str = Form(""),
    corrected: str = Form(""),
    page: int = Form(1),
):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)

    qs = {}
    if category:
        qs["category"] = category
    if corrected:
        qs["corrected"] = corrected
    if page > 1:
        qs["page"] = str(page)

    slug = item.lower().strip()
    if slug not in ITEM_CATEGORY:
        qs["err"] = "Item tidak dikenal"
        return RedirectResponse(f"/admin/cases?{urlencode(qs)}", status_code=303)

    try:
        memory.correct(case_id, slug)
        qs["ok"] = f"Koreksi tersimpan: {slug}"
    except KeyError:
        qs["err"] = "Kasus tidak ditemukan"
    except Exception as exc:  # noqa: BLE001
        qs["err"] = str(exc)

    return RedirectResponse(f"/admin/cases?{urlencode(qs)}", status_code=303)
