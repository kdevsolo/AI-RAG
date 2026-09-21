from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import User
from app.schema.user import UserCreate, UserLoginRequest


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id) -> User | None:
        return self.db.get(User, user_id)

    def create(self, data: UserCreate) -> User:
        user = User(
            name=data.name,
            email=data.email,
            password=hash_password(data.password),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def login(self, data: UserLoginRequest) -> User:
        user = self.db.query(User).filter(User.email == data.email).first()
        if not user or not verify_password(data.password, user.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return user
