from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.deps import DbSession
from app.db.models import User
from app.services.auth_service import AuthService

# auto_error=False: the default raises 403 on a missing Authorization
# header, and this API answers 401 for every auth failure.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthService(db).get_user_from_access_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
