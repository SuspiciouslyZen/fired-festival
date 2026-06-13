"""
AWS service discovery via Resource Groups Tagging API.

Enumerates all EC2 instances tagged Monitor:true and builds a
service_name -> instance_id map used by check_status, restart_service,
and read_logs at execution time.
"""
import logging

logger = logging.getLogger(__name__)

_discovery_map: dict[str, str] = {}  # service_name -> instance_id


def list_monitored_services() -> list[str]:
    """Return service names for all EC2 instances tagged Monitor:true."""
    global _discovery_map
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        client = boto3.client("resourcegroupstaggingapi", region_name="us-east-2")
        paginator = client.get_paginator("get_resources")
        services: dict[str, str] = {}

        for page in paginator.paginate(
            TagFilters=[{"Key": "Monitor", "Values": ["true"]}],
            ResourceTypeFilters=["ec2:instance"],
        ):
            for resource in page["ResourceTagMappingList"]:
                arn = resource["ResourceARN"]
                tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}
                # ARN format: arn:aws:ec2:region:account:instance/i-xxxx
                instance_id = arn.rsplit("/", 1)[-1]
                name = tags.get("Name", instance_id)
                services[name] = instance_id

        _discovery_map = services
        logger.info(f"AWS discovery found {len(services)} monitored services: {list(services.keys())}")
        return list(services.keys())

    except Exception as e:
        logger.warning(f"AWS service discovery failed, using static list: {e}")
        return []


def get_service_instance_map() -> dict[str, str]:
    """Return the cached service_name -> instance_id map from the last discovery run."""
    return _discovery_map.copy()


def get_service_name_for_instance(instance_id: str) -> str | None:
    """Reverse lookup: instance_id -> service_name from the cached discovery map."""
    for name, iid in _discovery_map.items():
        if iid == instance_id:
            return name
    return None
