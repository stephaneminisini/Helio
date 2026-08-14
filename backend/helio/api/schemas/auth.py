from datetime import datetime

from pydantic import BaseModel


class AuthorizeResponse(BaseModel):
    """Response model for GET /api/auth/enphase/authorize."""

    authorization_url: str


class ConnectionStatus(BaseModel):
    """Connection state of the Enphase account.

    Deliberately holds no token or secret: it is read by the browser, and the
    stored tokens never need to leave the server.

    Attributes:
        connected: Whether an Enphase refresh token is stored for the system.
        client_configured: Whether the server has a client ID and secret, i.e.
            whether connecting is possible at all.
        token_updated_at: When the stored token pair was last rotated.
        last_successful_poll_at: When the most recent poll succeeded.
        token_warning: Message set once the refresh token nears expiry.
    """

    connected: bool
    client_configured: bool
    token_updated_at: datetime | None = None
    last_successful_poll_at: datetime | None = None
    token_warning: str | None = None
