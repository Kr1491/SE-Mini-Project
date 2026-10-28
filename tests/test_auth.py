
import unittest
import sqlite3

from study_platform.auth import (
    AuthError,
    hash_password,
    verify_password,
    register_user,
    login_user,
)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT,
                role TEXT NOT NULL
                    CHECK(role IN ('student', 'instructor', 'administrator')),
                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK(is_active IN (0, 1))
            )
        """)

        self.user_data = {
            "name": "Test Student",
            "email": "student@example.com",
            "password": "StrongPassword123!",
            "role": "student",
        }

    def tearDown(self):
        self.db.close()

    def test_password_hash_is_not_plain_text(self):
        hashed = hash_password(self.user_data["password"])

        self.assertNotEqual(hashed, self.user_data["password"])
        self.assertTrue(verify_password(self.user_data["password"], hashed))
        self.assertFalse(verify_password("WrongPassword123!", hashed))

    def test_registration_stores_hashed_password(self):
        user = register_user(self.db, self.user_data)

        row = self.db.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            ("student@example.com",),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertNotEqual(row["password_hash"], self.user_data["password"])
        self.assertNotIn("password_hash", user)

    def test_duplicate_email_is_rejected(self):
        register_user(self.db, self.user_data)

        with self.assertRaises(AuthError):
            register_user(self.db, self.user_data)

    def test_login_with_correct_credentials(self):
        register_user(self.db, self.user_data)

        user = login_user(
            self.db,
            self.user_data["email"],
            self.user_data["password"],
        )

        self.assertEqual(user["email"], self.user_data["email"])
        self.assertNotIn("password_hash", user)

    def test_login_rejects_wrong_password(self):
        register_user(self.db, self.user_data)

        with self.assertRaises(AuthError) as context:
            login_user(
                self.db,
                self.user_data["email"],
                "IncorrectPassword123!",
            )

        self.assertEqual(context.exception.status, 401)

    def test_login_rejects_unknown_email(self):
        with self.assertRaises(AuthError) as context:
            login_user(
                self.db,
                "unknown@example.com",
                "StrongPassword123!",
            )

        self.assertEqual(context.exception.status, 401)

    def test_login_rejects_inactive_user(self):
        register_user(self.db, self.user_data)
        self.db.execute(
            "UPDATE users SET is_active = 0 WHERE email = ?",
            (self.user_data["email"],),
        )

        with self.assertRaises(AuthError) as context:
            login_user(
                self.db,
                self.user_data["email"],
                self.user_data["password"],
            )

        self.assertEqual(context.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
