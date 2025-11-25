# Password must be at least 8 characters,
# contain at least one uppercase, one digit, and one special character.
PASSWORD_REGEX = r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]).{8,}$"