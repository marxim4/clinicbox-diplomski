from __future__ import annotations

from sqlalchemy import select

from ..extensions import db
from ..models import Category


class CategoryRepository:
    def get_by_id_in_clinic(self, category_id, clinic_id):
        stmt = select(Category).where(
            Category.category_id == category_id,
            Category.clinic_id == clinic_id,
        )
        return db.session.scalar(stmt)

    def get_by_name_in_clinic(self, clinic_id, name):
        stmt = select(Category).where(
            Category.clinic_id == clinic_id,
            Category.name == name,
        )
        return db.session.scalar(stmt)

    def list_for_clinic(self, clinic_id):
        stmt = (
            select(Category)
            .where(Category.clinic_id == clinic_id)
            .order_by(
                Category.is_pinned.desc(),
                Category.name.asc(),
            )
        )
        return db.session.scalars(stmt).all()

    def create_category(self, clinic_id, name, is_pinned: bool = False):
        category = Category(
            clinic_id=clinic_id,
            name=name,
            is_pinned=is_pinned,
        )
        db.session.add(category)
        db.session.flush()
        return category

    def update_category(
            self,
            category,
            *,
            name: str | None = None,
            is_pinned: bool | None = None,
    ):
        if name is not None:
            category.name = name
        if is_pinned is not None:
            category.is_pinned = is_pinned
        db.session.flush()
        return category

    def increment_usage(self, category, dt):
        category.usage_count = (category.usage_count or 0) + 1
        category.last_used_at = dt
        db.session.flush()
        return category


category_repo = CategoryRepository()
