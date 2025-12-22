# Password must be at least 8 characters,
# Updated to require Lowercase, Uppercase, Digit, Special, and min 8 chars
PASSWORD_REGEX = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]).{8,}$"

PIN_REGEX = r"^\d{4}$"