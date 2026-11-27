"""AWS FinOps provider integration package."""

from cloud_recommender.services.aws.auth_service import (
    AwsAuthenticationError,
    AwsAuthService,
    AwsCredentials,
    get_aws_auth_service,
)
from cloud_recommender.services.aws.cloudwatch_service import (
    AwsCloudWatchMetricsService,
    get_aws_cloudwatch_service,
)
from cloud_recommender.services.aws.connectivity_service import (
    AwsConnectivityService,
    get_aws_connectivity_service,
)
from cloud_recommender.services.aws.cost_explorer_service import (
    AwsCostExplorerError,
    AwsCostExplorerService,
    get_aws_cost_explorer_service,
)
from cloud_recommender.services.aws.cur_service import (
    AwsCurService,
    get_aws_cur_service,
)
from cloud_recommender.services.aws.findings_service import (
    AwsFindingsDetector,
    get_aws_findings_detector,
)
from cloud_recommender.services.aws.pricing_service import (
    AwsPricingService,
    get_aws_pricing_service,
)
from cloud_recommender.services.aws.sigv4 import sign_aws_request

__all__ = [
    "AwsAuthenticationError",
    "AwsAuthService",
    "AwsCloudWatchMetricsService",
    "AwsConnectivityService",
    "AwsCostExplorerError",
    "AwsCostExplorerService",
    "AwsCredentials",
    "AwsCurService",
    "AwsFindingsDetector",
    "AwsPricingService",
    "get_aws_auth_service",
    "get_aws_cloudwatch_service",
    "get_aws_connectivity_service",
    "get_aws_cost_explorer_service",
    "get_aws_cur_service",
    "get_aws_findings_detector",
    "get_aws_pricing_service",
    "sign_aws_request",
]
