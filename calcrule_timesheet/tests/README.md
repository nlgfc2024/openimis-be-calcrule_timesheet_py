# Timesheet Calculation Rule Tests

This directory contains comprehensive unit and integration tests for the timesheet calculation rule module.

## Test Files

### `data.py`
Test fixtures and data for payment plans with different configurations:
- Individual and group payment plans
- Payment plans with and without limits
- Various base day rate configurations

### `test_helpers.py`
Helper functions for test setup:
- `create_time_entry()` - Create single ProjectTimeEntry
- `create_multiple_time_entries()` - Create multiple time entries at once
- `calculate_expected_payment()` - Calculate expected payment for verification
- `merge_dicts()` - Utility for merging test data dictionaries

### `test_calculation_rule.py`
Core unit tests for calculation rule components:

**TimesheetCalculationRuleTest**
- Tests calculation rule metadata (name, type, UUID, etc.)
- Tests run_calculation_rules with various inputs
- Tests payment cycle parameter extraction

**BaseTimesheetStrategyTest**
- Tests core timesheet payment calculation logic
- Tests with full days (100% completion)
- Tests with partial days (various percentages)
- Tests with no time entries
- Tests limit checking (exceeded and not exceeded)
- Tests edge cases (zero rate, etc.)

**IndividualTimesheetStrategyTest**
- Tests individual beneficiary strategy
- Tests conversion to bills and benefits
- Verifies correct beneficiary type handling

**GroupTimesheetStrategyTest**
- Tests group beneficiary strategy
- Tests group-specific calculation logic
- Verifies correct group beneficiary type handling

**TimesheetLimitAndTaskTest**
- Tests limit checking logic
- Tests task creation when limit is exceeded
- Tests is_exceed_limit flag behavior

### `test_integration.py`
End-to-end integration tests:

**TimesheetCalculationIntegrationTest**
- Complete calculation flow for individual beneficiaries
- Complete calculation flow for group beneficiaries
- Payment with limit exceeded (triggers task creation)
- Multiple beneficiaries calculation in single run
- Tests full integration with bill/benefit creation services

### `test_edge_cases.py`
Boundary conditions and edge cases:

**TimesheetEdgeCaseTest**
- Zero percent completion entries
- Mixed zero and full completion
- Very high and very low base day rates
- All partial percentages
- Limit exactly at payment amount
- Limit just below payment amount
- Single time entry
- Many time entries (full project duration)
- Time entry validation
- Decimal precision in calculations
- Beneficiaries without project assignment
- Sparse/non-consecutive time entries

## Running the Tests

From the openIMIS backend root directory:

```bash
cd openimis-be_py/openIMIS
workon openimis
python manage.py test calcrule_timesheet --keepdb
```

To run specific test classes:

```bash
python manage.py test calcrule_timesheet.tests.test_calculation_rule.BaseTimesheetStrategyTest --keepdb
python manage.py test calcrule_timesheet.tests.test_integration --keepdb
python manage.py test calcrule_timesheet.tests.test_edge_cases --keepdb
```

## Test Coverage

The test suite covers:
- ✅ Calculation rule initialization and metadata
- ✅ Time entry aggregation and payment calculation
- ✅ Individual beneficiary strategy
- ✅ Group beneficiary strategy
- ✅ Limit checking and enforcement
- ✅ Task creation when limits exceeded
- ✅ Bill and benefit conversion
- ✅ Payroll attachment
- ✅ Multiple beneficiaries in a single calculation run
- ✅ Edge cases and boundary conditions
- ✅ Decimal precision handling
- ✅ Validation of time entries

## Test Data Dependencies

Tests depend on:
- `social_protection` module (Beneficiary, BenefitPlan, Project models)
- `individual` module (Individual, Group models)
- `contribution_plan` module (PaymentPlan model)
- `core` module (User model, test helpers)
- `invoice` module (Bill model, BillService)
- `payroll` module (BenefitConsumptionService, PayrollService)
- `tasks_management` module (Task model, TaskService)

Most external services are mocked in tests to isolate the calculation logic.
