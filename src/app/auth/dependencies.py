import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt_utils import decode_token
from app.models import TokenUser

_bearer = HTTPBearer()


async def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> TokenUser:
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return TokenUser(id=payload["sub"], email=payload["email"], is_admin=payload["is_admin"])


async def require_admin(user: TokenUser = Depends(current_user)) -> TokenUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
