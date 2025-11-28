from sqlalchemy import Integer, String, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Patient(db.Model):
    __tablename__ = "patient"
    __table_args__ = (
        UniqueConstraint("clinic_id", "email", name="uq_patient_clinic_email"),
    )

    patient_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text)

    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )

    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="patients")
    doctor: Mapped["User"] = relationship("User", back_populates="patients")

    installment_plans: Mapped[List["InstallmentPlan"]] = relationship(
        "InstallmentPlan",
        back_populates="patient",
        cascade="all, delete-orphan",
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="patient",
    )

    def __repr__(self):
        return f"<Patient {self.patient_id} {self.first_name} {self.last_name}>"
