
"""Validation and password helpers for real user registration and login."""

import hashlib
import hmac
import secrets
import unicodedata
import sqlite3

PASSWORD_ITERATIONS = 600_000


class AuthError(Exception):
    """An expected authentication or registration error."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def validate_registration(data):
    """Validate registration input and return normalized account fields."""
    if not isinstance(data, dict):
        raise AuthError(400, "Provide registration details.")

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "student")

    if not all(isinstance(value, str) for value in (name, email, password, role)):
        raise AuthError(400, "All registration fields must be valid text.")

    name = unicodedata.normalize("NFC", name).strip()
    email = email.strip().lower()

    if not name or len(name) > 80:
        raise AuthError(400, "Name must contain between 1 and 80 characters.")

    if any(unicodedata.category(char).startswith("C") for char in name):
        raise AuthError(400, "Name contains unsupported characters.")

    if len(email) > 254 or not email or email.count("@") != 1:
        raise AuthError(400, "Enter a valid email address.")

    local, separator, domain = email.partition("@")
    if (
        not separator
        or not local
        or len(local) > 64
        or not domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or ".." in email
        or any(char.isspace() for char in email)
    ):
        raise AuthError(400, "Enter a valid email address.")

    if len(password) < 12 or len(password) > 128:
        raise AuthError(400, "Password must contain between 12 and 128 characters.")

    if role != "student":
        raise AuthError(400, "Public registration is only available for student accounts.")

    return {"name": name, "email": email, "password": password, "role": "student"}


def hash_password(password):
    """Hash a password using PBKDF2-HMAC-SHA256 and a random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored_hash):
    """Verify a password against a stored password hash."""
    try:
        algorithm, iterations_text, salt_hex, digest_hex = stored_hash.split("$")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)

        if (
            algorithm != "pbkdf2_sha256"
            or iterations < 1
            or iterations > PASSWORD_ITERATIONS
            or len(salt) != 16
            or len(expected) != 32
        ):
            return False

        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except (AttributeError, ValueError, TypeError):
        return False

def register_user(db, data):
    """Create a student account and return safe public account details."""
    account = validate_registration(data)
    password_hash = hash_password(account["password"])

    try:
        cursor = db.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (
                account["name"],
                account["email"],
                password_hash,
                account["role"],
            ),
        )
    except sqlite3.IntegrityError:
        existing = db.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (account["email"],),
        ).fetchone()

        if existing:
            raise AuthError(409, "An account with this email already exists.")

        raise

    return {
        "id": cursor.lastrowid,
        "name": account["name"],
        "email": account["email"],
        "role": account["role"],
    }


# Run an equivalent password check for unknown accounts; never use this as an account.
_DUMMY_PASSWORD_HASH = 'pbkdf2_sha256$600000$a4f183de039e41d9886b17c273ecb55a$95c17fe41e96ac8e1a26176b999145817c70325258e685a24f3daddaf484fcb3'


def login_user(db, email, password):
    """Verify an existing account and lock its checked state until session commit."""
    if not isinstance(email, str) or not isinstance(password, str):
        raise AuthError(400, 'Enter your email and password.')
    email = email.strip().lower()
    if not email or len(email) > 254 or not password or len(password) > 128:
        raise AuthError(400, 'Enter a valid email and password.')
    try:
        email.encode('utf-8'); password.encode('utf-8')
    except UnicodeError:
        raise AuthError(400, 'Enter a valid email and password.')
    user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    stored_hash = user['password_hash'] if user and user['password_hash'] else _DUMMY_PASSWORD_HASH
    valid = verify_password(password, stored_hash)
    if not user or not valid or not user['is_active']:
        raise AuthError(401, 'Invalid email or password.')
    # Recheck after password verification so a concurrent password/status change
    # cannot issue a session using credentials that have just been replaced.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    current = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
    if not current or not current['is_active'] or current['password_hash'] != stored_hash:
        raise AuthError(401, 'Invalid email or password.')
    return {key: current[key] for key in ('id', 'name', 'email', 'role')}
