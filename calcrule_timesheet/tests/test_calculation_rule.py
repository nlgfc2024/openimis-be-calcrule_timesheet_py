from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase

from contribution_plan.models import PaymentPlan
from core.test_helpers import LogInHelper
from social_protection.models import BenefitPlan, Beneficiary, GroupBeneficiary, BeneficiaryStatus
from social_protection.services import BeneficiaryService, GroupBeneficiaryService
from social_protection.tests.test_helpers import (
    create_benefit_plan,
    create_individual,
    create_project,
    create_group,
    add_individual_to_group,
)

from calcrule_timesheet.calculation_rule import TimesheetCalculationRule
from calcrule_timesheet.strategies import (
    IndividualTimesheetStrategy,
    GroupTimesheetStrategy,
    BaseTimesheetStrategy
)
from calcrule_timesheet.tests.data import (
    payment_plan_timesheet_individual,
    payment_plan_timesheet_individual_with_limit,
    payment_plan_timesheet_group,
    payment_plan_timesheet_group_with_limit,
)
from calcrule_timesheet.tests.test_helpers import (
    create_time_entry,
    create_multiple_time_entries,
    calculate_expected_payment,
    merge_dicts,
)


class TimesheetCalculationRuleTest(TestCase):
    """Test the TimesheetCalculationRule class"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.calculation_rule = TimesheetCalculationRule

    def test_calculation_rule_metadata(self):
        """Test that the calculation rule has correct metadata"""
        self.assertEqual(self.calculation_rule.calculation_rule_name, "Calculation rule: timesheet")
        self.assertEqual(self.calculation_rule.type, "timesheet")
        self.assertEqual(self.calculation_rule.sub_type, "benefit_plan")
        self.assertEqual(self.calculation_rule.status, "active")
        self.assertIsNotNone(self.calculation_rule.uuid)
        self.assertEqual(self.calculation_rule.version, 1)

    def test_run_calculation_rules_with_payment_plan(self):
        """Test that run_calculation_rules works with PaymentPlan instance"""
        payment_plan = Mock(spec=PaymentPlan)
        with patch.object(self.calculation_rule, 'calculate_if_active_for_object') as mock_calc:
            mock_calc.return_value = True
            result = self.calculation_rule.run_calculation_rules(None, payment_plan, self.user, {})
            self.assertTrue(result)
            mock_calc.assert_called_once_with(payment_plan)

    def test_run_calculation_rules_with_non_payment_plan(self):
        """Test that run_calculation_rules returns False for non-PaymentPlan"""
        non_payment_plan = Mock()
        result = self.calculation_rule.run_calculation_rules(None, non_payment_plan, self.user, {})
        self.assertFalse(result)

    def test_get_payment_cycle_parameters(self):
        """Test extraction of payment cycle parameters"""
        kwargs = {
            'user_id': 123,
            'start_date': '2023-01-01',
            'end_date': '2023-12-31',
            'payment_cycle': 'monthly'
        }
        user_id, start_date, end_date, payment_cycle = \
            self.calculation_rule.get_payment_cycle_parameters(**kwargs)

        self.assertEqual(user_id, 123)
        self.assertEqual(start_date, '2023-01-01')
        self.assertEqual(end_date, '2023-12-31')
        self.assertEqual(payment_cycle, 'monthly')


class BaseTimesheetStrategyTest(TestCase):
    """Test the BaseTimesheetStrategy calculation logic"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.benefit_plan_individual = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'ITIME001', 'type': "INDIVIDUAL"}
        )
        cls.project = create_project(
            'Test Timesheet Project',
            cls.benefit_plan_individual,
            cls.user.username
        )
        cls.individual = create_individual(cls.user.username)
        cls.beneficiary_service = BeneficiaryService(cls.user)

    def create_beneficiary_with_project(self):
        """Helper to create a beneficiary enrolled in the project"""
        beneficiary_payload = {
            "individual_id": self.individual.id,
            "benefit_plan_id": self.benefit_plan_individual.id,
            "status": BeneficiaryStatus.ACTIVE,
            "project_id": self.project.id,
        }
        result = self.beneficiary_service.create(beneficiary_payload)
        self.assertTrue(result.get('success', False))
        uuid = result.get('data', {}).get('uuid')
        return Beneficiary.objects.get(uuid=uuid)

    def test_calculate_timesheet_payment_full_days(self):
        """Test calculation with 100% completion for multiple days"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
            {'day_number': 3, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        expected = calculate_expected_payment(entries_data, base_day_rate)
        self.assertEqual(payment, expected)
        self.assertEqual(payment, 150.0)
        self.assertFalse(BaseTimesheetStrategy.is_exceed_limit)

    def test_calculate_timesheet_payment_partial_days(self):
        """Test calculation with partial completion percentages"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 50},
            {'day_number': 3, 'percent_complete': 75},
            {'day_number': 4, 'percent_complete': 0},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        expected = calculate_expected_payment(entries_data, base_day_rate)
        self.assertEqual(payment, expected)
        self.assertEqual(payment, 112.5)

    def test_calculate_timesheet_payment_no_entries(self):
        """Test calculation with no time entries returns zero"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 0.0)

    def test_calculate_timesheet_payment_with_limit_not_exceeded(self):
        """Test calculation with limit that is not exceeded"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0
        limit = 200.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, limit
        )

        self.assertEqual(payment, 100.0)
        self.assertFalse(BaseTimesheetStrategy.is_exceed_limit)

    def test_calculate_timesheet_payment_with_limit_exceeded(self):
        """Test calculation with limit that is exceeded"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 50.0
        limit = 100.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
            {'day_number': 3, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, limit
        )

        self.assertEqual(payment, 150.0)
        self.assertTrue(BaseTimesheetStrategy.is_exceed_limit)

    def test_calculate_timesheet_payment_edge_case_zero_rate(self):
        """Test calculation with zero base day rate"""
        beneficiary = self.create_beneficiary_with_project()
        base_day_rate = 0.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, base_day_rate, None
        )

        self.assertEqual(payment, 0.0)


class IndividualTimesheetStrategyTest(TestCase):
    """Test the IndividualTimesheetStrategy"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.benefit_plan = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'ITIME002', 'type': "INDIVIDUAL"}
        )
        cls.project = create_project(
            'Individual Strategy Test Project',
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

    def test_individual_strategy_type(self):
        """Test that strategy has correct type"""
        self.assertEqual(IndividualTimesheetStrategy.TYPE, "INDIVIDUAL")
        self.assertEqual(IndividualTimesheetStrategy.BENEFICIARY_TYPE, "beneficiary")
        self.assertEqual(IndividualTimesheetStrategy.BENEFICIARY_OBJECT, Beneficiary)

    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BillService')
    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.BenefitConsumptionService')
    def test_individual_strategy_convert(self, mock_benefit_service, mock_bill_service):
        """Test individual strategy conversion to bill and benefit"""
        beneficiary = self.create_beneficiary_with_project()

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 50},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

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

        payment_plan = Mock(spec=PaymentPlan)
        payment_plan.benefit_plan = self.benefit_plan
        kwargs = {
            'beneficiary': beneficiary,
            'amount': 75.0,
            'user': self.user,
            'end_date': '2023-12-31',
            'payment_cycle': 'monthly',
            'payroll': Mock(id=789),
        }

        IndividualTimesheetStrategy.convert(payment_plan, **kwargs)

        mock_bill_service.bill_create.assert_called_once()


class GroupTimesheetStrategyTest(TestCase):
    """Test the GroupTimesheetStrategy"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.benefit_plan = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'GTIME001', 'type': "GROUP"}
        )
        cls.project = create_project(
            'Group Strategy Test Project',
            cls.benefit_plan,
            cls.user.username
        )
        cls.individual = create_individual(cls.user.username)
        cls.group = create_group(cls.user.username)
        add_individual_to_group(cls.user.username, cls.individual, cls.group)
        cls.group_beneficiary_service = GroupBeneficiaryService(cls.user)

    def create_group_beneficiary_with_project(self):
        """Helper to create a group beneficiary enrolled in the project"""
        group_beneficiary_payload = {
            "group_id": self.group.id,
            "benefit_plan_id": self.benefit_plan.id,
            "status": BeneficiaryStatus.ACTIVE,
            "project_id": self.project.id,
        }
        result = self.group_beneficiary_service.create(group_beneficiary_payload)
        self.assertTrue(result.get('success', False))
        uuid = result.get('data', {}).get('uuid')
        return GroupBeneficiary.objects.get(uuid=uuid)

    def test_group_strategy_type(self):
        """Test that strategy has correct type"""
        self.assertEqual(GroupTimesheetStrategy.TYPE, "GROUP")
        self.assertEqual(GroupTimesheetStrategy.BENEFICIARY_TYPE, "group")
        self.assertEqual(GroupTimesheetStrategy.BENEFICIARY_OBJECT, GroupBeneficiary)

    def test_group_timesheet_calculation(self):
        """Test calculation for group beneficiary"""
        group_beneficiary = self.create_group_beneficiary_with_project()
        base_day_rate = 100.0

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 80},
            {'day_number': 3, 'percent_complete': 60},
        ]
        create_multiple_time_entries(
            group_beneficiary,
            entries_data,
            self.user.username,
            is_group=True
        )

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            group_beneficiary, base_day_rate, None
        )

        expected = calculate_expected_payment(entries_data, base_day_rate)
        self.assertEqual(payment, expected)
        self.assertEqual(payment, 240.0)


class TimesheetLimitAndTaskTest(TestCase):
    """Test limit checking and task creation functionality"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.benefit_plan = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'ILIMIT001', 'type': "INDIVIDUAL"}
        )
        cls.project = create_project(
            'Limit Test Project',
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

    @patch('calcrule_timesheet.strategies.timesheet_base_strategy.TaskService')
    def test_create_task_after_exceeding_limit(self, mock_task_service):
        """Test that task is created when payment exceeds limit"""
        beneficiary = self.create_beneficiary_with_project()

        convert_results = {
            'bill_data': {'code': 'TEST-001'},
            'user': self.user
        }
        convert_results_benefit = {'benefit_data': {}}
        payroll = Mock(id=999)

        BaseTimesheetStrategy.create_task_after_exceeding_limit(
            convert_results=convert_results,
            convert_results_benefit=convert_results_benefit,
            payroll=payroll
        )

        mock_task_service.assert_called_once()
        mock_task_instance = mock_task_service.return_value
        mock_task_instance.create.assert_called_once()

    def test_limit_checking_logic(self):
        """Test that is_exceed_limit flag is set correctly"""
        beneficiary = self.create_beneficiary_with_project()

        entries_data = [
            {'day_number': 1, 'percent_complete': 100},
            {'day_number': 2, 'percent_complete': 100},
            {'day_number': 3, 'percent_complete': 100},
        ]
        create_multiple_time_entries(beneficiary, entries_data, self.user.username)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, 50.0, 100.0
        )
        self.assertTrue(BaseTimesheetStrategy.is_exceed_limit)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, 50.0, 200.0
        )
        self.assertFalse(BaseTimesheetStrategy.is_exceed_limit)

        payment = BaseTimesheetStrategy._calculate_timesheet_payment(
            beneficiary, 50.0, None
        )
        self.assertFalse(BaseTimesheetStrategy.is_exceed_limit)
