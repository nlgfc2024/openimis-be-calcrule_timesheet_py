from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from contribution_plan.services import PaymentPlan as PaymentPlanService
from contribution_plan.models import PaymentPlan
from core.test_helpers import LogInHelper
from social_protection.models import Beneficiary, GroupBeneficiary, BeneficiaryStatus
from project_social_protection.models import ProjectStatus
from social_protection.services import BeneficiaryService, GroupBeneficiaryService
from social_protection.tests.test_helpers import (
    create_benefit_plan,
    create_individual,
    create_project,
    create_group,
    add_individual_to_group,
)

from calcrule_timesheet.calculation_rule import TimesheetCalculationRule
from calcrule_timesheet.tests.test_helpers import (
    create_enrollment,
    create_multiple_time_entries,
    calculate_expected_payment,
    merge_dicts,
)
from calcrule_timesheet.tests.data import (
    payment_plan_timesheet_individual,
    payment_plan_timesheet_group,
)


class TimesheetCalculationIntegrationTest(TestCase):
    """Integration tests for the complete timesheet calculation flow"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.calculation_rule = TimesheetCalculationRule()

        cls.benefit_plan_individual = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'INTG001', 'type': "INDIVIDUAL"}
        )
        cls.project_individual = create_project(
            'Integration Test Individual Project',
            cls.benefit_plan_individual,
            cls.user.username,
            status=ProjectStatus.COMPLETED
        )

        cls.benefit_plan_group = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'INTG002', 'type': "GROUP"}
        )
        cls.project_group = create_project(
            'Integration Test Group Project',
            cls.benefit_plan_group,
            cls.user.username,
            status=ProjectStatus.COMPLETED
        )

    def create_individual_beneficiary_with_enrollment(self, individual):
        """Helper to create individual beneficiary with enrollment"""
        service = BeneficiaryService(self.user)
        beneficiary_payload = {
            "individual_id": individual.id,
            "benefit_plan_id": self.benefit_plan_individual.id,
            "status": BeneficiaryStatus.ACTIVE,
        }
        result = service.create(beneficiary_payload)
        self.assertTrue(result.get('success', False), result.get('detail', 'No details'))
        uuid = result.get('data', {}).get('uuid')
        beneficiary = Beneficiary.objects.get(uuid=uuid)
        enrollment = create_enrollment(beneficiary, self.project_individual, self.user)
        return enrollment

    def create_group_beneficiary_with_enrollment(self, group):
        """Helper to create group beneficiary with enrollment"""
        service = GroupBeneficiaryService(self.user)
        group_beneficiary_payload = {
            "group_id": group.id,
            "benefit_plan_id": self.benefit_plan_group.id,
            "status": BeneficiaryStatus.ACTIVE,
        }
        result = service.create(group_beneficiary_payload)
        self.assertTrue(result.get('success', False), result.get('detail', 'No details'))
        uuid = result.get('data', {}).get('uuid')
        group_beneficiary = GroupBeneficiary.objects.get(uuid=uuid)
        enrollment = create_enrollment(group_beneficiary, self.project_group, self.user, is_group=True)
        return enrollment

    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.PayrollService')
    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BenefitConsumptionService')
    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BillService')
    def test_end_to_end_individual_calculation(
        self, mock_bill_service, mock_benefit_service, mock_payroll_service
    ):
        """Test complete calculation flow for individual beneficiary"""
        individual = create_individual(self.user.username, payload_override={'first_name': 'IntgTest1'})
        enrollment = self.create_individual_beneficiary_with_enrollment(individual)

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 75},
            {'day_number': 3, 'percent_complete': 50},
            {'day_number': 4, 'percent_complete': 100},
            {'day_number': 5, 'percent_complete': 80},
        ]
        create_multiple_time_entries(enrollment, entries_data, self.user.username)

        base_day_rate = 50.0
        expected_payment = calculate_expected_payment(entries_data, base_day_rate)

        mock_bill_service.bill_create.return_value = {
            'success': True,
            'data': {'id': 123}
        }
        mock_benefit_instance = MagicMock()
        mock_benefit_instance.create.return_value = {
            'success': True,
            'data': {'id': 456}
        }
        mock_benefit_service.return_value = mock_benefit_instance

        payment_plan_data = merge_dicts(
            payment_plan_timesheet_individual,
            {
                'benefit_plan_id': self.benefit_plan_individual.id,
                'calculation': self.calculation_rule.uuid,
                'json_ext': {
                    'calculation_rule': {
                        'base_day_rate': str(base_day_rate)
                    }
                }
            }
        )

        payment_plan_service = PaymentPlanService(self.user)
        payment_plan_payload = {
            'code': 'PP-INTG-IND-001',
            'name': 'Integration Test Individual Payment Plan',
            'calculation': str(self.calculation_rule.uuid),
            'benefit_plan_id': str(self.benefit_plan_individual.id),
            'benefit_plan_type': ContentType.objects.get_for_model(self.benefit_plan_individual),
            'periodicity': 12,
            'json_ext': payment_plan_data['json_ext']
        }
        result_pp = payment_plan_service.create(payment_plan_payload)
        self.assertTrue(result_pp.get('success', False))
        payment_plan = PaymentPlan.objects.get(id=result_pp['data']['uuid'])

        payment_cycle = Mock()
        payment_cycle.start_date = '2023-01-01'
        payment_cycle.end_date = '2023-12-31'

        payroll = Mock(id=789)
        kwargs = {
            'user_id': self.user.id,
            'start_date': '2023-01-01',
            'end_date': '2023-12-31',
            'payment_cycle': payment_cycle,
            'payroll': payroll,
        }

        result = self.calculation_rule.calculate(payment_plan, **kwargs)

        self.assertEqual(result, "Calculation and transformation into bills completed successfully.")
        mock_bill_service.bill_create.assert_called()

    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.PayrollService')
    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BenefitConsumptionService')
    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BillService')
    def test_end_to_end_group_calculation(
        self, mock_bill_service, mock_benefit_service, mock_payroll_service
    ):
        """Test complete calculation flow for group beneficiary"""
        individual = create_individual(self.user.username, payload_override={'first_name': 'GroupTest1'})
        group = create_group(self.user.username, payload_override={'code': 'GRPINTG1'})
        add_individual_to_group(self.user.username, individual, group)

        enrollment = self.create_group_beneficiary_with_enrollment(group)

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
            {'day_number': 3, 'percent_complete': 90},
        ]
        create_multiple_time_entries(
            enrollment,
            entries_data,
            self.user.username,
            is_group=True
        )

        base_day_rate = 100.0
        expected_payment = calculate_expected_payment(entries_data, base_day_rate)

        mock_bill_service.bill_create.return_value = {
            'success': True,
            'data': {'id': 234}
        }
        mock_benefit_instance = MagicMock()
        mock_benefit_instance.create.return_value = {
            'success': True,
            'data': {'id': 567}
        }
        mock_benefit_service.return_value = mock_benefit_instance

        payment_plan_data = merge_dicts(
            payment_plan_timesheet_group,
            {
                'benefit_plan_id': self.benefit_plan_group.id,
                'calculation': self.calculation_rule.uuid,
                'json_ext': {
                    'calculation_rule': {
                        'base_day_rate': str(base_day_rate)
                    }
                }
            }
        )

        payment_plan_service = PaymentPlanService(self.user)
        payment_plan_payload = {
            'code': 'PP-INTG-GRP-001',
            'name': 'Integration Test Group Payment Plan',
            'calculation': str(self.calculation_rule.uuid),
            'benefit_plan_id': str(self.benefit_plan_group.id),
            'benefit_plan_type': ContentType.objects.get_for_model(self.benefit_plan_group),
            'periodicity': 12,
            'json_ext': payment_plan_data['json_ext']
        }
        result_pp = payment_plan_service.create(payment_plan_payload)
        self.assertTrue(result_pp.get('success', False))
        payment_plan = PaymentPlan.objects.get(id=result_pp['data']['uuid'])

        payment_cycle = Mock()
        payment_cycle.start_date = '2023-01-01'
        payment_cycle.end_date = '2023-12-31'

        payroll = Mock(id=890)
        kwargs = {
            'user_id': self.user.id,
            'start_date': '2023-01-01',
            'end_date': '2023-12-31',
            'payment_cycle': payment_cycle,
            'payroll': payroll,
        }

        result = self.calculation_rule.calculate(payment_plan, **kwargs)

        self.assertEqual(result, "Calculation and transformation into bills completed successfully.")
        mock_bill_service.bill_create.assert_called()

    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.PayrollService')
    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BenefitConsumptionService')
    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BillService')
    def test_multiple_beneficiaries_calculation(
        self, mock_bill_service, mock_benefit_service, mock_payroll_service
    ):
        """Test calculation with multiple beneficiaries"""
        individuals = [
            create_individual(self.user.username, payload_override={'first_name': f'Multi{i}'})
            for i in range(3)
        ]
        enrollments = [
            self.create_individual_beneficiary_with_enrollment(individual)
            for individual in individuals
        ]

        entries_per_enrollment = [
            [
                {'day_number': 1, 'percent_complete': 100},
                {'day_number': 2, 'percent_complete': 50},
            ],
            [
                {'day_number': 1, 'percent_complete': 75},
                {'day_number': 2, 'percent_complete': 100},
                {'day_number': 3, 'percent_complete': 50},
            ],
            [
                {'day_number': 1, 'percent_complete': 100},
            ],
        ]

        for enrollment, entries_data in zip(enrollments, entries_per_enrollment):
            create_multiple_time_entries(enrollment, entries_data, self.user.username)

        base_day_rate = 50.0

        mock_bill_service.bill_create.return_value = {
            'success': True,
            'data': {'id': 123}
        }
        mock_benefit_instance = MagicMock()
        mock_benefit_instance.create.return_value = {
            'success': True,
            'data': {'id': 456}
        }
        mock_benefit_service.return_value = mock_benefit_instance

        payment_plan_data = merge_dicts(
            payment_plan_timesheet_individual,
            {
                'benefit_plan_id': self.benefit_plan_individual.id,
                'calculation': self.calculation_rule.uuid,
                'json_ext': {
                    'calculation_rule': {
                        'base_day_rate': str(base_day_rate)
                    }
                }
            }
        )

        payment_plan_service = PaymentPlanService(self.user)
        payment_plan_payload = {
            'code': 'PP-INTG-MULTI-001',
            'name': 'Integration Test Multi Payment Plan',
            'calculation': str(self.calculation_rule.uuid),
            'benefit_plan_id': str(self.benefit_plan_individual.id),
            'benefit_plan_type': ContentType.objects.get_for_model(self.benefit_plan_individual),
            'periodicity': 12,
            'json_ext': payment_plan_data['json_ext']
        }
        result_pp = payment_plan_service.create(payment_plan_payload)
        self.assertTrue(result_pp.get('success', False))
        payment_plan = PaymentPlan.objects.get(id=result_pp['data']['uuid'])

        payment_cycle = Mock()
        payment_cycle.start_date = '2023-01-01'
        payment_cycle.end_date = '2023-12-31'

        payroll = Mock(id=777)
        kwargs = {
            'user_id': self.user.id,
            'start_date': '2023-01-01',
            'end_date': '2023-12-31',
            'payment_cycle': payment_cycle,
            'payroll': payroll,
        }

        result = self.calculation_rule.calculate(payment_plan, **kwargs)

        self.assertEqual(result, "Calculation and transformation into bills completed successfully.")
        self.assertEqual(mock_bill_service.bill_create.call_count, 3)
