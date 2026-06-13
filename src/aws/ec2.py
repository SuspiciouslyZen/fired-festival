"""
AWS EC2 helpers for instance lifecycle operations.
"""
import logging

logger = logging.getLogger(__name__)


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
