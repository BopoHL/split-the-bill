"""The OpenAI client the receipt reader talks to, made on first use."""
import logging
import os

from openai import NotFoundError, OpenAI

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY is not set in environment!")
            raise ValueError("Missing OPENAI_API_KEY")
        # The SDK waits ten minutes and retries twice: a hung call would hold a
        # scan or a job that long. A receipt is read in well under a minute.
        _client = OpenAI(api_key=api_key, timeout=60.0, max_retries=1)
    return _client


def model_exists(name: str) -> bool:
    """Whether this API key can call the model. Anything but a plain «no such
    model» — no key, no network — is raised: that says nothing about the name."""
    try:
        get_openai_client().models.retrieve(name)
    except NotFoundError:
        return False
    return True
