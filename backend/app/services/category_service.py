from __future__ import annotations

from ..models import User
from ..data_layer.category_repository import category_repo
from ..schemas.categories import (
    CreateCategoryRequestSchema,
    UpdateCategoryRequestSchema,
)


class CategoryService:
    """
    Service for managing financial categories within a clinic.

    Categories provide a classification system for Cash Transactions (e.g., 'Office Supplies',
    'Consultation Fees'). This service handles the lifecycle of these categories,
    including creation, retrieval, and updates, while enforcing data integrity rules
    such as name uniqueness within a clinic scope.
    """

    def create_category(
            self,
            current_user: User,
            payload: CreateCategoryRequestSchema,
    ):
        """
        Creates a new transaction category.

        Enforces a uniqueness constraint to prevent duplicate category names
        within the same clinic to maintain data hygiene.
        """
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

    def list_categories(self, current_user: User):
        """
        Retrieves the list of categories available for the current user's clinic.
        """
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return [], "user has no clinic assigned"

        items = category_repo.list_for_clinic(clinic_id)
        return items, None

    def update_category(
            self,
            current_user: User,
            category_id: int,
            payload: UpdateCategoryRequestSchema,
    ):
        """
        Updates an existing category.

        Allows modification of the name and 'pinned' status (for UI prioritization).
        Includes a check to ensure that renaming a category does not cause a name
        collision with another existing category.
        """
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        category = category_repo.get_by_id_in_clinic(category_id, clinic_id)
        if not category:
            return None, "category not found in this clinic"

        if payload.name is not None:
            existing = category_repo.get_by_name_in_clinic(clinic_id, payload.name)
            # Ensure we aren't flagging the current category as its own duplicate
            if existing and existing.category_id != category.category_id:
                return None, "category with this name already exists in this clinic"

        updated = category_repo.update_category(
            category,
            name=payload.name,
            is_pinned=payload.is_pinned,
        )
        return updated, None


category_service = CategoryService()
