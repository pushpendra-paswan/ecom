from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db import get_db
from app.models.user import User
from app.schemas.category import CategoryListItemResponse, CategoryRequest, CategoryResponse
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryListItemResponse])
def list_categories(db: Session = Depends(get_db)):
    return category_service.list_categories(db)


@router.post("", response_model=CategoryResponse, status_code=201)
def create_category(
    request: CategoryRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return category_service.create_category(db, request)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    request: CategoryRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return category_service.update_category(db, category_id, request)


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    category_service.delete_category(db, category_id)
    return Response(status_code=204)
