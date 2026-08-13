"""Connection configuration management.

Provides dataclasses for HANA connection parameters and app-level settings.
Supports environment variable loading for deployment flexibility.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HANAConnectionConfig:
    """SAP HANA connection parameters.

    Usage:
        # Direct instantiation
        config = HANAConnectionConfig(
            host="hana01.company.com",
            port=30015,
            user="SYSTEM",
            password="secret",
        )

        # From environment variables
        config = HANAConnectionConfig.from_env()

        # From a state dictionary (e.g., ConnectionStore)
        config = HANAConnectionConfig.from_dict(state)
    """

    host: str = ""
    port: int = 30015
    user: str = ""
    password: str = ""
    encrypt: bool = True
    sslValidateCertificate: bool = False
    tenant: str = ""

    @classmethod
    def from_env(cls) -> "HANAConnectionConfig":
        """Create config from environment variables.

        Environment Variables:
            HANA_HOST: Database hostname
            HANA_PORT: SQL port (default: 30015)
            HANA_USER: Database user
            HANA_PASSWORD: Database password
            HANA_ENCRYPT: Enable TLS (default: true)
            HANA_VALIDATE_CERT: Validate server cert (default: false)
            HANA_TENANT: Tenant database name
        """
        return cls(
            host=os.getenv("HANA_HOST", ""),
            port=int(os.getenv("HANA_PORT", "30015")),
            user=os.getenv("HANA_USER", ""),
            password=os.getenv("HANA_PASSWORD", ""),
            encrypt=os.getenv("HANA_ENCRYPT", "true").lower() == "true",
            sslValidateCertificate=os.getenv("HANA_VALIDATE_CERT", "false").lower() == "true",
            tenant=os.getenv("HANA_TENANT", ""),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "HANAConnectionConfig":
        """Create config from a dictionary (e.g., from ConnectionStore).

        Args:
            data: Dictionary with connection parameters.
        """
        return cls(
            host=data.get("host", ""),
            port=int(data.get("port", 30015)),
            user=data.get("user", ""),
            password=data.get("password", ""),
            encrypt=data.get("encrypt", True),
            sslValidateCertificate=data.get("sslValidateCertificate", False),
            tenant=data.get("tenant", ""),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "encrypt": self.encrypt,
            "sslValidateCertificate": self.sslValidateCertificate,
            "tenant": self.tenant,
        }

    @property
    def display_string(self) -> str:
        """Human-readable connection info (no password)."""
        s = f"{self.user}@{self.host}:{self.port}"
        if self.tenant:
            s += f" ({self.tenant})"
        return s

    @property
    def is_valid(self) -> bool:
        """Check if minimum required fields are present."""
        return bool(self.host and self.port and self.user and self.password)


@dataclass
class ConnectionManagerConfig:
    """Configuration for the Connection Manager application."""

    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8051
    state_file: str = ""

    hana: HANAConnectionConfig = field(default_factory=HANAConnectionConfig)

    @classmethod
    def load(cls) -> "ConnectionManagerConfig":
        """Load from environment variables."""
        return cls(
            debug=os.getenv("CONN_MGR_DEBUG", "false").lower() == "true",
            host=os.getenv("CONN_MGR_HOST", "0.0.0.0"),
            port=int(os.getenv("CONN_MGR_PORT", "8051")),
            state_file=os.getenv("CONN_MGR_STATE_FILE", ""),
            hana=HANAConnectionConfig.from_env(),
        )


# Singleton config instance
Config = ConnectionManagerConfig.load()
