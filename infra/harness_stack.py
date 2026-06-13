"""
AWS infrastructure for the Ops Runbook Harness.

Provisions:
  - SNS topic that receives CloudWatch Alarm notifications
  - HTTP subscription POSTing to /webhook/ec2 on the harness
  - CloudWatch StatusCheckFailed alarm per Monitor:true-tagged EC2 instance
  - EventBridge rule: EC2 state → stopped → SNS (backup path)
  - IAM instance profile for the harness EC2 with least-privilege permissions
"""
import boto3
import aws_cdk as cdk
from aws_cdk import (
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
)
from constructs import Construct


def _get_monitored_instances() -> list[dict]:
    """Discover EC2 instances tagged Monitor:true at synth time."""
    try:
        client = boto3.client("resourcegroupstaggingapi", region_name="us-east-2")
        paginator = client.get_paginator("get_resources")
        instances = []
        for page in paginator.paginate(
            TagFilters=[{"Key": "Monitor", "Values": ["true"]}],
            ResourceTypeFilters=["ec2:instance"],
        ):
            for resource in page["ResourceTagMappingList"]:
                arn = resource["ResourceARN"]
                instance_id = arn.rsplit("/", 1)[-1]
                tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}
                instances.append({"id": instance_id, "name": tags.get("Name", instance_id)})
        return instances
    except Exception as e:
        print(f"Warning: could not discover instances at synth time: {e}")
        return []


class HarnessStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        harness_url = self.node.try_get_context("harness_url") or ""
        webhook_url = f"{harness_url.rstrip('/')}/webhook/ec2"

        # SNS topic — receives both CloudWatch alarm actions and EventBridge forwarding
        topic = sns.Topic(self, "HarnessAlerts", display_name="Ops Runbook Harness Alerts")

        # HTTP subscription → harness webhook
        if harness_url:
            topic.add_subscription(subs.UrlSubscription(webhook_url))

        # CloudWatch StatusCheckFailed alarms for each monitored instance
        for instance in _get_monitored_instances():
            alarm = cw.Alarm(
                self,
                f"StatusCheck-{instance['id']}",
                alarm_name=f"harness-status-check-{instance['name']}",
                metric=cw.Metric(
                    namespace="AWS/EC2",
                    metric_name="StatusCheckFailed",
                    dimensions_map={"InstanceId": instance["id"]},
                    period=cdk.Duration.minutes(1),
                    statistic="Maximum",
                ),
                threshold=1,
                evaluation_periods=2,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                alarm_description=f"EC2 status check failed for {instance['name']} ({instance['id']})",
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            alarm.add_alarm_action(cw_actions.SnsAction(topic))

        # EventBridge rule: EC2 instance → stopped → SNS (backup alongside CW alarm)
        events.Rule(
            self,
            "EC2StoppedRule",
            rule_name="harness-ec2-stopped",
            description="Forward EC2 stopped-state events to the harness SNS topic",
            event_pattern=events.EventPattern(
                source=["aws.ec2"],
                detail_type=["EC2 Instance State-change Notification"],
                detail={"state": ["stopped"]},
            ),
            targets=[targets.SnsTopic(topic)],
        )

        # IAM policy for the harness EC2 instance profile
        harness_policy = iam.ManagedPolicy(
            self,
            "HarnessPolicy",
            managed_policy_name="OpsRunbookHarnessPolicy",
            statements=[
                # Service discovery
                iam.PolicyStatement(
                    actions=["tag:GetResources"],
                    resources=["*"],
                ),
                # CloudWatch metrics read
                iam.PolicyStatement(
                    actions=["cloudwatch:GetMetricStatistics", "cloudwatch:ListMetrics"],
                    resources=["*"],
                ),
                # CloudWatch Logs read
                iam.PolicyStatement(
                    actions=["logs:FilterLogEvents", "logs:DescribeLogGroups"],
                    resources=["*"],
                ),
                # EC2 stop/start scoped to Monitor:true instances
                iam.PolicyStatement(
                    actions=[
                        "ec2:StopInstances",
                        "ec2:StartInstances",
                        "ec2:DescribeInstanceStatus",
                        "ec2:DescribeInstances",
                    ],
                    resources=["*"],
                    conditions={
                        "StringEquals": {"aws:ResourceTag/Monitor": "true"}
                    },
                ),
                # Unrestricted describe (no resource-level condition supported)
                iam.PolicyStatement(
                    actions=["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"],
                    resources=["*"],
                ),
            ],
        )

        harness_role = iam.Role(
            self,
            "HarnessRole",
            role_name="OpsRunbookHarnessRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[harness_policy],
        )

        iam.CfnInstanceProfile(
            self,
            "HarnessInstanceProfile",
            instance_profile_name="OpsRunbookHarnessInstanceProfile",
            roles=[harness_role.role_name],
        )

        cdk.CfnOutput(self, "WebhookUrl", value=webhook_url)
        cdk.CfnOutput(self, "SnsTopicArn", value=topic.topic_arn)
