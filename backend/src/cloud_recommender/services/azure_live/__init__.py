"""Live Azure access using credentials supplied by the signed-in user.

Security properties (enforced by code and tests):
- Tokens are requested directly from Microsoft Entra ID with the user's tenant/client/secret
  (OAuth2 client credentials); no Azure CLI, no DefaultAzureCredential, no server identity.
- The client secret exists only for the duration of the connect call; it is never stored,
  logged or returned. Only the short-lived access token is kept, in process memory.
- Azure calls are read-only (GET, plus the Cost Management read query).
"""
