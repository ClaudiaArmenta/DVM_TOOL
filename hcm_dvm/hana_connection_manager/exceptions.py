"""Custom exceptions for the HANA Connection Manager."""


class HanaConnectionManagerError(Exception):
    """Base exception for all HANA Connection Manager errors."""

    def __init__(self, message: str, details: str = ""):
        self.message = message
        self.details = details
        super().__init__(self.message)


class ConnectionError(HanaConnectionManagerError):
    """Raised when a HANA database connection fails."""

    pass


class QueryError(HanaConnectionManagerError):
    """Raised when a SQL query execution fails."""

    pass


class SessionError(HanaConnectionManagerError):
    """Raised when SAP GUI session detection or interaction fails."""

    pass
