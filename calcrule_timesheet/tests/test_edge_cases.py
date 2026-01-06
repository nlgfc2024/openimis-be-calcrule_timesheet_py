from unittest.mock import Mock
from django.test import TestCase
from django.core.exceptions import ValidationError

from core.test_helpers import LogInHelper
from social_protection.models import Beneficiary, BeneficiaryStatus
from social_protection.services import BeneficiaryService
from social_protection.tests.test_helpers import (
    create_benefit_plan,
    create_individual,
    create_project,
)

from calcrule_timesheet.strategies import BaseTimesheetStrategy
from calcrule_timesheet.tests.test_helpers import (
    create_time_entry,
    create_multiple_time_entries,
)


class TimesheetEdgeCaseTest(TestCase):
    """Test edge cases and boundary conditions"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.benefit_plan = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'EDGE001', 'type': "INDIVIDUAL"}
        )
        cls.project = create_project(
            'Edge Case Test Project',
            cls.benefit_plan,
            cls.user.username
        )
        cls.individual = create_individual(cls.user.username)
        cls.beneficiary_service = BeneficiaryService(cls.user)

    def create_beneficiary_with_project(self):
        """Helper to create a beneficiary enrolled in the project"""
        beneficiary_payload = {
            "individual_id": self.individual.id,
            "benefit_plan_id": self.benefit_plan.id,
            "status": BeneficiaryStatus.ACTIVE,
            "project_id": self.project.id,
        }
        result = self.beneficiary_service.create(beneficiary_payload)
        self.assertTrue(result.get('success', False))
        uuid = result.get('data', {}).get('uuid')
        return Beneficiary.objects.get(uuid=uuid)

    def test_zero_percent_completion(self):
        """Test entries with 0% completion"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 0},
            {'day_number': 2, 'percent_complete': 0},
            {'day_number': 3, 'percent_complete': 0},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 0.0)

    def test_mixed_zero_and_full_completion(self):
        """Test mix of 0% and 100% entries"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 0},
            {'day_number': 3, 'percent_complete': 100},
            {'day_number': 4, 'percent_complete': 0},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 100.0)

    def test_very_high_base_day_rate(self):
        """Test calculation with very high day rate"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 10000.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 50},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 15000.0)

    def test_very_small_base_day_rate(self):
        """Test calculation with fractional day rate"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 0.01

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertAlmostEqual(payment, 0.02, places=2)

    def test_all_partial_percentages(self):
        """Test with various partial completion percentages"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 100.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 25},
            {'day_number': 2, 'percent_complete': 33},
            {'day_number': 3, 'percent_complete': 66},
            {'day_number': 4, 'percent_complete': 99},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        expected = (25 + 33 + 66 + 99)
        self.assertEqual(payment, expected)

    def test_limit_exactly_at_payment_amount(self):
        """Test when limit exactly equals calculated payment"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, 100.0
        )

        self.assertEqual(payment, 100.0)
        self.assertFalse(BaseTimesheetStrategy.is_exceed_limit)

    def test_limit_one_unit_below_payment(self):
        """Test when limit is just below payment amount"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, 99.99
        )

        self.assertEqual(payment, 100.0)
        self.assertTrue(BaseTimesheetStrategy.is_exceed_limit)

    def test_single_time_entry(self):
        """Test calculation with only one time entry"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        time_entry = create_time_entry(beneficiary, 1, 100, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 50.0)

    def test_many_time_entries(self):
        """Test calculation with many time entries (full project duration)"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': i, 'percent_complete': 100}
            for i in range(1, 91)
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 4500.0)

    def test_time_entry_validation_day_number_exceeds_working_days(self):
        """Test that time entry validation works for day_number"""
        beneficiary = self.create_beneficiary_with_project()

        with self.assertRaises(ValidationError):
            time_entry = create_time_entry(
                beneficiary,
                day_number=999,
                percent_complete=100,
                username=self.user.username
            )
            time_entry.full_clean()

    def test_decimal_precision_in_calculation(self):
        """Test that decimal precision is maintained in calculations"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 33.33

        entries_data = [
            {'day_number': 1, 'percent_complete': 33},
            {'day_number': 2, 'percent_complete': 67},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        expected = (0.33 * 33.33) + (0.67 * 33.33)
        self.assertAlmostEqual(payment, expected, places=2)

    def test_beneficiary_without_project(self):
        """Test calculation for beneficiary without project assignment"""
        beneficiary_payload = {
            "individual_id": self.individual.id,
            "benefit_plan_id": self.benefit_plan.id,
            "status": BeneficiaryStatus.ACTIVE,
        }
        result = self.beneficiary_service.create(beneficiary_payload)
        self.assertTrue(result.get('success', False))
        uuid = result.get('data', {}).get('uuid')
        beneficiary = Beneficiary.objects.get(uuid=uuid)

        base_day_rate = 50.0

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 0.0)

    def test_sparse_time_entries(self):
        """Test with non-consecutive day numbers"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 5, 'percent_complete': 100},
            {'day_number': 10, 'percent_complete': 100},
            {'day_number': 20, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 200.0)
