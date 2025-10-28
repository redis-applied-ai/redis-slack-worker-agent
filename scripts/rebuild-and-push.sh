#!/bin/bash
set -euo pipefail

echo "========================================="
echo "Rebuilding Docker images for linux/amd64"
echo "========================================="

AWS_REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

echo "ECR: $ECR"
echo ""

echo "Step 1: Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR"
echo "✓ Logged in"
echo ""

echo "Step 2: Building API image for linux/amd64 (this will take ~5-10 minutes)..."
docker build --platform linux/amd64 --no-cache -f Dockerfile.api -t "$ECR/my-ai-agent-api:latest" .
echo "✓ API image built"
echo ""

echo "Step 3: Pushing API image..."
docker push "$ECR/my-ai-agent-api:latest"
echo "✓ API image pushed"
echo ""

echo "Step 4: Building Worker image for linux/amd64 (this will take ~5-10 minutes)..."
docker build --platform linux/amd64 --no-cache -f Dockerfile.worker -t "$ECR/my-ai-agent-worker:latest" .
echo "✓ Worker image built"
echo ""

echo "Step 5: Pushing Worker image..."
docker push "$ECR/my-ai-agent-worker:latest"
echo "✓ Worker image pushed"
echo ""

echo "Step 6: Verifying local image architectures..."
API_ARCH=$(docker image inspect "$ECR/my-ai-agent-api:latest" --format '{{.Architecture}}')
WORKER_ARCH=$(docker image inspect "$ECR/my-ai-agent-worker:latest" --format '{{.Architecture}}')
echo "API architecture: $API_ARCH"
echo "Worker architecture: $WORKER_ARCH"

if [ "$API_ARCH" != "amd64" ] || [ "$WORKER_ARCH" != "amd64" ]; then
  echo "❌ ERROR: Images are not amd64!"
  exit 1
fi
echo "✓ Both images are amd64"
echo ""

echo "Step 7: Forcing ECS service redeployments..."
aws ecs update-service --cluster my-ai-agent-cluster --service my-ai-agent-api-service --force-new-deployment --region "$AWS_REGION" >/dev/null
aws ecs update-service --cluster my-ai-agent-cluster --service my-ai-agent-worker-service --force-new-deployment --region "$AWS_REGION" >/dev/null
echo "✓ Redeployments triggered"
echo ""

echo "========================================="
echo "✓ All done!"
echo "========================================="
echo ""
echo "ECS will now pull the new amd64 images and redeploy."
echo "This typically takes 2-5 minutes."
echo ""
echo "Monitor deployment:"
echo "  aws ecs describe-services --cluster my-ai-agent-cluster --services my-ai-agent-api-service --region us-east-1"
echo ""
echo "Check health:"
echo "  curl http://my-ai-agent-alb-438639628.us-east-1.elb.amazonaws.com/health"

