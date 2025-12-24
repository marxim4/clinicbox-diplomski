from enum import Enum


class PlanStatus(str, Enum):
    PLANNED = "PLANNED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"
