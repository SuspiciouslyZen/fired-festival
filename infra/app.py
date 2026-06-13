#!/usr/bin/env python3
"""
CDK app for the Ops Runbook Harness AWS infrastructure.

Deploy:
  cd infra
  pip install -r requirements.txt
  cdk deploy --context harness_url=https://your-harness-url.com
"""
import aws_cdk as cdk
from harness_stack import HarnessStack

app = cdk.App()
HarnessStack(
    app, "OpsRunbookHarness",
    env=cdk.Environment(region="us-east-2"),
)
app.synth()
