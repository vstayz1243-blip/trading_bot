class Trading212Error(Exception):
    """Base exception for Trading 212 API errors."""

class Trading212AuthenticationError(Trading212Error):
    """Raised when authentication fails."""

class Trading212RateLimitError(Trading212Error):
    """Raised when the Trading 212 API rate limit is exceeded."""

class Trading212BadRequestError(Trading212Error):
    """Raised when the API rejects the request."""

class Trading212NotFoundError(Trading212Error):
    """Raised when a requested resource does not exist."""

class Trading212ServerError(Trading212Error):
    """Raised when Trading 212 returns a server-side error."""