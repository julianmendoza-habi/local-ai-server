import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import current_user
from app.auth.hashing import hash_password, verify_password
from app.auth.jwt_utils import create_token
from app.config import settings
from app.db import get_pool
from app.models import LoginRequest, RegisterRequest, TokenResponse, TokenUser, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def _can_register(email: str, pool: asyncpg.Pool) -> bool:
    """Admin emails bypass the allowlist; everyone else must be pre-approved."""
    if settings.is_admin_email(email):
        return True
    row = await pool.fetchrow("SELECT 1 FROM allowed_emails WHERE email = $1", email.lower())
    return row is not None


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, pool: asyncpg.Pool = Depends(get_pool)) -> TokenResponse:
    email = body.email.lower().strip()

    if not await _can_register(email, pool):
        raise HTTPException(status_code=403, detail="This email is not authorized to register")

    existing = await pool.fetchrow("SELECT id FROM users WHERE email = $1", email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user_id = uuid.uuid4()
    is_admin = settings.is_admin_email(email)
    pw_hash, pw_salt = hash_password(body.password)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO users (id, email, display_name, is_admin)
                VALUES ($1, $2, $3, $4)
                """,
                user_id,
                email,
                body.display_name,
                is_admin,
            )
            await conn.execute(
                """
                INSERT INTO user_identities (user_id, provider, password_hash, password_salt)
                VALUES ($1, 'local', $2, $3)
                """,
                user_id,
                pw_hash,
                pw_salt,
            )

    return TokenResponse(access_token=create_token(user_id, email, is_admin))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, pool: asyncpg.Pool = Depends(get_pool)) -> TokenResponse:
    email = body.email.lower().strip()

    row = await pool.fetchrow(
        """
        SELECT u.id, u.email, u.is_admin, ui.password_hash
        FROM users u
        JOIN user_identities ui ON ui.user_id = u.id AND ui.provider = 'local'
        WHERE u.email = $1
        """,
        email,
    )

    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await pool.execute(
        "UPDATE users SET last_login_at = NOW() WHERE id = $1",
        row["id"],
    )

    return TokenResponse(access_token=create_token(row["id"], row["email"], row["is_admin"]))


@router.get("/me", response_model=UserOut)
async def me(
    user: TokenUser = Depends(current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> UserOut:
    row = await pool.fetchrow(
        "SELECT id, email, display_name, is_admin, created_at, last_login_at FROM users WHERE id = $1",
        uuid.UUID(user.id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(
        id=str(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
        is_admin=row["is_admin"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )
