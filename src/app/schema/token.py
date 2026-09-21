from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schema.user import UserRead


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # Access token lifetime in seconds, so clients need not decode the JWT.
    expires_in: int


class LoginResponse(TokenPair):
    """Login only: the tokens plus who they belong to.

    Nested rather than flattened so user fields cannot collide with token
    fields, and so UserRead stays the single definition of a public user
    (it already excludes `password`). /refresh returns a bare TokenPair —
    it is given only a token, so it has no user context to echo back.
    """

    user: UserRead


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPayload(BaseModel):
    """Decoded claim set.

    Validating `type` as a Literal is what stops a refresh token being
    replayed as an access token: constructing this from a decoded dict
    raises if the claim is anything else, or missing.
    """

    sub: str
    exp: datetime
    iat: datetime
    jti: str
    type: Literal["access", "refresh"]
