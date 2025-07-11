# TODO: Database Connection and Error Handling Refactoring

## Goal
Reduce code redundancy in database connection management and error handling across all API endpoints by creating reusable utilities.

## Phase 1: Create Core Database Utilities
- [x] Add database utility functions section after imports in app.py (after line 10)
- [x] Implement `db_connection()` context manager:
  - [x] Handles connection lifecycle automatically
  - [x] Ensures cursor and connection cleanup
  - [x] Works with Python's `with` statement
- [x] Implement `db_error_handler()` decorator:
  - [x] Wraps endpoints for consistent error handling
  - [x] Logs errors with endpoint name
  - [x] Returns appropriate HTTP status codes
- [x] Create `execute_query()` helper function:
  - [x] Accepts query string and parameters
  - [x] Handles fetch_all vs fetch_one modes
  - [x] Uses db_connection context manager internally
- [x] Add proper type hints to all utility functions

## Phase 2: Create Unit Tests for Database Utilities
- [x] Create test/test_db_utils.py file
- [x] Test db_connection context manager:
  - [x] Test successful connection and cleanup
  - [x] Test cleanup when exception occurs during query
  - [x] Test behavior when connection fails
  - [x] Verify cursor.close() and conn.close() are called
- [x] Test db_error_handler decorator:
  - [x] Test mysql.connector.Error → HTTPException(500)
  - [x] Test HTTPException pass-through unchanged
  - [x] Test generic Exception → HTTPException(500)
  - [x] Verify error logging includes endpoint name
- [x] Test execute_query helper:
  - [x] Test with fetch_all=True (default)
  - [x] Test with fetch_all=False
  - [x] Test parameter binding works correctly
  - [x] Test with empty results

## Phase 3: Refactor /api/symbols Endpoint
- [x] Apply @db_error_handler("/api/symbols") decorator
- [x] Replace entire try/except/finally block with db_connection usage
- [x] Remove manual cursor.close() and conn.close() calls
- [x] Reduce function body to ~10 lines
- [x] Update test_app.py for /api/symbols:
  - [x] Update mock patches to work with new structure
  - [x] Ensure all 5 existing tests still pass
  - [x] Add test for new decorator behavior

## Phase 4: Refactor /api/liquidations Endpoint
- [x] Apply @db_error_handler("/api/liquidations") decorator
- [x] Keep parameter validation logic unchanged (lines 91-109)
- [x] Replace database try/except/finally with db_connection
- [x] Use execute_query for the SQL query execution
- [x] Update test_app.py for /api/liquidations:
  - [x] Adjust mock patches for new patterns
  - [x] Ensure all 11 existing tests pass
  - [x] Verify validation logic unchanged

## Phase 5: Refactor /api/liquidation-orders Endpoint
- [x] Apply @db_error_handler("/api/liquidation-orders") decorator
- [x] Keep complex parameter validation (lines 228-274)
- [x] Replace database try/except/finally with db_connection
- [x] Handle both query patterns (timestamp vs limit) with new utilities
- [x] Update test_app.py for /api/liquidation-orders:
  - [x] Update mocks for refactored structure
  - [x] Ensure all 14 existing tests pass
  - [x] Test both query modes work correctly

## Phase 6: FastAPI Dependency Injection Alternative
- [x] Create get_db_cursor() dependency function using yield
- [x] Add proper Generator type hints
- [x] Create example endpoint using Depends(get_db_cursor)
- [x] Write tests comparing context manager vs dependency injection
- [x] Document pros/cons of each approach in comments
- [x] Make decision on which pattern to use going forward

## Phase 7: Update Integration Tests
- [x] Update test_integration.py mock patches for new structure
- [x] Ensure test_complete_liquidations_flow works
- [x] Ensure test_complete_symbols_flow works
- [x] Ensure test_complete_liquidation_orders_flow works
- [x] Verify test_concurrent_requests handles new patterns
- [x] Fix test_error_handling_integration for new error handler

## Phase 8: Performance and Connection Optimization
- [ ] Research if mysql.connector supports connection pooling
- [ ] Implement connection pool if beneficial
- [ ] Add connection timeout configuration
- [ ] Add retry logic for transient connection failures
- [ ] Profile before/after to measure performance impact

## Phase 9: Documentation Updates
- [x] Update CLAUDE.md with:
  - [x] New database utilities documentation
  - [x] Code examples using the utilities
  - [x] Updated architecture section
  - [x] Migration guide for new endpoints
- [x] Add comprehensive docstrings to all utilities
- [x] Document the refactoring in CLAUDE.md

## Phase 10: Final Validation
- [x] Run full test suite: `pytest -v`
- [x] Check coverage: `pytest --cov=app --cov-report=html`
- [x] Ensure 100% coverage on new utilities
- [ ] Manually test with real database
- [x] Calculate actual code reduction:
  - [x] Count lines before refactoring
  - [x] Count lines after refactoring
  - [x] Document percentage reduction
- [x] Run linting if configured
- [x] Verify no regression in functionality

## Success Metrics
- ✅ All 73 tests pass (57 original + 16 new)
- ✅ 100% test coverage achieved
- ✅ Endpoint size reductions:
  - /api/symbols: 33 → 13 lines (61% reduction)
  - /api/liquidations: 96 → 83 lines (14% reduction)
  - /api/liquidation-orders: 128 → 113 lines (12% reduction)
- ✅ No changes to API responses or behavior
- ✅ Consistent error messages across all endpoints
- ✅ Improved maintainability and testability

## Implementation Notes
- Refactor one endpoint at a time
- Keep original code in comments until fully tested
- Each phase should be a separate commit
- If issues arise, be prepared to rollback
- Consider keeping both patterns temporarily for comparison

## Code Reduction Estimates
- /api/symbols: ~35 lines → ~15 lines
- /api/liquidations: ~95 lines → ~40 lines  
- /api/liquidation-orders: ~128 lines → ~60 lines
- Total reduction: ~258 lines → ~115 lines (55% reduction)