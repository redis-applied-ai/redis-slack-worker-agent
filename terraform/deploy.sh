#!/bin/bash

# Applied AI Agent - Terraform Deployment Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command_exists terraform; then
        print_error "Terraform is not installed. Please install Terraform >= 1.0"
        exit 1
    fi
    
    if ! command_exists aws; then
        print_error "AWS CLI is not installed. Please install AWS CLI"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        print_error "AWS credentials not configured. Please run 'aws configure'"
        exit 1
    fi
    
    print_status "Prerequisites check passed"
}

# Function to deploy environment
deploy_environment() {
    local environment=$1
    local action=${2:-"plan"}
    
    if [[ ! "$environment" =~ ^(dev|stage|prod)$ ]]; then
        print_error "Invalid environment: $environment. Must be dev, stage, or prod"
        exit 1
    fi
    
    print_status "Deploying $environment environment..."
    
    cd "environments/$environment"
    
    # Initialize Terraform
    print_status "Initializing Terraform..."
    terraform init
    
    # Validate configuration
    print_status "Validating Terraform configuration..."
    terraform validate
    
    if [ "$action" = "plan" ]; then
        print_status "Creating Terraform plan..."
        terraform plan -out=tfplan
        print_warning "Plan created. Run with 'apply' to deploy or 'destroy' to remove resources"
    elif [ "$action" = "apply" ]; then
        print_status "Applying Terraform configuration..."
        terraform apply -auto-approve
        print_status "Deployment completed successfully!"
        
        # Show outputs
        print_status "Deployment outputs:"
        terraform output
    elif [ "$action" = "destroy" ]; then
        print_warning "This will destroy all resources in $environment environment!"
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            print_status "Destroying resources..."
            terraform destroy -auto-approve
            print_status "Resources destroyed successfully!"
        else
            print_status "Destruction cancelled"
        fi
    else
        print_error "Invalid action: $action. Must be plan, apply, or destroy"
        exit 1
    fi
    
    cd ../..
}

# Function to show help
show_help() {
    echo "Applied AI Agent - Terraform Deployment Script"
    echo ""
    echo "Usage: $0 [ENVIRONMENT] [ACTION]"
    echo ""
    echo "ENVIRONMENT:"
    echo "  dev       - Development environment"
    echo "  stage     - Staging environment"
    echo "  prod      - Production environment"
    echo ""
    echo "ACTION:"
    echo "  plan      - Create Terraform plan (default)"
    echo "  apply     - Deploy infrastructure"
    echo "  destroy   - Remove infrastructure"
    echo ""
    echo "Examples:"
    echo "  $0 dev plan"
    echo "  $0 stage apply"
    echo "  $0 prod destroy"
    echo ""
    echo "Prerequisites:"
    echo "  - Terraform >= 1.0"
    echo "  - AWS CLI configured"
    echo "  - Appropriate AWS permissions"
}

# Main script
main() {
    # Check if help is requested
    if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
        show_help
        exit 0
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Get environment and action
    local environment=${1:-"dev"}
    local action=${2:-"plan"}
    
    # Deploy environment
    deploy_environment "$environment" "$action"
}

# Run main function with all arguments
main "$@"
