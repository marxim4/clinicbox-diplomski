"""
Application Constants.

Defines global constants and regular expressions used for validation across the system.
"""

# Regex enforces: At least 8 chars, 1 Lowercase, 1 Uppercase, 1 Digit, 1 Special character.
PASSWORD_REGEX = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]).{8,}$"

# Regex enforces: Exactly 4 digits.
PIN_REGEX = r"^\d{4}$"
