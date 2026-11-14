from fastapi import APIRouter, Depends, Request

from app.deps import require_role
from app.templating import templates

router = APIRouter()


@router.get("/staff/scan")
def scanner_page(request: Request, user=Depends(require_role("staff", "admin"))):
    return templates.TemplateResponse(request, "staff/scan.html", {})
