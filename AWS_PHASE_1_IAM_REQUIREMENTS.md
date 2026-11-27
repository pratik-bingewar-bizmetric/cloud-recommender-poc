# AWS Phase 1: IAM Requirements & Least-Privilege Policy Specification

> **Document Status:** Complete & Enforced  
> **Date:** 2026-11-24  
> **Repository:** `cloud-recommender-poc`  
> **Target Account ID:** `435305479688`  
> **Policy Name:** `FinOpsReadOnlyDiscoveryPolicy`

---

## 1. Zero-Execution & Read-Only Policy Mandate

The FinOps application is strictly an observability, inventory, and advisory platform. Under no circumstances does the application require or use mutation (`Create*`, `Update*`, `Delete*`, `Put*`, `Attach*`, `Detach*`, `Modify*`) permissions.

---

## 2. Recommended AWS Managed Policies

For customers utilizing AWS managed policies, the minimum baseline consists of:

| AWS Managed Policy | ARN | Purpose |
| :--- | :--- | :--- |
| `SecurityAudit` | `arn:aws:iam::aws:policy/SecurityAudit` | Read-only inspection of IAM, Security Groups, VPCs, and encryption configurations. |
| `ViewOnlyAccess` | `arn:aws:iam::aws:policy/job-function/ViewOnlyAccess` | View-only inspection of compute instances, Lambda functions, S3 buckets, and RDS databases. |
| `AWSPriceListServiceFullAccess` | `arn:aws:iam::aws:policy/AWSPriceListServiceFullAccess` | Read-only access to query current AWS Retail & Catalog pricing. |

---

## 3. Dedicated Custom Least-Privilege IAM Policy

For enterprise customers requiring exact least-privilege scoping without broad wildcard access, attach the following custom IAM policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "FinOpsIdentityAndCallerVerification",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsSecurityAndIAMInspection",
      "Effect": "Allow",
      "Action": [
        "iam:ListRoles",
        "iam:GetRole",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsComputeAndNetworkingDiscovery",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeRegions",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeRouteTables",
        "ec2:DescribeInternetGateways",
        "ec2:DescribeNatGateways",
        "ec2:DescribeVpnGateways",
        "ec2:DescribeInstances",
        "ec2:DescribeVolumes",
        "ec2:DescribeAddresses",
        "lambda:ListFunctions",
        "lambda:GetFunctionConfiguration"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsContainersDiscovery",
      "Effect": "Allow",
      "Action": [
        "ecs:ListClusters",
        "ecs:DescribeClusters",
        "eks:ListClusters",
        "eks:DescribeCluster"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsStorageAndDatabasesDiscovery",
      "Effect": "Allow",
      "Action": [
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "rds:DescribeDBInstances"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsMonitoringAndCostIntelligence",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:ListMetrics",
        "ce:GetDimensionValues",
        "pricing:DescribeServices",
        "pricing:GetProducts"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 4. Cross-Account STS AssumeRole Trust Policy

When deploying cross-account access, create an IAM Role in the customer account with the trust policy below:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "FinOpsAppAssumeRolePolicy",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::435305479688:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "finops-client-account-435305479688"
        }
      }
    }
  ]
}
```

