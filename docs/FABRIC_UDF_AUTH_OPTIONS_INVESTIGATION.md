# Fabric UDF Authentication — Reuse Investigation (no admin rights)

Date 2026-11-16 · read-only investigation: no code, configuration, Entra object, consent or deployment was changed. Secrets were not read or shown.
Context: `docs/FABRIC_UDF_401_AND_DEPLOYMENT_REPORT.md` (the UDF client needs a delegated Entra token for the Fabric/Power BI audience).

## Update — verified production facts and official-documentation check

**Confirmed by the account owner (taken as given, not re-tested):** workspace `672a6995-4190-4000-befd-5cc6479c3f74`; UDF item `8c5bbc01-c941-4f0e-90d3-7053921c32f8`, name `finops-udf-prod-v5`; account `pratik.bingewar@bizmetric.com` is **Workspace Admin** with direct **Read, Write, Reshare, Execute** on the item; the portal ID matches the app configuration. **Conclusion: the 401 is not a Fabric permission, UDF-identity or workspace problem.** A 401 means Fabric did not accept the *token*; item permissions are evaluated only after authentication succeeds (a missing item permission would be 403). Nothing about the UDF, the workspace or your permissions needs to change, and none was changed.

**Official documentation, re-read today** ([Tutorial: invoke user data functions from a Python application](https://learn.microsoft.com/en-us/fabric/data-engineering/user-data-functions/tutorial-invoke-from-python-app), updated 2026-08-04; [Generate invocation code](https://learn.microsoft.com/en-us/fabric/data-engineering/user-data-functions/generate-invocation-code), updated 2026-11-06):

| Requirement | What Microsoft states |
|---|---|
| Registration | An Entra app registration; **Authentication → Add a platform → Single-page application** with the redirect URI; authorization code flow with **PKCE** (fallback: also add *Mobile and desktop applications*; sample also enables *Allow public client flows*). |
| Permission | "Add the **Power BI Service**, select **Delegated permissions**, and select **UserDataFunction.Execute.All** or **item.Execute.All** permissions. Confirm that admin consent isn't required." |
| Scope in the sample | `scope = "https://analysis.windows.net/powerbi/api/user_impersonation"` (Power BI resource, delegated). The audience is not spelled out; it is the Power BI service. |
| Request | `POST <Public URL of the function>` with `Authorization: Bearer <token>`; the URL is copied from the portal ("Public URL"); **Public access must be enabled** for the function (an off setting gives 400, not 401). |
| Caller's item permission | At least **Execute** on the UDF item. |
| Service principals / app-only | **Not stated by either page** (only delegated permissions are listed). Unverified. |

**Correction to my earlier report:** I had defaulted the app's scope to `…/powerbi/api/.default`, which Microsoft does not document for this call. The application now defaults to the documented scope `https://analysis.windows.net/powerbi/api/user_impersonation` (still overridable with `VITE_FABRIC_UDF_SCOPE`). The audience check in the client already accepts the Power BI audience.

**Reusable registration? — rechecked across all 143 app registrations in the tenant (read-only):** none is suitable.
- Apps with SPA redirect URIs belong to other products (FCM-Bizmetric, Murphy, Klydo, Biz-Single-Sign-On, …); none has a `fabricapps.net` redirect.
- Only **one** app requests `UserDataFunction`/`Item.Execute` at all: `PowerBIAPI` (created 2022, `Item.Execute.All`, **web** platform only, no SPA platform, **no owner listed**). Reusing it would still need an administrator to add an SPA platform and would share one client ID with unrelated Power BI integrations — not recommended.
- Nobody-owned and other teams' apps cannot be edited by you (you own no applications).

**Exact remaining administrator requirement:** one new single-tenant **SPA** registration (or an administrator adding an SPA platform to an app you will own) carrying the delegated Power BI Service permission above, **plus you as Owner**. Entra roles that can do it: *Application Developer*, *Application Administrator* or *Cloud Application Administrator* (Global Administrator is not required). Admin **consent** is needed only if user consent is blocked in your tenant — Microsoft says it should not be.

**Application readiness (done, no admin needed):** only `VITE_ENTRA_CLIENT_ID` is missing; the tenant is taken from the existing `VITE_FABRIC_TENANT_ID`. A new non-secret helper, `getFabricUdfAuthReadiness()`, reports `ready/missing/scope/tenant` for the test step. 181 frontend tests and the production build pass. The new build is **not** deployed (it changes nothing visible until the client ID exists).

## 1. Verdict

| Question | Answer |
|---|---|
| Can existing Fabric SSO supply the token? | **No.** |
| Can an existing app registration be reused? | **No suitable one exists.** |
| Is administrator involvement unavoidable? | **For the direct (browser → Fabric UDF) design: yes** — you cannot create the registration yourself (verified). |
| Is there a supported design that needs no new registration? | **Possibly: Rayfin Functions as a server-side relay.** Supported and documented, but whether Fabric accepts the app identity for the UDF invoke endpoint is **not verified** and it is an architecture change. |
| Code work possible without an admin? | The client is already complete. The only remaining no-admin work is an optional relay prototype that needs a deployment and a viability test. |

## 2. What was inspected and what it shows

1. **Rayfin / Fabric SSO** (`rayfin.yml`, `rayfin-auth-provider-fabric`, packaged guide `auth/fabric.md`, `auth/direct-entra-auth.md`). Fabric SSO authenticates the user *to the Rayfin app*: the Fabric host hands the app a **handoff code** (PKCE), which the SDK exchanges for **Rayfin session tokens**. No Entra access token for Fabric REST is ever exposed to the app. `externalEntraExchange: true` goes the other way (it exchanges an Entra token **for** a Rayfin session) and needs an Entra token the app would already have. Rayfin tokens are not accepted by `api.fabric.microsoft.com`. → SSO cannot be reused to call the UDF endpoint directly.
2. **Entra / MSAL configuration.** The app's MSAL code needs `VITE_ENTRA_CLIENT_ID`, which is unset in `.env`, `.env.local` and `.env.production`; only `VITE_FABRIC_TENANT_ID` is present. No SPA registration is configured anywhere.
3. **Backend API authentication.** `backend/.env` defines no Entra settings (`ENTRA_*`) at all and `entra_auth_enabled` defaults to false; there is no backend app registration to reuse either.
4. **Existing registrations (verified live, read-only Graph/`az`).** You own **no** applications (`az ad app list --show-mine` → empty). Tenant apps with Fabric-flavoured names (`FabricTrainingIndia`, `biz-foundry-acc-fabric`, `Biz_Fabric_Hackathon`, `DBXGenieFabric`, …) belong to other work: none has an SPA redirect URI, none has any Power BI Service permission; `DBXGenieFabric` only has Power Platform connector redirects. Repurposing another team's registration would mean sharing a client ID across unrelated products and needs that app's owner to edit it — not recommended and not a clean fit.
5. **Permissions that exist in the tenant (verified).** The Power BI Service principal exposes `UserDataFunction.Execute.All` and `Item.Execute.All`, both **type `User`** (delegated, user-consentable in principle — consistent with Microsoft's tutorial, which says admin consent should not be required). Whether *your* tenant lets users consent to them depends on its consent policy (assigned policies: `ManagePermissionGrantsForSelf.microsoft-user-default-recommended` and `…allow-consent-apps`); the classification of these specific permissions was not readable, so this is **uncertain**.
6. **Supported server-side mechanism.** Yes — **Rayfin Functions** (packaged guide `functions/*`): TypeScript functions deployed by `rayfin up` that run in the Fabric runtime and are called from the browser with `RayfinClient` (`client.functions.<name>.invoke()`), authenticated by the **Rayfin session that SSO already provides** (no Entra registration). Inside a function, `ctx.Tokens.Fabric` is a token for `https://api.fabric.microsoft.com/v1`, issued to the **application identity** — for current Fabric apps, *the owner of the Fabric app item* — documented example: calling the Fabric REST API from a function. Our UDF invoke endpoint is a Fabric REST call, so a relay function could call it.
7. **Using the signed-in user's own identity without a new registration: not possible.** The Rayfin session identifies the user to Rayfin only; it carries no Entra delegated token. With the relay the Fabric call is made as the **item owner**, not as the end user.
8. **Tenant facts (verified).** You cannot register applications: `allowedToCreateApps = false`, and you hold no directory role.

Rejected on purpose: using Microsoft's first-party public clients (Azure CLI / PowerShell client IDs) in the browser, embedding a client secret or service-principal credential in the frontend, or sending the Rayfin token to Fabric — each bypasses or weakens Entra.

## 3. Options compared

| Option | Needs admin? | Per-user identity at Fabric | Verified? | Effort / risk |
|---|---|---|---|---|
| **A. SPA registration + MSAL (current code)** | **Yes** (someone with *Application Developer*/*Application Administrator*; consent only if user consent is blocked) | **Yes** (each user's own delegated token; Fabric enforces their Execute permission) | Code and flow verified offline; live not tested | Smallest change; client already built; one build variable |
| **B. Rayfin Functions relay (`ctx.Tokens.Fabric`)** | **No Entra admin**; the app identity (item owner) needs Execute on the UDF item — you, as workspace creator, very likely already have it | **No** — every caller acts as the owner; per-user authorisation must be coded in the function using the caller's Rayfin token | **Not verified**: the docs say to check the target API supports the application identity, and the UDF invoke endpoint is only documented for delegated users | Adds a TS functions project, `services.functions.enabled: true` + `auth.type: application` in `rayfin.yml`, a **full `rayfin up`** (changes remote app settings), and a wrapper function per UDF call |
| **C. FastAPI backend as relay** | Yes (needs a backend registration + Fabric-capable credential) | Depends | No | Larger; adds a secret-bearing server |

## 4. Minimum administrator action (for option A)

One request to an Entra administrator (Application Developer or higher), no client secret involved:

1. **Create one app registration**, single tenant (`fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`), e.g. "Cloud FinOps Recommender (Fabric UDF)".
2. **Authentication → Add a platform → Single-page application**, redirect URI `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net/redirect.html` (add `http://localhost:5173/redirect.html` if local sign-in is wanted).
3. **API permissions → Add → Power BI Service → Delegated → `UserDataFunction.Execute.All`** (add `Item.Execute.All` if the first is refused). Grant **admin consent only if** user consent turns out to be blocked.
4. **Add you as an Owner** of the registration, so redirect URIs and permissions can be adjusted later without another admin ticket.
5. Send back the **Application (client) ID** (a public identifier). It goes into `VITE_ENTRA_CLIENT_ID`; then redeploy with `npx rayfin up staticapp deploy`.

Separately (not Entra): each user needs **Execute** on the UDF item in the Fabric portal (workspace role Contributor or higher, or the item shared with Execute).

## 5. What can be done without an administrator

- **Already done**: the UDF client acquires/uses only a Fabric-audience delegated token, never the Rayfin token, with silent renewal, single retry, popup fallback and precise 401/403/404/429/5xx diagnostics; the Fabric tenant is read from the existing `VITE_FABRIC_TENANT_ID`; build id and deployment were completed.
- **Nothing further in the current code is blocked by the lack of a registration** other than the live token itself; until the client ID exists the app shows `ENTRA_NOT_CONFIGURED`.
- **Optional, no Entra admin**: a viability test of option B — a single `pingFabricUdf` Rayfin function that uses `ctx.Tokens.Fabric` to call `…/userDataFunctions/{id}/functions/list_connections/invoke`. It requires enabling Functions in `rayfin.yml` and a full `rayfin up` (it changes the deployed app's runtime settings), so I did **not** start it (you asked for no speculative changes, and the Workspace Connections feature is on hold). If it returns 200 it removes the need for an admin; if Fabric rejects the application identity, option A is the only route.

## 6. Recommendation

Request the registration (option A): it is the documented model for calling UDFs, keeps per-user identity and auditing, and needs no secret. In parallel, if the request will take long, authorise the option-B viability test as a time-boxed experiment — accepting that it runs as the item owner and needs its own per-user authorisation in code.
