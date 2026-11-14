from fastapi import APIRouter, Depends, Request

from app.deps import require_role
from app.templating import templates

router = APIRouter()


@router.get("/admin")
def admin_home(request: Request, user=Depends(require_role("admin"))):
    return templates.TemplateResponse(request, "admin/dashboard.html", {})
