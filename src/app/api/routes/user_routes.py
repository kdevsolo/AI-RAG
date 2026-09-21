from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import CurrentUser
from app.db.deps import DbSession
from app.schema.token import LoginResponse, RefreshRequest, TokenPair
from app.schema.user import UserCreate, UserLoginRequest, UserRead
from app.services.auth_service import AuthService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


# dependency injection
def get_user_service(db: DbSession) -> UserService:
    return UserService(db)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_auth_service(db: DbSession) -> AuthService:
    return AuthService(db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


# routes
# Declared before /{user_id}: FastAPI matches in order, so the dynamic
# route would otherwise swallow "me" and fail to parse it as an id.
@router.get("/me", status_code=200, response_model=UserRead)
def read_me(user: CurrentUser):
    return user


@router.get("/{user_id}", status_code=200, response_model=UserRead)
def get_user(user_id: str, service: UserServiceDep):
    user = service.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found!")
    return user


@router.post("/", status_code=201, response_model=UserRead)
def create_user(data: UserCreate, service: UserServiceDep):
    return service.create(data)


@router.post("/login", status_code=200, response_model=LoginResponse)
def login_user(data: UserLoginRequest, service: UserServiceDep):
    return service.login(data)


@router.post("/refresh", status_code=200, response_model=TokenPair)
def refresh_token(data: RefreshRequest, service: AuthServiceDep):
    return service.refresh(data.refresh_token)


@router.post("/logout", status_code=204, response_class=Response)
def logout(data: RefreshRequest, service: AuthServiceDep) -> None:
    service.revoke(data.refresh_token)
