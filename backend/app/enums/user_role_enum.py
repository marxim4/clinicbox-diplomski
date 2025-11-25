from enum import Enum


class UserRole(str, Enum):
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    RECEPTION = "RECEPTION"
    ACCOUNTANT = "ACCOUNTANT"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"