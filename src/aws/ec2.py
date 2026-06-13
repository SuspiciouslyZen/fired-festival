"""
AWS EC2 helpers for instance lifecycle operations.
"""
import logging

logger = logging.getLogger(__name__)


def start_ec2_instance(instance_id: str) -> dict:
    """
    Start a stopped EC2 instance and wait until it reaches running state.
    Blocks up to ~2 minutes (12 attempts × 10s delay) before returning.
    """
    try:
        import boto3

        client = boto3.client("ec2", region_name="us-east-2")
        client.start_instances(InstanceIds=[instance_id])
        logger.info(f"EC2 instance {instance_id} start issued, waiting for running state")

        waiter = client.get_waiter("instance_running")
        waiter.wait(
            InstanceIds=[instance_id],
            WaiterConfig={"Delay": 10, "MaxAttempts": 12},
        )

        logger.info(f"EC2 instance {instance_id} is running")
        return {"success": True, "new_status": "running", "instance_id": instance_id}

    except Exception as e:
        logger.error(f"EC2 start failed for {instance_id}: {e}")
        return {"success": False, "new_status": "unknown", "instance_id": instance_id, "error": str(e)}


def get_ec2_instance_status(instance_id: str) -> dict:
    """Return current state and status checks for an EC2 instance."""
    try:
        import boto3

        client = boto3.client("ec2", region_name="us-east-2")
        resp = client.describe_instances(InstanceIds=[instance_id])
        instance = resp["Reservations"][0]["Instances"][0]
        state = instance["State"]["Name"]

        status_resp = client.describe_instance_status(
            InstanceIds=[instance_id], IncludeAllInstances=True
        )
        status_items = status_resp.get("InstanceStatuses", [])
        sys_check = "not-applicable"
        inst_check = "not-applicable"
        if status_items:
            sys_check = status_items[0]["SystemStatus"]["Status"]
            inst_check = status_items[0]["InstanceStatus"]["Status"]

        return {
            "instance_id": instance_id,
            "state": state,
            "system_status": sys_check,
            "instance_status": inst_check,
            "status": "healthy" if state == "running" and inst_check == "ok" else state,
        }

    except Exception as e:
        logger.error(f"EC2 describe failed for {instance_id}: {e}")
        return {"instance_id": instance_id, "state": "unknown", "error": str(e)}


def restart_ec2_instance(instance_id: str) -> dict:
    """
    Stop an EC2 instance, wait for stopped state, then start it.
    Returns {"success": bool, "new_status": str, "instance_id": str}.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        client = boto3.client("ec2", region_name="us-east-2")
        client.stop_instances(InstanceIds=[instance_id])

        waiter = client.get_waiter("instance_stopped")
        waiter.wait(
            InstanceIds=[instance_id],
            WaiterConfig={"Delay": 5, "MaxAttempts": 12},
        )

        client.start_instances(InstanceIds=[instance_id])
        logger.info(f"EC2 instance {instance_id} restarted successfully")
        return {"success": True, "new_status": "healthy", "instance_id": instance_id}

    except Exception as e:
        logger.error(f"EC2 restart failed for {instance_id}: {e}")
        return {
            "success": False,
            "new_status": "unknown",
            "instance_id": instance_id,
            "error": str(e),
        }
