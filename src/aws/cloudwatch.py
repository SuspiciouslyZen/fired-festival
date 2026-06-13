"""
AWS CloudWatch helpers for metrics and logs.
"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def get_instance_metrics(instance_id: str) -> dict:
    """
    Fetch CPUUtilization, mem_used_percent, and StatusCheckFailed from CloudWatch
    for the given EC2 instance. Returns {"status": "unknown"} if no data.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        client = boto3.client("cloudwatch", region_name="us-east-2")
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=5)

        def _stat(namespace: str, metric: str, dimension_name: str) -> float | None:
            resp = client.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric,
                Dimensions=[{"Name": dimension_name, "Value": instance_id}],
                StartTime=start,
                EndTime=end,
                Period=300,
                Statistics=["Average"],
            )
            points = sorted(resp.get("Datapoints", []), key=lambda p: p["Timestamp"])
            return points[-1]["Average"] if points else None

        cpu = _stat("AWS/EC2", "CPUUtilization", "InstanceId")
        mem = _stat("CWAgent", "mem_used_percent", "InstanceId")
        status_check = _stat("AWS/EC2", "StatusCheckFailed", "InstanceId")

        if cpu is None and mem is None and status_check is None:
            return {"status": "unknown"}

        failed = status_check is not None and status_check > 0
        high_cpu = cpu is not None and cpu >= 90
        status = "degraded" if (failed or high_cpu) else "healthy"

        result: dict = {"status": status, "instance_id": instance_id}
        if cpu is not None:
            result["cpu_percent"] = round(cpu, 1)
        if mem is not None:
            result["memory_percent"] = round(mem, 1)
        if status_check is not None:
            result["status_check_failed"] = int(status_check)
        return result

    except Exception as e:
        logger.warning(f"CloudWatch metrics failed for {instance_id}: {e}")
        return {"status": "unknown"}


def get_recent_logs(log_group: str, minutes: int = 15) -> list[str]:
    """
    Fetch up to 50 recent log events from a CloudWatch Logs group.
    Returns empty list if the group doesn't exist or has no events.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        client = boto3.client("logs", region_name="us-east-2")
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ms = end_ms - minutes * 60 * 1000

        resp = client.filter_log_events(
            logGroupName=log_group,
            startTime=start_ms,
            endTime=end_ms,
            limit=50,
        )
        return [e["message"].strip() for e in resp.get("events", [])]

    except Exception as e:
        logger.warning(f"CloudWatch Logs failed for {log_group}: {e}")
        return []
