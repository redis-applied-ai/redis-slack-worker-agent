#!/usr/bin/env bash
# Provision IAM permissions and verify access for Amazon Bedrock foundation models.
#
# Usage:
#   scripts/bedrock_provision_access.sh role <ROLE_NAME> [REGION]
#   scripts/bedrock_provision_access.sh user <USER_NAME> [REGION]
#
# Notes:
# - This script grants IAM permissions to INVOKE Bedrock models (least privilege)
#   and verifies CLI support and model presence in the region.
# - Enabling model access (provider subscriptions) typically requires the AWS Console.
#   If a model is not enabled for your account, follow the console link printed below.
# - Requires: awscli v2 with Bedrock commands, and permissions to attach policies.

set -euo pipefail

if ! command -v aws >/dev/null 2>&1; then
  echo "❌ aws CLI not found. Please install AWS CLI v2." >&2
  exit 1
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 (role|user) <NAME> [REGION]" >&2
  exit 1
fi

TARGET_TYPE="$1"   # role|user
TARGET_NAME="$2"
REGION="${3:-${AWS_DEFAULT_REGION:-us-east-1}}"

# Default model ID we plan to use in this repo
DEFAULT_MODEL_ID="anthropic.claude-3-5-sonnet-20240620-v1:0"

# Validate CLI has bedrock commands
if ! aws bedrock list-foundation-models --region "$REGION" >/dev/null 2>&1; then
  echo "❌ Your AWS CLI doesn't appear to support Bedrock commands or region $REGION isn't enabled for Bedrock." >&2
  echo "   Try updating AWS CLI (>=2.13) and ensure Bedrock is available in $REGION." >&2
  exit 1
fi

echo "✅ AWS CLI Bedrock detected. Region: $REGION"

# Create or locate a minimal invoke policy for Bedrock
POLICY_NAME="applied-ai-bedrock-invoke"
POLICY_DOC=$(mktemp)
cat >"$POLICY_DOC" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeAndListBedrockModels",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel"
      ],
      "Resource": "*"
    }
  ]
}
JSON

# Try to find existing policy
EXISTING_ARN=$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='${POLICY_NAME}'].Arn | [0]" --output text)
if [[ "$EXISTING_ARN" == "None" || -z "$EXISTING_ARN" ]]; then
  echo "ℹ️  Creating IAM policy: $POLICY_NAME"
  POLICY_ARN=$(aws iam create-policy \
    --policy-name "$POLICY_NAME" \
    --policy-document "file://$POLICY_DOC" \
    --query 'Policy.Arn' --output text)
else
  echo "ℹ️  Found existing IAM policy: $POLICY_NAME"
  POLICY_ARN="$EXISTING_ARN"
fi
rm -f "$POLICY_DOC"

echo "ℹ️  Attaching policy to $TARGET_TYPE: $TARGET_NAME"
if [[ "$TARGET_TYPE" == "role" ]]; then
  aws iam attach-role-policy --role-name "$TARGET_NAME" --policy-arn "$POLICY_ARN" || true
elif [[ "$TARGET_TYPE" == "user" ]]; then
  aws iam attach-user-policy --user-name "$TARGET_NAME" --policy-arn "$POLICY_ARN" || true
else
  echo "❌ TARGET_TYPE must be 'role' or 'user'" >&2
  exit 1
fi

echo "✅ Attached policy $POLICY_NAME ($POLICY_ARN) to $TARGET_TYPE $TARGET_NAME"

# Optional: also attach AWS managed read-only policy for Bedrock catalog visibility
MANAGED_READONLY_ARN="arn:aws:iam::aws:policy/AmazonBedrockReadOnly"
if [[ "$TARGET_TYPE" == "role" ]]; then
  aws iam attach-role-policy --role-name "$TARGET_NAME" --policy-arn "$MANAGED_READONLY_ARN" || true
else
  aws iam attach-user-policy --user-name "$TARGET_NAME" --policy-arn "$MANAGED_READONLY_ARN" || true
fi

echo "✅ Attached managed policy AmazonBedrockReadOnly"

# Verify model visibility in region
echo "ℹ️  Verifying model presence in region ($REGION): $DEFAULT_MODEL_ID"
MODEL_EXISTS=$(aws bedrock list-foundation-models --region "$REGION" \
  --query "modelSummaries[?modelId=='${DEFAULT_MODEL_ID}'] | length(@)" --output text)
if [[ "$MODEL_EXISTS" == "0" ]]; then
  echo "⚠️  Model $DEFAULT_MODEL_ID not listed in $REGION. It may be unavailable in this region." >&2
else
  echo "✅ Model $DEFAULT_MODEL_ID is listed in $REGION."
fi

# Guidance for model access enablement
CONSOLE_URL="https://${REGION}.console.aws.amazon.com/bedrock/home?region=${REGION}#/model-access"
echo
echo "Next step: ensure model access is enabled in your account (if required)."
echo "Open the Model access page and enable the providers/models you plan to use:"
echo "  $CONSOLE_URL"
echo

# Summary
echo "Done. IAM permissions attached. If you see AccessDenied when invoking,"
echo "enable the specific model on the Model access page above, then retry."

