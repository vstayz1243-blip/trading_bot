class Trading212Error(Exception):
    """Basisklasse für Trading-212-Fehler."""


class Trading212AuthenticationError(Trading212Error):
    """Authentifizierung fehlgeschlagen."""


class Trading212APIError(Trading212Error):
    """Die API hat eine Anfrage abgelehnt oder einen Fehler gemeldet."""


class Trading212ConnectionError(Trading212Error):
    """Trading 212 konnte nicht erreicht werden."""


class Trading212OrderStatusUnknown(Trading212ConnectionError):
    """Eine schreibende Anfrage wurde gesendet, ihr Ergebnis ist unklar."""