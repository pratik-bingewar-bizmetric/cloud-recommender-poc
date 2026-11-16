/**
 * Top-level popup relay page entry (MSAL browser v5). Needed when the app runs inside the Fabric
 * iframe: MSAL opens this page as a top-level popup, which then opens the Entra sign-in window.
 * The relay may only navigate to Microsoft's sign-in origin.
 */
import { runPopupRelay } from "@azure/msal-browser/popup-relay";

void runPopupRelay({ allowedAuthorityOrigins: ["https://login.microsoftonline.com"] });
