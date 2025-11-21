from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Integer,
    ForeignKey,
    Numeric,
    DateTime,
    Text,
    Enum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from ..enums import CashTransactionType, TransactionStatus


class CashTransaction(db.Model):
    __tablename__ = "cash_transaction"

    tx_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    cashbox_id: Mapped[int] = mapped_column(
        ForeignKey("cashbox.cashbox_id"),
        nullable=False,
    )

    type: Mapped[CashTransactionType] = mapped_column(
        Enum(CashTransactionType),
        nullable=False,
    )

    # Link to patient payment (for IN from patients) – optional
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment.payment_id"),
        nullable=True,
    )

    # Expense category (for OUT transactions) – optional
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.category_id"),
        nullable=True,
    )

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus),
        default=TransactionStatus.PENDING,
        nullable=False,
    )

    note: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=True,
    )


    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="cash_transactions")
    cashbox: Mapped["Cashbox"] = relationship("Cashbox", back_populates="transactions")
    payment: Mapped["Payment"] = relationship("Payment", back_populates="cash_transaction")
    category: Mapped["Category"] = relationship("Category", back_populates="transactions")

    created_by_user: Mapped["User"] = relationship(
        "User",
        back_populates="created_transactions",
        foreign_keys=[created_by],
    )
    approved_by_user: Mapped["User"] = relationship(
        "User",
        back_populates="approved_transactions",
        foreign_keys=[approved_by],
    )

    def __repr__(self) -> str:
        return f"<CashTransaction {self.tx_id} type={self.type} amount={self.amount}>"
