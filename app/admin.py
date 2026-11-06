"""Admin dashboard: sidebar, kasus (infinite scroll), CRUD item."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.items_store import items_store
from app.memory import memory

router = APIRouter(prefix="/admin", tags=["admin"])
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
PER_PAGE = 24


def _logged_in(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _check_password(username: str, password: str) -> bool:
    user_ok = hmac.compare_digest(username, config.ADMIN_USERNAME)
    pass_ok = hmac.compare_digest(password, config.ADMIN_PASSWORD)
    return user_ok and pass_ok


def _all_items() -> dict[str, str]:
    return items_store.category_map()


def _shell_ctx(active: str, **extra):
    return {"active": active, **extra}


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
    return TEMPLATES.TemplateResponse(request, "login.html", {"error": error})


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


def _parse_case_filters(
    category: str | None,
    corrected: str | None,
    item: str | None,
):
    corrected_filter: bool | None = None
    if corrected == "1":
        corrected_filter = True
    elif corrected == "0":
        corrected_filter = False
    cat = category if category in ("organic", "anorganic", "other") else None
    catalog = _all_items()
    item_filter = item if item in catalog else None
    return cat, corrected_filter, item_filter, catalog


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

    cat, corrected_filter, item_filter, catalog = _parse_case_filters(category, corrected, item)
    error = request.query_params.get("err")
    message = request.query_params.get("ok")

    try:
        rows, total = memory.list_cases(
            limit=PER_PAGE,
            offset=(page - 1) * PER_PAGE,
            category=cat,
            corrected=corrected_filter,
            item=item_filter,
        )
        stats = memory.stats()
    except Exception as exc:  # noqa: BLE001
        return TEMPLATES.TemplateResponse(
            request,
            "cases.html",
            _shell_ctx(
                "cases",
                cases=[],
                total=0,
                page=1,
                has_more=False,
                stats={"enabled": False, "error": str(exc)},
                category=cat or "",
                corrected=corrected or "",
                item=item_filter or "",
                all_items=catalog,
                message=None,
                error=f"Gagal membaca vector store: {exc}",
            ),
        )

    has_more = page * PER_PAGE < total
    return TEMPLATES.TemplateResponse(
        request,
        "cases.html",
        _shell_ctx(
            "cases",
            cases=rows,
            total=total,
            page=page,
            has_more=has_more,
            stats=stats,
            category=cat or "",
            corrected=corrected or "",
            item=item_filter or "",
            all_items=catalog,
            message=message,
            error=error,
        ),
    )


@router.get("/cases/fragment", response_class=HTMLResponse)
async def cases_fragment(
    request: Request,
    category: str | None = Query(None),
    corrected: str | None = Query(None),
    item: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    if not _logged_in(request):
        raise HTTPException(status_code=401, detail="Login dulu")

    cat, corrected_filter, item_filter, catalog = _parse_case_filters(category, corrected, item)
    rows, total = memory.list_cases(
        limit=PER_PAGE,
        offset=(page - 1) * PER_PAGE,
        category=cat,
        corrected=corrected_filter,
        item=item_filter,
    )
    has_more = page * PER_PAGE < total
    return TEMPLATES.TemplateResponse(
        request,
        "cases_cards.html",
        {
            "cases": rows,
            "all_items": catalog,
            "category": cat or "",
            "corrected": corrected or "",
            "page": page,
            "has_more": has_more,
            "total": total,
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
):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)

    qs: dict[str, str] = {}
    if category:
        qs["category"] = category
    if corrected:
        qs["corrected"] = corrected

    slug = item.lower().strip()
    if slug not in _all_items():
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


@router.get("/items", response_class=HTMLResponse)
async def items_page(
    request: Request,
    category: str | None = Query(None),
    edit: str | None = Query(None),
):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)

    cat = category if category in ("organic", "anorganic", "other") else None
    rows = items_store.list_rows(cat)
    edit_row = items_store.get(edit) if edit else None
    edit_slug = edit if edit_row else None
    return TEMPLATES.TemplateResponse(
        request,
        "items.html",
        _shell_ctx(
            "items",
            items=rows,
            category=cat or "",
            edit_slug=edit_slug,
            edit_row=edit_row,
            message=request.query_params.get("ok"),
            error=request.query_params.get("err"),
        ),
    )


@router.post("/items/create")
async def items_create(
    request: Request,
    slug: Annotated[str, Form()],
    category: Annotated[str, Form()],
    description: Annotated[str, Form()],
):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    try:
        row = items_store.create(slug, category, description)
        qs = {"ok": f"Item dibuat: {row['slug']}"}
    except Exception as exc:  # noqa: BLE001
        qs = {"err": str(exc)}
    return RedirectResponse(f"/admin/items?{urlencode(qs)}", status_code=303)


@router.post("/items/{slug}/update")
async def items_update(
    request: Request,
    slug: str,
    category: Annotated[str, Form()],
    description: Annotated[str, Form()],
):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    try:
        row = items_store.update(slug, category, description)
        qs = {"ok": f"Item diupdate: {row['slug']}"}
    except KeyError:
        qs = {"err": "Item tidak ditemukan"}
    except Exception as exc:  # noqa: BLE001
        qs = {"err": str(exc)}
    return RedirectResponse(f"/admin/items?{urlencode(qs)}", status_code=303)


@router.post("/items/{slug}/delete")
async def items_delete(request: Request, slug: str):
    if not _logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    try:
        items_store.delete(slug)
        qs = {"ok": f"Item dihapus: {slug}"}
    except KeyError:
        qs = {"err": "Item tidak ditemukan"}
    except Exception as exc:  # noqa: BLE001
        qs = {"err": str(exc)}
    return RedirectResponse(f"/admin/items?{urlencode(qs)}", status_code=303)
