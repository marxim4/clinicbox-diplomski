from enum import Enum


class UserRole(str, Enum):
    OWNER = "OWNER"
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    ACCOUNTANT = "ACCOUNTANT"
