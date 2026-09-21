import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import config
from app.core.security import TokenError, create_token, decode_token, hash_token
from app.db.models import RefreshToken, User
from app.schema.token import TokenPair

# One generic message for every token failure: never reveal whether a token
# was unknown, expired, revoked, or simply the wrong type.
CREDENTIALS_ERROR = HTTPException(
    status_code=401,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def issue_pair(self, user: User) -> TokenPair:
        access_token, _, _ = create_token(
            str(user.id),
            "access",
            timedelta(minutes=config.access_token_expire_minutes),
        )
        refresh_token, _, refresh_expires_at = create_token(
            str(user.id),
            "refresh",
            timedelta(days=config.refresh_token_expire_days),
        )

        self.db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(refresh_token),
                expires_at=refresh_expires_at,
            )
        )
        self.db.commit()

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=config.access_token_expire_minutes * 60,
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(refresh_token, "refresh")
        except TokenError:
            raise CREDENTIALS_ERROR from None

        row = self._find(refresh_token)
        # A signature-valid token with no row was never issued here.
        if row is None or row.revoked_at is not None:
            raise CREDENTIALS_ERROR
        # Redundant with the JWT exp check, but the DB is the authority on
        # token state and the two must agree.
        if row.expires_at <= datetime.now(UTC):
            raise CREDENTIALS_ERROR

        user = self._load_user(payload.sub)

        # Rotation: the presented token is single-use and now spent.
        row.revoked_at = datetime.now(UTC)
        return self.issue_pair(user)

    def revoke(self, refresh_token: str) -> None:
        """Revoke a refresh token, silently when it is unknown.

        Idempotent by design, so logout cannot be used to probe which
        tokens exist.
        """
        row = self._find(refresh_token)
        if row is None or row.revoked_at is not None:
            return

        row.revoked_at = datetime.now(UTC)
        self.db.commit()

    def get_user_from_access_token(self, token: str) -> User:
        try:
            payload = decode_token(token, "access")
        except TokenError:
            raise CREDENTIALS_ERROR from None

        return self._load_user(payload.sub)

    def _find(self, refresh_token: str) -> RefreshToken | None:
        return (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == hash_token(refresh_token))
            .first()
        )

    def _load_user(self, subject: str) -> User:
        try:
            user_id = uuid.UUID(subject)
        except ValueError:
            # Only reachable with a validly signed token, but a non-UUID
            # sub would otherwise surface as a 500 from db.get.
            raise CREDENTIALS_ERROR from None

        user = self.db.get(User, user_id)
        if user is None:
            raise CREDENTIALS_ERROR
        return user
