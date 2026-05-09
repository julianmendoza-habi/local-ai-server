import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_admin
from app.db import get_pool
from app.models import AllowedEmailIn, AllowedEmailOut, TokenUser, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/allowed-emails", response_model=list[AllowedEmailOut])
async def list_allowed_emails(
    _: TokenUser = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[AllowedEmailOut]:
    rows = await pool.fetch("SELECT email, note, added_at FROM allowed_emails ORDER BY added_at DESC")
    return [AllowedEmailOut(email=r["email"], note=r["note"], added_at=r["added_at"]) for r in rows]


@router.post("/allowed-emails", response_model=AllowedEmailOut, status_code=201)
async def add_allowed_email(
    body: AllowedEmailIn,
    _: TokenUser = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
) -> AllowedEmailOut:
    email = body.email.lower().strip()
    try:
        row = await pool.fetchrow(
            "INSERT INTO allowed_emails (email, note) VALUES ($1, $2) RETURNING email, note, added_at",
            email,
            body.note,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already in allowlist")
    return AllowedEmailOut(email=row["email"], note=row["note"], added_at=row["added_at"])


@router.delete("/allowed-emails/{email}", status_code=204)
async def remove_allowed_email(
    email: str,
    _: TokenUser = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    result = await pool.execute("DELETE FROM allowed_emails WHERE email = $1", email.lower())
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Email not found in allowlist")


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: TokenUser = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[UserOut]:
    rows = await pool.fetch(
        "SELECT id, email, display_name, is_admin, created_at, last_login_at FROM users ORDER BY created_at DESC"
    )
    return [
        UserOut(
            id=str(r["id"]),
            email=r["email"],
            display_name=r["display_name"],
            is_admin=r["is_admin"],
            created_at=r["created_at"],
            last_login_at=r["last_login_at"],
        )
        for r in rows
    ]


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    admin: TokenUser = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid user_id format")
    result = await pool.execute("DELETE FROM users WHERE id = $1", uid)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="User not found")
