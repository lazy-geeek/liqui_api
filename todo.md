# FastAPI Liquidation API Performance Optimization TODO

## Recent Updates (2025-01-15)
- ✅ Fixed USD calculation to use `average_price * order_filled_accumulated_quantity` instead of pre-calculated `usd_size`
- ✅ Resolved all type safety issues and Pylance errors
- ✅ Updated API response format for `/api/liquidations` endpoint
- ✅ Cleaned up unused imports and improved code quality

## Overview
This document outlines the step-by-step tasks to optimize the FastAPI liquidation API by implementing Redis caching, async MySQL connections, and other performance improvements.

## Quick Win Priorities
1. **Database Indexes** (Phase 5.1) - Immediate 30-50% query improvement
2. **Redis Caching** (Phase 3 & 4) - 90%+ improvement for repeated queries  
3. **Async Database** (Phase 2) - Better concurrency handling
4. **Connection Pooling** (Phase 2.1) - Reduce connection overhead

## Phase 1: Setup and Dependencies

### 1.1 Install Required Dependencies
- [x] Add Redis-related dependencies to `pyproject.toml`:
  - [x] `redis[hiredis]>=4.5.0` (includes async support)
  - [x] `fastapi-cache2==0.2.1`
  - [x] `aiomysql==0.2.0`
  - [x] `hiredis==2.3.2` (C parser for better Redis performance)
- [x] Run `poetry install` to install new dependencies
- [x] Update `requirements.txt` (should auto-update with poetry-auto-export)

### 1.2 Environment Configuration
- [x] Add Redis configuration variables to `.env`:
  - [x] `REDIS_HOST=localhost`
  - [x] `REDIS_PORT=6379`
  - [x] `REDIS_PASSWORD=` (if applicable)
  - [x] `REDIS_DB=0`
  - [x] `CACHE_TTL_SECONDS=300` (default 5 minutes)
  - [x] `CACHE_TTL_SYMBOLS=3600` (1 hour for symbols)
- [x] Update CLAUDE.md with new environment variables

## Phase 2: Async Database Implementation

### 2.1 Create Async Database Module
- [x] Create `app_async_db.py` with:
  - [x] Async connection pool setup using `aiomysql`
  - [x] Async context manager for connections
  - [x] Async query executor function
  - [x] Connection pool configuration (min=5, max=20)

### 2.2 Update Database Utilities
- [x] Create async versions of existing utilities:
  - [x] `async_db_connection()` context manager
  - [x] `async_db_error_handler()` decorator
  - [x] `async_execute_query()` function
- [x] Maintain backward compatibility with sync versions

### 2.3 Migrate Endpoints to Async
- [x] Convert `/api/liquidations` to use async database
- [x] Convert `/api/symbols` to use async database
- [x] Convert `/api/liquidation-orders` to use async database
- [x] Ensure all `async def` functions properly await database calls

## Phase 3: Redis Cache Implementation

### 3.1 Create Cache Configuration Module
- [x] Create `cache_config.py` with:
  - [x] Redis connection setup
  - [x] Cache key generation functions
  - [x] TTL configuration based on data type
  - [x] Cache initialization function

### 3.2 Implement Cache Key Generation
- [x] Create standardized cache key format:
  - [x] Liquidations: `liq:{symbol}:{timeframe}:{start}:{end}`
  - [x] Symbols: `symbols:all`
  - [x] Orders: `orders:{symbol}:{start}:{end}` or `orders:{symbol}:latest:{limit}`
- [x] Add hash function for long keys if needed

### 3.3 Add FastAPI Cache Integration
- [x] Initialize cache in app startup event
- [x] Configure Redis backend for cache
- [x] Add cache decorator utilities
- [x] Implement cache invalidation strategy
- [x] Add cache stampede prevention (circuit breaker pattern)
- [x] Implement Redis connection error handling (fallback to database)

## Phase 4: Endpoint Optimization

### 4.1 Optimize `/api/liquidations`
- [x] Add `@cache()` decorator with dynamic TTL
- [x] Implement cache key based on query parameters
- [x] Add cache warming for popular symbol/timeframe combinations
- [x] Add response compression for large datasets

### 4.2 Optimize `/api/symbols`
- [x] Add `@cache()` with longer TTL (1 hour)
- [x] Implement cache invalidation trigger
- [x] Consider pre-loading on startup (implemented via cache warming)

### 4.3 Optimize `/api/liquidation-orders`
- [x] Add `@cache()` with short TTL for recent data
- [x] Implement different TTLs for historical vs recent data
- [x] Add pagination support for large result sets
- [x] Add streaming response for very large queries (`/api/liquidation-orders/stream`)

## Phase 5: Database Optimization

### 5.1 Add Database Indexes
- [x] Create composite index on `(symbol, order_trade_time)`
- [x] Analyze query patterns and add additional indexes
- [x] Document index creation SQL in migration file

### 5.2 Query Optimization
- [x] Review and optimize SQL queries (COMPLETED: Changed from usd_size to calculated value)
- [x] Consider prepared statements for common queries
- [x] Add query timeout configuration

## Phase 6: Testing

### 6.1 Update Existing Tests
- [x] Update `test_app.py` to mock Redis cache
- [x] Update database mocks to support async operations
- [x] Ensure all tests pass with new async implementation

### 6.2 Add New Cache Tests
- [x] Create `test_cache.py` with:
  - [x] Cache hit/miss tests
  - [x] TTL expiration tests
  - [x] Cache key generation tests
  - [x] Cache invalidation tests

### 6.3 Add Performance Tests
- [x] Create `test_performance.py` with:
  - [x] Response time benchmarks
  - [x] Concurrent request handling tests
  - [x] Cache effectiveness metrics

### 6.4 Integration Tests
- [x] Update `test_integration.py` for Redis integration
- [x] Add tests for async database operations
- [x] Test cache warming functionality
- [x] Test Redis connection failure scenarios
- [x] Test cache stampede prevention

## Phase 7: Monitoring and Management

### 7.1 Add Cache Metrics Endpoint
- [x] Create `/api/cache/stats` endpoint:
  - [x] Cache hit rate
  - [x] Cache size
  - [x] TTL information
  - [x] Keys by pattern

### 7.2 Add Cache Management Endpoints
- [x] Create `/api/cache/clear`
- [x] Create `/api/cache/invalidate/symbol/{symbol}`
- [x] Create `/api/cache/invalidate/symbols`
- [ ] Add authentication for management endpoints

### 7.3 Logging and Monitoring
- [x] Add cache hit/miss logging
- [x] Add performance metrics logging
- [ ] Create Grafana dashboard queries (if applicable)

## Phase 8: Documentation

### 8.1 Update API Documentation
- [x] Document cache behavior in endpoint descriptions
- [x] Add cache management endpoints to documentation
- [x] Document new environment variables

### 8.2 Update CLAUDE.md
- [x] Add Redis setup instructions
- [x] Document cache architecture
- [x] Add cache management documentation
- [x] Update technology stack
- [x] Document recent architectural changes (COMPLETED: Added performance enhancement section)

### 8.3 Create Performance Guide
- [ ] Document expected performance improvements
- [ ] Add tuning recommendations
- [ ] Include cache strategy explanation

## Phase 9: Deployment Preparation

### 9.1 Update Deployment Configuration
- [x] Deploy as Dokku app (as mentioned in CLAUDE.md)
- [x] Add Redis to Procfile (if self-hosted)
- [x] Update Dokku configuration for Redis
- [x] Document Redis service requirements

### 9.2 Migration Strategy
- [x] Create rollback plan
- [x] Document cache warming procedure
- [x] Add health check for Redis connection
- [x] Create feature flags for gradual rollout
- [x] Document Redis memory requirements

## Phase 10: Security and Error Handling

### 10.1 Security Measures
- [ ] Implement cache key sanitization
- [ ] Add input validation for cache keys
- [ ] Consider encryption for sensitive cached data
- [ ] Implement rate limiting per API key/IP

### 10.2 Error Handling
- [ ] Implement circuit breaker for Redis failures
- [ ] Add retry logic with exponential backoff
- [ ] Create graceful degradation when cache unavailable
- [ ] Add comprehensive error logging

## Phase 11: Optional Enhancements

### 11.1 Advanced Caching
- [ ] Implement cache preloading for popular queries
- [ ] Add cache compression for large responses
- [ ] Implement distributed cache invalidation

### 11.2 Further Optimizations
- [ ] Consider response streaming for large datasets
- [ ] Implement request debouncing
- [ ] Add connection multiplexing

## Success Metrics
- [ ] Response time < 100ms for cached queries
- [ ] Cache hit rate > 70% for popular endpoints
- [ ] Database load reduction > 60%
- [ ] Support for 5x more concurrent requests
- [ ] Zero downtime during migration
- [ ] 99.9% availability maintained

## Notes
- Start with Phase 1-3 for immediate improvements
- Phases can be implemented incrementally
- Each phase should be tested before moving to the next
- Monitor performance metrics after each phase