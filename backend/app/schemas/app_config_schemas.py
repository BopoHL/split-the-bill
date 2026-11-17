from pydantic import BaseModel


class AppConfigResponse(BaseModel):
    """What the Mini App needs to know that an operator decides."""
    support_username: str
