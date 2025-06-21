class DataApiRateLimitError(Exception):
    """Raised when a data API responds with HTTP 429."""
    pass
