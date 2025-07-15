# Deployment Guide for Liqui API

## Overview
This guide covers deploying the Liqui API using Dokku, Docker, and other deployment methods.

## Prerequisites

- Python 3.12+
- Redis server
- MySQL database
- Docker (for containerized deployment)
- Dokku server (for Dokku deployment)

## Environment Variables

The following environment variables are required:

### Database Configuration
```bash
DB_HOST=your-mysql-host
DB_USER=your-mysql-user
DB_PASSWORD=your-mysql-password
DB_DATABASE=your-database-name
DB_LIQ_TABLENAME=binance_liqs  # Optional, defaults to binance_liqs
```

### Redis Configuration
```bash
REDIS_HOST=localhost          # Redis host
REDIS_PORT=6379              # Redis port
REDIS_PASSWORD=              # Redis password (if required)
REDIS_DB=0                   # Redis database number
CACHE_TTL_SECONDS=300        # Default cache TTL (5 minutes)
CACHE_TTL_SYMBOLS=3600       # Symbols cache TTL (1 hour)
```

### Query Optimization
```bash
QUERY_TIMEOUT_SECONDS=30      # Standard query timeout
LONG_QUERY_TIMEOUT_SECONDS=120 # Long query timeout
```

## Deployment Methods

### 1. Dokku Deployment

#### Step 1: Prepare Dokku Server
```bash
# Create the application
dokku apps:create liqui-api

# Install Redis plugin (if not already installed)
dokku plugin:install https://github.com/dokku/dokku-redis.git redis

# Create and link Redis service
dokku redis:create liqui-api-redis
dokku redis:link liqui-api-redis liqui-api

# This automatically sets REDIS_URL environment variable
# The app will detect and use this automatically
```

#### Step 2: Configure Environment Variables
```bash
# Set database variables
dokku config:set liqui-api DB_HOST=your-mysql-host
dokku config:set liqui-api DB_USER=your-mysql-user
dokku config:set liqui-api DB_PASSWORD=your-mysql-password
dokku config:set liqui-api DB_DATABASE=your-database-name
dokku config:set liqui-api DB_LIQ_TABLENAME=binance_liqs

# Set cache and optimization variables
dokku config:set liqui-api CACHE_TTL_SECONDS=300
dokku config:set liqui-api CACHE_TTL_SYMBOLS=3600
dokku config:set liqui-api QUERY_TIMEOUT_SECONDS=30
dokku config:set liqui-api LONG_QUERY_TIMEOUT_SECONDS=120
```

#### Step 3: Deploy Application
```bash
# Add Dokku remote
git remote add dokku dokku@your-dokku-server:liqui-api

# Deploy
git push dokku main
```

#### Step 4: Configure Domain (Optional)
```bash
# Set domain
dokku domains:set liqui-api api.yourdomain.com

# Enable SSL with Let's Encrypt
dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git
dokku letsencrypt:enable liqui-api
```

### 2. Docker Deployment

#### Step 1: Build and Run with Docker Compose
```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your configuration

# Build and run
docker-compose up -d
```

#### Step 2: Manual Docker Build
```bash
# Build image
docker build -t liqui-api .

# Run container
docker run -d \
  --name liqui-api \
  -p 8000:8000 \
  -e DB_HOST=your-mysql-host \
  -e DB_USER=your-mysql-user \
  -e DB_PASSWORD=your-mysql-password \
  -e DB_DATABASE=your-database-name \
  -e REDIS_HOST=redis \
  --link redis:redis \
  liqui-api
```

### 3. Traditional Server Deployment

#### Step 1: Install Dependencies
```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install --no-dev
```

#### Step 2: Set Environment Variables
```bash
# Create .env file or set environment variables
export DB_HOST=your-mysql-host
export DB_USER=your-mysql-user
export DB_PASSWORD=your-mysql-password
export DB_DATABASE=your-database-name
export REDIS_HOST=localhost
export REDIS_PORT=6379
```

#### Step 3: Run Application
```bash
# Production server
poetry run gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 app:app

# Development server
poetry run uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## Database Setup

### Required Database Indexes
Run the following SQL to create performance indexes:

```sql
-- Run the migration script
source migrations.sql
```

### Database Schema
The application expects a table with these columns:
- `symbol` (VARCHAR)
- `order_trade_time` (BIGINT)
- `side` (VARCHAR)
- `average_price` (DECIMAL)
- `order_filled_accumulated_quantity` (DECIMAL)
- Additional columns for liquidation orders endpoint

## Redis Configuration

### Redis Memory Requirements
- **Development**: 256MB minimum
- **Production**: 1GB+ recommended
- **High Traffic**: 2GB+ recommended

### Redis Configuration Options
```bash
# Redis persistence
redis-server --appendonly yes

# Redis memory limit
redis-server --maxmemory 1gb --maxmemory-policy allkeys-lru
```

## Health Checks

The application provides a health check endpoint at `/health`:

```bash
# Check application health
curl http://localhost:8000/health
```

Response format:
```json
{
  "status": "healthy",
  "timestamp": "2023-01-01T00:00:00Z",
  "components": {
    "database": {
      "status": "healthy",
      "message": "Database connection successful"
    },
    "redis": {
      "status": "healthy",
      "message": "Redis connection successful",
      "hit_rate": 75.5
    }
  }
}
```

## Monitoring

### Application Metrics
- Response times via `/api/cache/stats`
- Cache hit rates via `/api/cache/stats`
- Database query performance
- Error rates in application logs

### Recommended Monitoring Tools
- **Application Performance**: New Relic, DataDog
- **Infrastructure**: Prometheus + Grafana
- **Logs**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **Uptime**: Pingdom, UptimeRobot

## Performance Tuning

### Database Optimization
- Ensure proper indexes are created (see migrations.sql)
- Monitor slow queries
- Consider read replicas for high traffic

### Cache Optimization
- Monitor cache hit rates (target >70%)
- Adjust TTL values based on usage patterns
- Consider Redis clustering for high availability

### Application Scaling
- Scale horizontally with multiple instances
- Use load balancer (nginx, HAProxy)
- Monitor memory usage and CPU utilization

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Check environment variables
   - Verify database connectivity
   - Check firewall rules

2. **Redis Connection Issues**
   - Ensure Redis is running
   - Check Redis configuration
   - Verify network connectivity

3. **Memory Issues**
   - Monitor Redis memory usage
   - Check for memory leaks
   - Adjust cache TTL settings

4. **Performance Issues**
   - Check database indexes
   - Monitor cache hit rates
   - Analyze slow queries

### Debugging Commands
```bash
# Check application logs
docker logs liqui-api

# Monitor Redis
redis-cli monitor

# Check database connections
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD -e "SHOW PROCESSLIST;"

# Test health endpoint
curl -v http://localhost:8000/health
```

## Security Considerations

1. **Environment Variables**
   - Never commit secrets to version control
   - Use secure environment variable management
   - Rotate credentials regularly

2. **Network Security**
   - Use TLS/SSL for all connections
   - Implement proper firewall rules
   - Restrict database access

3. **API Security**
   - Implement rate limiting
   - Use API keys for authentication
   - Monitor for abuse patterns

## Rollback Plan

### Quick Rollback (Dokku)
```bash
# List releases
dokku releases liqui-api

# Rollback to previous release
dokku releases:rollback liqui-api <release-id>
```

### Database Rollback
```bash
# Backup current database
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE > backup.sql

# Restore from backup if needed
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE < backup.sql
```

### Cache Rollback
```bash
# Clear cache if needed
redis-cli FLUSHDB

# Restart Redis
sudo systemctl restart redis
```

## Maintenance

### Regular Tasks
- Monitor application metrics
- Update dependencies
- Backup database
- Monitor Redis memory usage
- Check application logs

### Scaling Considerations
- Monitor response times
- Track database query performance
- Monitor cache hit rates
- Plan for traffic growth

## Support

For deployment issues:
1. Check application logs
2. Verify environment variables
3. Test database connectivity
4. Check Redis availability
5. Review this deployment guide