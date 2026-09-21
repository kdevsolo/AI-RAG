from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.db.deps import DbSession
from app.schema.user import UserCreate, UserLoginRequest, UserRead
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


# dependency injection
def get_user_service(db: DbSession) -> UserService:
    return UserService(db)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


# routes
@router.get("/{user_id}", status_code=200, response_model=UserRead)
def get_user(user_id: str, service: UserServiceDep):
    user = service.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found!")
    return user


@router.post("/", status_code=201, response_model=UserRead)
def create_user(data: UserCreate, service: UserServiceDep):
    return service.create(data)


@router.post("/login", status_code=200, response_model=UserRead)
def login_user(data: UserLoginRequest, service: UserServiceDep):
    return service.login(data)
