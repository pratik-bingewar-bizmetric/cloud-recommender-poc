"""Exceptions for Azure AI Foundry model inference."""


class AzureAIFoundryError(Exception):
    """Base exception for Azure AI Foundry operations."""


class AzureAIFoundryNotConfiguredError(AzureAIFoundryError):
    """Raised when Azure AI Foundry credentials/endpoints are not configured."""

    def __init__(
        self,
        message: str = (
            "Azure AI Foundry is not configured. Required environment variables: "
            "AZURE_AI_FOUNDRY_ENDPOINT, AZURE_AI_FOUNDRY_API_KEY, "
            "and AZURE_AI_FOUNDRY_DEPLOYMENT_NAME."
        ),
        missing_vars: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.missing_vars = missing_vars or []


class AzureAIFoundryAuthError(AzureAIFoundryError):
    """Raised when Azure AI Foundry authentication fails (401 / 403)."""


class AzureAIFoundryRateLimitError(AzureAIFoundryError):
    """Raised when Azure AI Foundry returns HTTP 429 Too Many Requests."""


class AzureAIFoundryTimeoutError(AzureAIFoundryError):
    """Raised when request to Azure AI Foundry times out."""


class AzureAIFoundryResponseError(AzureAIFoundryError):
    """Raised when Azure AI Foundry returns an invalid or schema-nonconforming response."""
