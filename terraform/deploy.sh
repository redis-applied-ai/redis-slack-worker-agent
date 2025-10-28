#!/usr/bin/env bash

# Applied AI Agent - Terraform Deployment Script (Single Project)
# Simplified for one environment. Operates in the terraform/ directory.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Missing required command: $1"
    exit 1
  fi
}

usage() {
  cat <<EOF
Applied AI Agent - Terraform Deployment Script (Single Project)

Usage: $(basename "$0") [plan|apply|destroy]
  plan    - terraform init/validate/plan (default)
  apply   - terraform apply (uses tfplan if present, else prompts)
  destroy - terraform destroy (prompts)

Notes:
- Expects to be run from repo root. It will cd into terraform/ automatically.
- Requires Terraform >= 1.0. AWS CLI is needed for 'apply' and 'destroy'.
EOF
}

main() {
  local action=${1:-plan}
  case "$action" in
    -h|--help) usage; exit 0;;
    plan|apply|destroy) ;;
    *) error "Unknown action: $action"; usage; exit 1;;
  esac

  need terraform
  if [[ "$action" != "plan" ]]; then
    need aws
    # Validate AWS credentials early for state-changing actions
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
      error "AWS credentials not configured. Run 'aws configure' first."
      exit 1
    fi
  fi

  # Run from terraform directory
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$SCRIPT_DIR"

  info "Initializing Terraform..."
  terraform init

  info "Validating Terraform configuration..."
  terraform validate

  if [[ "$action" == "plan" ]]; then
    info "Creating Terraform plan (tfplan)..."
    terraform plan -out=tfplan
    warn "Plan saved to tfplan. Run: $(basename "$0") apply to deploy."
    exit 0
  fi

  if [[ "$action" == "apply" ]]; then
    info "Applying Terraform configuration..."
    if [[ -f tfplan ]]; then
      terraform apply tfplan
    else
      warn "No tfplan found. Applying without a saved plan."
      terraform apply
    fi

    info "Deployment completed successfully. Outputs:"
    terraform output
    exit 0
  fi

  if [[ "$action" == "destroy" ]]; then
    warn "This will destroy all infrastructure!"
    read -rp "Type 'yes' to confirm: " confirm
    if [[ "$confirm" == "yes" ]]; then
      terraform destroy
      info "Resources destroyed."
    else
      info "Destroy cancelled."
    fi
  fi
}

main "$@"
