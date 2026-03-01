#!/bin/bash

# ==================== SOLDIA v2.0 - Deployment Script ====================

set -e  # Exit on error

echo "=================================================="
echo "🚀 SOLDIA v2.0 - Production Deployment"
echo "=================================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "ℹ $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    print_error "Do not run this script as root!"
    exit 1
fi

# Check prerequisites
print_info "Checking prerequisites..."

# Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi
print_success "Docker found"

# Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
print_success "Docker Compose found"

# Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed."
    exit 1
fi
print_success "Python 3 found"

echo ""

# Check if .env exists
if [ ! -f .env ]; then
    print_warning ".env file not found. Creating from .env.example..."
    
    if [ -f .env.example ]; then
        cp .env.example .env
        print_success ".env file created"
        print_warning "Please edit .env file and set your configuration!"
        print_info "Critical values to set:"
        echo "  - SECRET_KEY"
        echo "  - DATABASE_URL"
        echo "  - MAIN_WALLET"
        echo "  - MAIN_WALLET_TOKEN"
        echo "  - HOT_WALLET_PRIVATE_KEY"
        echo ""
        read -p "Press Enter after editing .env file..."
    else
        print_error ".env.example not found!"
        exit 1
    fi
else
    print_success ".env file found"
fi

echo ""

# Ask for deployment mode
echo "Select deployment mode:"
echo "  1) Development (with hot reload)"
echo "  2) Production (optimized)"
read -p "Enter choice [1-2]: " deploy_mode

case $deploy_mode in
    1)
        print_info "Deploying in DEVELOPMENT mode..."
        COMPOSE_FILE="docker-compose.yml"
        ;;
    2)
        print_info "Deploying in PRODUCTION mode..."
        COMPOSE_FILE="docker-compose.yml"
        
        # Check critical environment variables
        if grep -q "CHANGE_THIS" .env || grep -q "change_this" .env; then
            print_error "Found default values in .env! Please set proper values."
            exit 1
        fi
        ;;
    *)
        print_error "Invalid choice!"
        exit 1
        ;;
esac

echo ""

# Build images
print_info "Building Docker images..."
docker-compose -f $COMPOSE_FILE build
print_success "Images built successfully"

echo ""

# Start services
print_info "Starting services..."
docker-compose -f $COMPOSE_FILE up -d

# Wait for services to be healthy
print_info "Waiting for services to be ready..."
sleep 10

# Check service health
print_info "Checking service health..."

# PostgreSQL
if docker-compose -f $COMPOSE_FILE exec -T postgres pg_isready -U soldia_user > /dev/null 2>&1; then
    print_success "PostgreSQL is healthy"
else
    print_error "PostgreSQL is not healthy!"
    docker-compose -f $COMPOSE_FILE logs postgres
    exit 1
fi

# Redis
if docker-compose -f $COMPOSE_FILE exec -T redis redis-cli -a "${REDIS_PASSWORD:-}" ping > /dev/null 2>&1; then
    print_success "Redis is healthy"
else
    print_error "Redis is not healthy!"
    docker-compose -f $COMPOSE_FILE logs redis
    exit 1
fi

echo ""

# Run database migrations
print_info "Running database migrations..."
docker-compose -f $COMPOSE_FILE exec -T web alembic upgrade head
print_success "Migrations completed"

echo ""

# Test API health
print_info "Testing API health..."
sleep 5

if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    print_success "API is healthy"
else
    print_error "API health check failed!"
    docker-compose -f $COMPOSE_FILE logs web
    exit 1
fi

echo ""
echo "=================================================="
print_success "Deployment completed successfully!"
echo "=================================================="
echo ""

# Show service URLs
echo "Service URLs:"
echo "  • API:            http://localhost:8000"
echo "  • API Docs:       http://localhost:8000/docs"
echo "  • API Health:     http://localhost:8000/health"
echo "  • Flower (Celery): http://localhost:5555"
echo ""

# Show useful commands
echo "Useful commands:"
echo "  • View logs:        docker-compose logs -f"
echo "  • Stop services:    docker-compose down"
echo "  • Restart:          docker-compose restart"
echo "  • View stats:       docker-compose ps"
echo "  • Shell access:     docker-compose exec web bash"
echo ""

# Show warnings for production
if [ "$deploy_mode" = "2" ]; then
    print_warning "Production deployment checklist:"
    echo "  ✓ Change all default passwords"
    echo "  ✓ Configure firewall (allow only 80, 443, 22)"
    echo "  ✓ Set up SSL/TLS certificates"
    echo "  ✓ Configure backup strategy"
    echo "  ✓ Set up monitoring (Sentry, etc.)"
    echo "  ✓ Review CORS settings"
    echo "  ✓ Test rate limiting"
    echo ""
fi

print_success "SOLDIA v2.0 is now running!"
