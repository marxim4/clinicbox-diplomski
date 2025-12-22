from enum import Enum


class UserRole(str, Enum):
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    RECEPTIONIST = "RECEPTIONIST"
    ACCOUNTANT = "ACCOUNTANT"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    OWNER = "OWNER"
