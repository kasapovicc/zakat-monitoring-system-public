"""
HTML template views for Zekat monitoring app
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.storage.config import ConfigStorage
from app.paths import get_resource_path

# Initialize router
router = APIRouter()

# Initialize templates
templates_dir = get_resource_path("app/templates")
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Dashboard page"""
    config_storage = ConfigStorage()
    configured = config_storage.config_exists()

    if not configured:
        # Redirect to setup if not configured
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "configured": False
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "configured": True,
    })


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, restart: bool = False):
    """Setup wizard page"""
    config_storage = ConfigStorage()
    configured = config_storage.config_exists()

    return templates.TemplateResponse("setup.html", {
        "request": request,
        "configured": configured,
        "restart_mode": restart
    })


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """Balance history page"""
    config_storage = ConfigStorage()
    if not config_storage.config_exists():
        # Redirect to setup
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "configured": False
        })

    return templates.TemplateResponse("history.html", {
        "request": request,
        "configured": True
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page"""
    config_storage = ConfigStorage()
    if not config_storage.config_exists():
        # Redirect to setup
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "configured": False
        })

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "configured": True
    })


@router.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    """Analysis page"""
    config_storage = ConfigStorage()
    if not config_storage.config_exists():
        # Redirect to setup
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "configured": False
        })

    return templates.TemplateResponse("analysis.html", {
        "request": request,
        "configured": True
    })
