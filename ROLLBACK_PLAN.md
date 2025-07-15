# Rollback Plan for Liqui API

## Overview
This document outlines the comprehensive rollback procedures for the Liqui API deployment, covering various failure scenarios and recovery strategies.

## Quick Reference

### Emergency Rollback Commands
```bash
# Dokku - Immediate rollback to previous release
dokku releases:rollback liqui-api

# Docker - Rollback to previous image
docker-compose down
docker tag liqui-api:previous liqui-api:latest
docker-compose up -d

# Cache - Clear problematic cache
redis-cli FLUSHDB
```

## Rollback Scenarios

### 1. Application Deployment Failure

#### Scenario A: Dokku Deployment Failure
```bash
# Check current releases
dokku releases liqui-api

# Rollback to previous working release
dokku releases:rollback liqui-api <previous-release-id>

# Verify rollback
curl http://your-domain/health
```

#### Scenario B: Docker Deployment Failure
```bash
# Stop current containers
docker-compose down

# Rollback to previous image
docker tag liqui-api:previous liqui-api:latest

# Restart with previous version
docker-compose up -d

# Verify rollback
docker logs liqui-api
curl http://localhost:8000/health
```

### 2. Database Issues

#### Scenario A: Database Migration Failure
```bash
# Connect to database
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE

# Drop problematic indexes (if applicable)
DROP INDEX IF EXISTS idx_symbol_order_trade_time ON binance_liqs;
DROP INDEX IF EXISTS idx_symbol_time_side ON binance_liqs;
DROP INDEX IF EXISTS idx_order_trade_time ON binance_liqs;
DROP INDEX IF EXISTS idx_side_time ON binance_liqs;
DROP INDEX IF EXISTS idx_symbol_side ON binance_liqs;

# Restore from backup
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE < backup_pre_migration.sql

# Verify data integrity
SELECT COUNT(*) FROM binance_liqs;
SELECT DISTINCT symbol FROM binance_liqs LIMIT 10;
```

#### Scenario B: Database Connection Issues
```bash
# Check database connectivity
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD -e "SELECT 1;"

# Rollback to previous database configuration
# Update environment variables
dokku config:set liqui-api DB_HOST=previous-db-host
dokku config:set liqui-api DB_USER=previous-db-user
dokku config:set liqui-api DB_PASSWORD=previous-db-password

# Restart application
dokku ps:restart liqui-api
```

### 3. Cache/Redis Issues

#### Scenario A: Redis Performance Issues
```bash
# Clear all cache
redis-cli FLUSHDB

# Restart Redis
sudo systemctl restart redis

# Disable cache temporarily
dokku config:set liqui-api REDIS_HOST=disabled

# Restart application
dokku ps:restart liqui-api
```

#### Scenario B: Redis Connection Failure
```bash
# Check Redis status
redis-cli ping

# Rollback to previous Redis configuration
dokku config:set liqui-api REDIS_HOST=previous-redis-host
dokku config:set liqui-api REDIS_PORT=previous-redis-port

# Or disable Redis temporarily
dokku config:unset liqui-api REDIS_HOST
dokku config:unset liqui-api REDIS_PORT

# Restart application
dokku ps:restart liqui-api
```

### 4. Performance Degradation

#### Scenario A: High Response Times
```bash
# Check current cache stats
curl http://your-domain/api/cache/stats

# Clear cache to reset performance
curl -X POST http://your-domain/api/cache/clear

# Rollback to previous cache configuration
dokku config:set liqui-api CACHE_TTL_SECONDS=600
dokku config:set liqui-api CACHE_TTL_SYMBOLS=7200

# Restart application
dokku ps:restart liqui-api
```

#### Scenario B: Database Query Timeouts
```bash
# Rollback to previous timeout settings
dokku config:set liqui-api QUERY_TIMEOUT_SECONDS=60
dokku config:set liqui-api LONG_QUERY_TIMEOUT_SECONDS=300

# Restart application
dokku ps:restart liqui-api

# Monitor query performance
curl http://your-domain/health
```

## Step-by-Step Rollback Procedures

### Complete System Rollback

#### Step 1: Assess the Situation
```bash
# Check application health
curl http://your-domain/health

# Check application logs
dokku logs liqui-api --tail 100

# Check database connectivity
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD -e "SELECT 1;"

# Check Redis connectivity
redis-cli ping
```

#### Step 2: Identify Rollback Target
```bash
# List available releases
dokku releases liqui-api

# Identify last known good release
# Check Git history
git log --oneline -10
```

#### Step 3: Execute Rollback
```bash
# Rollback application
dokku releases:rollback liqui-api <target-release-id>

# If database changes were made, restore from backup
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE < backup_pre_change.sql

# Clear cache to prevent stale data
redis-cli FLUSHDB
```

#### Step 4: Verify Rollback
```bash
# Check application health
curl http://your-domain/health

# Test critical endpoints
curl "http://your-domain/api/symbols"
curl "http://your-domain/api/liquidations?symbol=BTCUSDT&timeframe=5m&start_timestamp=1609459200000&end_timestamp=1609462800000"

# Check cache functionality
curl http://your-domain/api/cache/stats
```

## Environment-Specific Rollback

### Development Environment
```bash
# Stop current deployment
docker-compose down

# Rollback to previous version
git checkout <previous-commit>

# Rebuild and restart
docker-compose build
docker-compose up -d
```

### Staging Environment
```bash
# Rollback Dokku deployment
dokku releases:rollback liqui-api-staging <release-id>

# Restore staging database if needed
mysql -h $STAGING_DB_HOST -u $STAGING_DB_USER -p$STAGING_DB_PASSWORD $STAGING_DB_DATABASE < staging_backup.sql
```

### Production Environment
```bash
# Create immediate backup before rollback
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE > emergency_backup_$(date +%Y%m%d_%H%M%S).sql

# Rollback application
dokku releases:rollback liqui-api <release-id>

# Monitor closely after rollback
watch "curl -s http://your-domain/health | jq '.status'"
```

## Validation Checklist

### Post-Rollback Verification
- [ ] Health check endpoint returns 200 OK
- [ ] Database connectivity confirmed
- [ ] Redis connectivity confirmed (if applicable)
- [ ] All API endpoints respond correctly
- [ ] Cache hit rates are reasonable
- [ ] Response times are acceptable
- [ ] No error spikes in logs
- [ ] Application metrics look normal

### Testing Commands
```bash
# Basic health check
curl -f http://your-domain/health || echo "Health check failed"

# Test symbols endpoint
curl -f http://your-domain/api/symbols || echo "Symbols endpoint failed"

# Test liquidations endpoint
curl -f "http://your-domain/api/liquidations?symbol=BTCUSDT&timeframe=5m&start_timestamp=1609459200000&end_timestamp=1609462800000" || echo "Liquidations endpoint failed"

# Test cache stats
curl -f http://your-domain/api/cache/stats || echo "Cache stats failed"
```

## Communication Plan

### Incident Response Team
1. **Primary**: DevOps Engineer
2. **Secondary**: Backend Developer
3. **Escalation**: Technical Lead

### Communication Channels
- **Immediate**: Slack #alerts channel
- **Status Updates**: Status page
- **Post-Mortem**: Email to stakeholders

### Notification Templates

#### Rollback Initiated
```
🚨 ROLLBACK INITIATED
Service: Liqui API
Environment: Production
Reason: [Brief description]
ETA: [Estimated time to completion]
Status: In Progress
```

#### Rollback Completed
```
✅ ROLLBACK COMPLETED
Service: Liqui API
Environment: Production
Previous Version: [version]
Current Version: [version]
Status: Service Restored
Next Steps: [Investigation plan]
```

## Prevention Strategies

### Pre-Deployment Checks
```bash
# Run tests
pytest

# Check database migrations
python -c "from migrations import check_migrations; check_migrations()"

# Verify environment variables
python -c "from app import app; print('Environment OK')"

# Test Redis connectivity
redis-cli ping
```

### Monitoring Alerts
- Response time > 2 seconds
- Error rate > 5%
- Cache hit rate < 50%
- Database connection failures
- Redis connection failures

## Recovery Time Objectives

- **Application Rollback**: 5 minutes
- **Database Rollback**: 15 minutes
- **Complete System Rollback**: 30 minutes
- **Cache Recovery**: 2 minutes

## Backup Strategy

### Automated Backups
```bash
# Daily database backup
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE > backup_$(date +%Y%m%d).sql

# Retain backups for 30 days
find /backups -name "backup_*.sql" -mtime +30 -delete
```

### Manual Backup Before Changes
```bash
# Before deployment
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_DATABASE > backup_pre_deployment_$(date +%Y%m%d_%H%M%S).sql

# Document current release
dokku releases liqui-api > releases_before_deployment.txt
```

## Emergency Contacts

### Technical Team
- **DevOps Lead**: [contact info]
- **Backend Lead**: [contact info]
- **Database Admin**: [contact info]

### Business Team
- **Product Manager**: [contact info]
- **Customer Support**: [contact info]

## Post-Rollback Actions

1. **Immediate**: Verify service restoration
2. **Short-term**: Investigate root cause
3. **Medium-term**: Implement preventive measures
4. **Long-term**: Update deployment processes

## Documentation Updates

After each rollback:
1. Update this document with lessons learned
2. Add new scenarios encountered
3. Improve automation scripts
4. Update monitoring thresholds