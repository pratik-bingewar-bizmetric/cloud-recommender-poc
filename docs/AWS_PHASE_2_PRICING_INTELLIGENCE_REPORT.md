# AWS Phase 2 — Pricing Intelligence & Location Normalization Report

> **AWS Service:** Price List API (`api.pricing.us-east-1.amazonaws.com`)  
> **API Actions:** `GetProducts`, `DescribeServices`  
> **Scope:** On-Demand Retail Pricing across EC2, Lambda, RDS, EBS, S3, and NAT Gateways  

---

## 1. Regional Location Normalization

The AWS Price List API indexes offerings using standard geographic location attributes rather than standard region codes. The `AwsPricingService` implements authoritative mapping:

| Region Code | Price List Location String | Verified Status |
| :--- | :--- | :--- |
| `eu-north-1` | `EU (Stockholm)` | Verified Live & Static |
| `us-east-1` | `US East (N. Virginia)` | Verified Live & Static |
| `us-east-2` | `US East (Ohio)` | Standard Mapping |
| `us-west-1` | `US West (N. California)` | Standard Mapping |
| `us-west-2` | `US West (Oregon)` | Standard Mapping |
| `eu-west-1` | `EU (Ireland)` | Standard Mapping |
| `eu-central-1` | `EU (Frankfurt)` | Standard Mapping |
| `ap-south-1` | `Asia Pacific (Mumbai)` | Standard Mapping |

---

## 2. In-Memory Caching & Deterministic Fallback

1. **In-Memory TTL Caching:**
   - Cache key format: `{ResourceType}:{Region}:{ResourceName}`.
   - Prevents duplicate queries for identical instance types across discovery sessions.
2. **Deterministic Offline Fallback Catalog:**
   - When external pricing APIs are unavailable, throttled, or running in an offline test suite, the service falls back to `STATIC_FALLBACK_RATES`.
   - Example baseline rates for `eu-north-1`:
     - `AWS::EC2::Instance` (`t3.medium`): $0.0416/hr ($30.37/mo).
     - `AWS::RDS::DBInstance` (`db.t3.medium` PostgreSQL): $0.068/hr ($49.64/mo).
     - `AWS::EC2::Volume` (`gp3` per 100GB): $8.00/mo ($0.08/GB-mo).
     - `AWS::EC2::NatGateway`: $0.045/hr ($32.85/mo).
     - `AWS::Lambda::Function`: $0.0000166667 per GB-second.
3. **Public Catalog Distinction:**
   - The UI explicitly highlights: *"Public on-demand list price rate retrieved via AWS Price List API. This represents standard retail catalog pricing and excludes customer negotiated enterprise discounts (EDP)."*

