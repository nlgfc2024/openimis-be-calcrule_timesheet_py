from django.test import TestCase

from core.test_helpers import LogInHelper
from social_protection.models import Beneficiary, BeneficiaryStatus
from social_protection.services import BeneficiaryService
from social_protection.tests.test_helpers import (
    create_benefit_plan,
    create_individual,
)
from project_social_protection.tests.test_helpers import create_project
from project_social_protection.models import (
    BeneficiaryProjectEnrollment,
    GroupBeneficiaryProjectEnrollment,
    ProjectStatus,
)

from calcrule_timesheet.strategies.timesheet_individual_strategy import IndividualTimesheetStrategy
from calcrule_timesheet.strategies.timesheet_group_strategy import GroupTimesheetStrategy
from calcrule_timesheet.tests.test_helpers import create_enrollment

STRATEGY_LOGGER = 'calcrule_timesheet.strategies.timesheet_base_strategy'


class ResolveEnrollmentsTest(TestCase):
    """
    PayrollService sends the payroll's filter criteria as `beneficiaries_queryset`.
    These tests pin that the strategy narrows the enrollment set by it, so a payroll
    scoped to one project does not pay the whole benefit plan.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api()
        cls.benefit_plan = create_benefit_plan(
            cls.user.username,
            payload_override={'code': 'SCOPE01', 'type': "INDIVIDUAL"},
        )
        cls.project_a = create_project(
            'Scoping Project A',
            cls.benefit_plan,
            cls.user.username,
            status=ProjectStatus.COMPLETED,
        )
        cls.project_b = create_project(
            'Scoping Project B',
            cls.benefit_plan,
            cls.user.username,
            status=ProjectStatus.COMPLETED,
        )

    def setUp(self):
        super().setUp()
        self.beneficiary_a = self._beneficiary('ScopeA')
        self.beneficiary_b = self._beneficiary('ScopeB')
        self.enrollment_a = create_enrollment(self.beneficiary_a, self.project_a, self.user)
        self.enrollment_b = create_enrollment(self.beneficiary_b, self.project_b, self.user)
        self.payment_plan = self._payment_plan_stub()

    def _beneficiary(self, first_name):
        individual = create_individual(
            self.user.username, payload_override={'first_name': first_name}
        )
        result = BeneficiaryService(self.user).create({
            "individual_id": individual.id,
            "benefit_plan_id": self.benefit_plan.id,
            "status": BeneficiaryStatus.ACTIVE,
        })
        self.assertTrue(result.get('success', False), result.get('detail', 'No details'))
        return Beneficiary.objects.get(uuid=result['data']['uuid'])

    def _payment_plan_stub(self):
        benefit_plan = self.benefit_plan

        class _PaymentPlan:
            pass

        _PaymentPlan.benefit_plan = benefit_plan
        return _PaymentPlan()

    def test_narrows_to_the_beneficiaries_payroll_selected(self):
        resolved = IndividualTimesheetStrategy._resolve_enrollments(
            self.payment_plan,
            beneficiaries_queryset=Beneficiary.objects.filter(pk=self.beneficiary_a.pk),
        )
        self.assertEqual([e.pk for e in resolved], [self.enrollment_a.pk])

    def test_without_the_kwarg_every_enrollment_is_paid(self):
        resolved = IndividualTimesheetStrategy._resolve_enrollments(self.payment_plan)
        self.assertCountEqual(
            [e.pk for e in resolved], [self.enrollment_a.pk, self.enrollment_b.pk]
        )

    def test_empty_selection_pays_nobody(self):
        """An empty queryset must stay empty, not fall back to 'everyone'."""
        resolved = IndividualTimesheetStrategy._resolve_enrollments(
            self.payment_plan,
            beneficiaries_queryset=Beneficiary.objects.none(),
        )
        self.assertEqual(list(resolved), [])

    def test_explicit_enrollments_queryset_wins(self):
        resolved = IndividualTimesheetStrategy._resolve_enrollments(
            self.payment_plan,
            enrollments_queryset=BeneficiaryProjectEnrollment.objects.filter(
                pk=self.enrollment_b.pk
            ),
            beneficiaries_queryset=Beneficiary.objects.filter(pk=self.beneficiary_a.pk),
        )
        self.assertEqual([e.pk for e in resolved], [self.enrollment_b.pk])

    def test_explicit_empty_enrollments_queryset_stays_empty(self):
        resolved = IndividualTimesheetStrategy._resolve_enrollments(
            self.payment_plan,
            enrollments_queryset=BeneficiaryProjectEnrollment.objects.none(),
        )
        self.assertEqual(list(resolved), [])

    def test_mismatched_model_is_ignored_rather_than_filtered_on(self):
        """
        PayrollService always builds a Beneficiary queryset, even for a GROUP plan.
        The group strategy must not filter its GroupBeneficiary FK with it.
        """
        with self.assertLogs(STRATEGY_LOGGER, level='WARNING') as logs:
            resolved = GroupTimesheetStrategy._resolve_enrollments(
                self.payment_plan,
                beneficiaries_queryset=Beneficiary.objects.filter(pk=self.beneficiary_a.pk),
            )
        self.assertIs(resolved.model, GroupBeneficiaryProjectEnrollment)
        self.assertNotIn('group_beneficiary', str(resolved.query).lower().split('where')[-1])
        self.assertIn('expected GroupBeneficiary', logs.output[0])
