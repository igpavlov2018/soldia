#!/bin/bash

echo "🔄 Running database migrations..."

# Wait for database to be ready
echo "⏳ Waiting for database..."
sleep 5

# Run migrations
alembic upgrade head

echo "✅ Migrations complete!"
