from __future__ import annotations

from ..models import User
from ..data_layer.category_repository import category_repo
from ..schemas.categories import (
    CreateCategoryRequestSchema,
    UpdateCategoryRequestSchema,
)


class CategoryService:
    def create_category(
        self,
        current_user,
        payload: CreateCategoryRequestSchema,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        existing = category_repo.get_by_name_in_clinic(clinic_id, payload.name)
        if existing:
            return None, "category with this name already exists in this clinic"

        category = category_repo.create_category(
            clinic_id=clinic_id,
            name=payload.name,
            is_pinned=payload.is_pinned,
        )
        return category, None

    def list_categories(self, current_user):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return [], "user has no clinic assigned"

        items = category_repo.list_for_clinic(clinic_id)
        return items, None

    def update_category(
        self,
        current_user,
        category_id,
        payload: UpdateCategoryRequestSchema,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        category = category_repo.get_by_id_in_clinic(category_id, clinic_id)
        if not category:
            return None, "category not found in this clinic"

        if payload.name is not None:
            existing = category_repo.get_by_name_in_clinic(clinic_id, payload.name)
            if existing and existing.category_id != category.category_id:
                return None, "category with this name already exists in this clinic"

        updated = category_repo.update_category(
            category,
            name=payload.name,
            is_pinned=payload.is_pinned,
        )
        return updated, None


category_service = CategoryService()
