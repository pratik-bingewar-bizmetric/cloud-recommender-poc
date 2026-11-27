# AWS Phase 2 — CloudWatch Telemetry & Resource Utilization Report

> **AWS Service:** CloudWatch Monitoring (`monitoring.{region}.amazonaws.com`)  
> **API Actions:** `GetMetricData`, `ListMetrics`  
> **Scope:** Compute, Serverless, Storage, Networking, and Database  

---

## 1. Telemetry Scope & Metrics Matrix

| AWS Resource Type | Namespace | Supported Metrics | Metric Unit | Gating / Instrumentation Status |
| :--- | :--- | :--- | :--- | :--- |
| `AWS::EC2::Instance` | `AWS/EC2` | `CPUUtilization`, `NetworkIn`, `NetworkOut`, `DiskReadOps`, `DiskWriteOps` | Percent, Bytes, Count | Standard Available |
| `AWS::EC2::Instance` (RAM) | `CWAgent` | `MemoryUtilization` | Percent | **`INSTRUMENTATION_REQUIRED`** (Requires CloudWatch Agent) |
| `AWS::Lambda::Function` | `AWS/Lambda` | `Invocations`, `Duration`, `Errors`, `Throttles` | Count, Milliseconds | Standard Available |
| `AWS::RDS::DBInstance` | `AWS/RDS` | `CPUUtilization`, `DatabaseConnections`, `FreeStorageSpace`, `ReadIOPS`, `WriteIOPS` | Percent, Count, Bytes | Standard Available |
| `AWS::EC2::Volume` | `AWS/EBS` | `VolumeReadOps`, `VolumeWriteOps`, `VolumeTotalReadTime`, `VolumeTotalWriteTime` | Count, Seconds | Standard Available |
| `AWS::EC2::NatGateway` | `AWS/NATGateway` | `BytesInFromSource`, `BytesOutToDestination`, `PacketsDropCount` | Bytes, Count | Standard Available |
| `AWS::S3::Bucket` | `AWS/S3` | `BucketSizeBytes`, `NumberOfObjects` | Bytes, Count | **Daily Granularity Only** (No Paid Request Metrics) |
| `AWS::ECS::Cluster` / `EKS` | `ContainerInsights`| Container Memory & CPU | Percent | **`INSTRUMENTATION_REQUIRED`** (Requires Container Insights) |

---

## 2. Key Telemetry Guardrails

1. **EC2 Memory Gating Invariant:**
   - AWS CloudWatch standard metrics **do not include operating system memory**.
   - The platform strictly marks EC2 memory as `INSTRUMENTATION_REQUIRED` and displays an "Agent Required" indicator in the UI.
   - It **never** estimates memory or treats absent memory data as 0% usage.
2. **S3 Daily Granularity Compliance:**
   - Standard CloudWatch storage metrics for S3 are calculated once per day at 00:00 UTC.
   - The telemetry service requests 86400s periods for S3 and does **not** enable paid 1-minute request metrics.
3. **Configurable Lookback Intervals:**
   - 24 Hours: 300-second resolution.
   - 7 Days: 3600-second resolution.
   - 30 Days: 86400-second resolution.

