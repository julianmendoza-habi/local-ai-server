import bcrypt


def hash_password(plain: str) -> tuple[str, str]:
    """Returns (password_hash, password_salt)."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain.encode(), salt)
    return hashed.decode(), salt.decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
