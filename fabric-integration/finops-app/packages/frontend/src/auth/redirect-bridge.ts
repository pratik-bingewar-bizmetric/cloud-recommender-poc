/**
 * Redirect bridge page entry (MSAL browser v5). Entra redirects the sign-in popup here; this page
 * hands the response to the main window and closes. It never reads or stores tokens itself.
 */
import { broadcastResponseToMainFrame } from "@azure/msal-browser/redirect-bridge";

void broadcastResponseToMainFrame();
