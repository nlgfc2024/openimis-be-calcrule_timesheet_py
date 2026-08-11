from unittest.mock import Mock
from django.test import TestCase
from django.core.exceptions import ValidationError

from core.test_helpers import LogInHelper
from social_protection.models import Beneficiary, BeneficiaryStatus
from social_protection.services import BeneficiaryService
from social_protection.tests.test_helpers import (
    create_benefit_plan,
    create_individual,
)
from project_social_protection.tests.test_helpers import create_project

from calcrule_timesheet.strategies import BaseTimesheetStrategy
from calcrule_timesheet.tests.test_helpers import (
    create_enrollment,
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

    def create_beneficiary_with_enrollment(self):
        """Helper to create a beneficiary enrolled in the project"""
        beneficiary_payload = {
            "individual_id": self.individual.id,
            "benefit_plan_id": self.benefit_plan.id,
            "status": BeneficiaryStatus.ACTIVE,
        }
        result = self.beneficiary_service.create(beneficiary_payload)
        self.assertTrue(result.get('success', False), result.get('detail', 'No details'))
        uuid = result.get('data', {}).get('uuid')
        beneficiary = Beneficiary.objects.get(uuid=uuid)
        enrollment = create_enrollment(beneficiary, self.project, self.user)
        return enrollment

    def test_zero_percent_completion(self):
        """Test entries with 0% completion"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 0},
            {'day_number': 2, 'percent_complete': 0},
            {'day_number': 3, 'percent_complete': 0},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertEqual(payment, 0.0)

    def test_mixed_zero_and_full_completion(self):
        """Test mix of 0% and 100% entries"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 0},
            {'day_number': 3, 'percent_complete': 100},
            {'day_number': 4, 'percent_complete': 0},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertEqual(payment, 100.0)

    def test_very_high_base_day_rate(self):
        """Test calculation with very high day rate"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 10000.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 50},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertEqual(payment, 15000.0)

    def test_very_small_base_day_rate(self):
        """Test calculation with fractional day rate"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 0.01

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertAlmostEqual(payment, 0.02, places=2)

    def test_all_partial_percentages(self):
        """Test with various partial completion percentages"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 100.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 25},
            {'day_number': 2, 'percent_complete': 33},
            {'day_number': 3, 'percent_complete': 66},
            {'day_number': 4, 'percent_complete': 99},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        expected = (25 + 33 + 66 + 99)
        self.assertEqual(payment, expected)

    def test_single_time_entry(self):
        """Test calculation with only one time entry"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 50.0

        create_time_entry(enrollment, 1, 100, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertEqual(payment, 50.0)

    def test_many_time_entries(self):
        """Test calculation with many time entries (full project duration)"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': i, 'percent_complete': 100}
            for i in range(1, 91)
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertEqual(payment, 4500.0)

    def test_time_entry_validation_day_number_exceeds_working_days(self):
        """Test that time entry validation works for day_number"""
        enrollment = self.create_beneficiary_with_enrollment()

        with self.assertRaises(ValidationError):
            time_entry = create_time_entry(
                enrollment,
                day_number=999,
                percent_complete=100,
                username=self.user.username
            )
            time_entry.full_clean()

    def test_decimal_precision_in_calculation(self):
        """Test that decimal precision is maintained in calculations"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 33.33

        entries_data = [
            {'day_number': 1, 'percent_complete': 33},
            {'day_number': 2, 'percent_complete': 67},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        expected = (0.33 * 33.33) + (0.67 * 33.33)
        self.assertAlmostEqual(payment, expected, places=2)

    def test_enrollment_without_time_entries(self):
        """Test calculation for enrollment without time entries"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 50.0

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertEqual(payment, 0.0)

    def test_sparse_time_entries(self):
        """Test with non-consecutive day numbers"""
        enrollment = self.create_beneficiary_with_enrollment()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 5, 'percent_complete': 100},
            {'day_number': 10, 'percent_complete': 100},
            {'day_number': 20, 'percent_complete': 100},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            enrollment, base_day_rate
        )

        self.assertEqual(payment, 200.0)
