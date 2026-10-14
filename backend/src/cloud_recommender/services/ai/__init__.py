"""Azure AI services package for Cloud Recommender."""

from cloud_recommender.services.ai.exceptions import (
    AzureAIFoundryAuthError,
    AzureAIFoundryError,
    AzureAIFoundryNotConfiguredError,
    AzureAIFoundryRateLimitError,
    AzureAIFoundryResponseError,
    AzureAIFoundryTimeoutError,
)
from cloud_recommender.services.ai.foundry_provider import AzureAIFoundryProvider

__all__ = [
    "AzureAIFoundryProvider",
    "AzureAIFoundryError",
    "AzureAIFoundryNotConfiguredError",
    "AzureAIFoundryAuthError",
    "AzureAIFoundryRateLimitError",
    "AzureAIFoundryTimeoutError",
    "AzureAIFoundryResponseError",
]
