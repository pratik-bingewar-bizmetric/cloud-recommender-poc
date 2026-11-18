/**
 * Types for Service Principal-Only authentication and application sessions.
 * Mirrors backend/src/cloud_recommender/schemas/auth.py.
 */

export interface ServicePrincipalConnectRequest {
  account_name: string;
  subscription_id: string;
  tenant_id: string;
  client_id: string;
  client_secret: string;
}

export interface ServicePrincipalConnectResponse {
  session_token: string;
  session_id: string;
  account_id: string;
  account_name: string;
  connection_id: string;
  tenant_id: string;
  subscription_id: string;
  subscription_name: string;
  roles: string[];
  permissions: {
    reader: boolean;
    cost_management_reader: boolean;
    monitoring_reader: boolean;
    [key: string]: boolean;
  };
  created_at: string;
  expires_at: string;
}

export interface SessionInfoResponse {
  session_id: string;
  account_id: string;
  account_name: string;
  connection_id: string;
  tenant_id: string;
  subscription_id: string;
  subscription_name: string;
  roles: string[];
  permissions: {
    reader: boolean;
    cost_management_reader: boolean;
    monitoring_reader: boolean;
    [key: string]: boolean;
  };
  created_at: string;
  expires_at: string;
  last_used_at: string;
}

export interface LogoutResponse {
  status: string;
  message: string;
}

