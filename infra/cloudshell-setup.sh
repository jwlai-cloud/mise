#!/usr/bin/env bash
# Paste into AWS CloudShell while signed in to the console as an ADMIN of
# account 034355008385. Creates the deployer policy, attaches it to
# mimir-bedrock, and creates the mise-runtime role. Safe to re-run.
# Generated from infra/*.json - regenerate if those change.
set -uo pipefail
ACCT=034355008385
[ "$(aws sts get-caller-identity --query Account --output text)" = "$ACCT" ] \
  || { echo "Wrong account - sign in to $ACCT first"; exit 1; }

cat > /tmp/mise-deployer.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AgentCoreEverything",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:*",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": [
            "us-east-1",
            "us-west-2",
            "ap-southeast-2"
          ]
        }
      }
    },
    {
      "Sid": "BedrockModelsAndProfiles",
      "Effect": "Allow",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel",
        "bedrock:ListInferenceProfiles",
        "bedrock:GetInferenceProfile",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DeploySubstrate",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:CompleteLayerUpload",
        "ecr:CreateRepository",
        "ecr:DescribeRepositories",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart",
        "codebuild:CreateProject",
        "codebuild:BatchGetBuilds",
        "codebuild:ListProjects",
        "codebuild:StartBuild",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:PutLogEvents",
        "xray:GetSamplingRules",
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords"
      ],
      "Resource": "*"
    },
    {
      "Sid": "TrajectoryEvaluatorLambda",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:GetFunction",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:AddPermission",
        "lambda:InvokeFunction",
        "lambda:DeleteFunction"
      ],
      "Resource": "arn:aws:lambda:*:*:function:mise-*"
    },
    {
      "Sid": "DeploymentArtifacts",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::bedrock-agentcore-*",
        "arn:aws:s3:::bedrock-agentcore-*/*",
        "arn:aws:s3:::mise-*",
        "arn:aws:s3:::mise-*/*"
      ]
    },
    {
      "Sid": "InboundAuthForTheRuntime",
      "Effect": "Allow",
      "Action": [
        "cognito-idp:CreateUserPool",
        "cognito-idp:CreateUserPoolClient",
        "cognito-idp:DescribeUserPool",
        "cognito-idp:DescribeUserPoolClient",
        "cognito-idp:ListUserPools",
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminSetUserPassword"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CreateTheRuntimeExecutionRole",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:GetRole",
        "iam:ListRoles",
        "iam:TagRole",
        "iam:PutRolePolicy",
        "iam:GetRolePolicy",
        "iam:AttachRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:CreateServiceLinkedRole"
      ],
      "Resource": "arn:aws:iam::*:role/mise-*"
    },
    {
      "Sid": "PassOnlyToAgentCore",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/mise-*",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": [
            "bedrock-agentcore.amazonaws.com",
            "lambda.amazonaws.com"
          ]
        }
      }
    }
  ]
}
JSON

cat > /tmp/mise-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AgentCoreRuntimeAssumes",
      "Effect": "Allow",
      "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
      "Action": "sts:AssumeRole",
      "Condition": {"StringEquals": {"aws:SourceAccount": "034355008385"}}
    },
    {
      "Sid": "TrajectoryEvaluatorLambdaAssumes",
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

cat > /tmp/mise-exec.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeTheModelsTheAgentGraphUses",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                 "bedrock:Converse", "bedrock:ConverseStream"],
      "Resource": [
        "arn:aws:bedrock:ap-southeast-2:*:inference-profile/au.*",
        "arn:aws:bedrock:*::foundation-model/*"
      ]
    },
    {
      "Sid": "PerCookCalibration",
      "Effect": "Allow",
      "Action": ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents",
                 "bedrock-agentcore:RetrieveMemoryRecords", "bedrock-agentcore:GetMemory",
                 "bedrock-agentcore:IngestData"],
      "Resource": "arn:aws:bedrock-agentcore:ap-southeast-2:*:memory/*"
    },
    {
      "Sid": "Observability",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams",
                 "xray:PutTraceSegments", "xray:PutTelemetryRecords"],
      "Resource": "*"
    }
  ]
}
JSON

echo "1/3 policy MiseDeployer"
aws iam create-policy --policy-name MiseDeployer \
  --policy-document file:///tmp/mise-deployer.json >/dev/null 2>&1 \
  || aws iam create-policy-version --policy-arn arn:aws:iam::$ACCT:policy/MiseDeployer \
       --policy-document file:///tmp/mise-deployer.json --set-as-default >/dev/null
aws iam attach-user-policy --user-name mimir-bedrock \
  --policy-arn arn:aws:iam::$ACCT:policy/MiseDeployer

echo "2/3 role mise-runtime"
aws iam create-role --role-name mise-runtime \
  --assume-role-policy-document file:///tmp/mise-trust.json >/dev/null 2>&1 \
  || aws iam update-assume-role-policy --role-name mise-runtime \
       --policy-document file:///tmp/mise-trust.json
aws iam put-role-policy --role-name mise-runtime --policy-name mise-runtime \
  --policy-document file:///tmp/mise-exec.json

echo "3/3 verify"
aws iam list-attached-user-policies --user-name mimir-bedrock \
  --query "AttachedPolicies[?PolicyName=='MiseDeployer'].PolicyName" --output text
aws iam get-role --role-name mise-runtime --query Role.Arn --output text
echo "Done. Now submit the Anthropic use-case form in the Bedrock console, then run"
echo "  python3 infra/preflight.py   on your laptop."
