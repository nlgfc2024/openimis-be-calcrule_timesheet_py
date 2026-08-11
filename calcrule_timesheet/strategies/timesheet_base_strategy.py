import logging

from django.db import transaction

from calcrule_timesheet.apps import CalcruleTimesheetConfig
from core.models import User
from core.signals import register_service_signal
from invoice.models import Bill
from invoice.services import BillService
from social_protection.models import BeneficiaryStatus
from project_social_protection.models import ProjectStatus
from payroll.services import BenefitConsumptionService, PayrollService

from calcrule_timesheet.strategies.timesheet_strategy_interface import TimesheetStrategyInterface


logger = logging.getLogger(__name__)


class BaseTimesheetStrategy(TimesheetStrategyInterface):

    @classmethod
    def check_calculation(cls, calculation, payment_plan):
        return calculation.uuid == str(payment_plan.calculation)

    @classmethod
    def _resolve_enrollments(cls, payment_plan, **kwargs):
        """
        Work out which project enrollments this run should pay.

        `enrollments_queryset` is an explicit override (tests, direct callers) and wins.
        Otherwise start from every enrollment on a COMPLETED project of this benefit plan
        and narrow it by `beneficiaries_queryset` - the kwarg PayrollService actually sends,
        carrying the payroll's filter criteria (project_ids / location_ids / advanced
        criteria) and its ACTIVE-beneficiary restriction. Without that narrowing a payroll
        scoped to one project pays the whole phase.
        """
        enrollments = kwargs.get('enrollments_queryset', None)
        # `is not None`, not truthiness: evaluating an empty queryset must stay empty
        # rather than silently falling back to "everyone".
        if enrollments is not None:
            return enrollments

        enrollments = cls.ENROLLMENT_OBJECT.objects.filter(
            project__benefit_plan=payment_plan.benefit_plan,
            project__status=ProjectStatus.COMPLETED,
            is_deleted=False,
        ).select_related('project', cls.BENEFICIARY_FIELD)

        beneficiaries = kwargs.get('beneficiaries_queryset', None)
        if beneficiaries is None:
            return enrollments

        # PayrollService._select_beneficiary_based_on_criteria always builds a
        # social_protection.Beneficiary queryset, even for a GROUP benefit plan, so it can
        # be the wrong model for this strategy's enrollment FK. Filtering on a mismatched
        # model would quietly pay nobody; keep the unnarrowed set and say so instead.
        if getattr(beneficiaries, 'model', None) is not cls.BENEFICIARY_OBJECT:
            logger.warning(
                "%s: ignoring beneficiaries_queryset of %s, expected %s - "
                "payroll filter criteria will not be applied.",
                cls.__name__,
                getattr(beneficiaries, 'model', type(beneficiaries)).__name__,
                cls.BENEFICIARY_OBJECT.__name__,
            )
            return enrollments

        return enrollments.filter(**{f"{cls.BENEFICIARY_FIELD}__in": beneficiaries})

    @classmethod
    def calculate(cls, calculation, payment_plan, **kwargs):
        payroll = kwargs.get('payroll', None)
        enrollments = cls._resolve_enrollments(payment_plan, **kwargs)

        payment_plan_parameters = payment_plan.json_ext
        user_id, start_date, end_date, payment_cycle = \
            calculation.get_payment_cycle_parameters(**kwargs)
        user = User.objects.filter(id=user_id).first()

        base_day_rate = float(payment_plan_parameters['calculation_rule']['base_day_rate'])

        for enrollment in enrollments:
            calculated_payment = cls._calculate_timesheet_payment(
                enrollment, base_day_rate
            )

            beneficiary = getattr(enrollment, cls.BENEFICIARY_FIELD)
            additional_params = {
                f"{cls.BENEFICIARY_TYPE}": beneficiary,
                "enrollment": enrollment,
                "amount": calculated_payment,
                "user": user,
                "end_date": end_date,
                "payment_cycle": payment_cycle,
                "payroll": payroll,
            }
            calculation.run_convert(
                payment_plan,
                **additional_params
            )
        return "Calculation and transformation into bills completed successfully."

    @classmethod
    def _calculate_timesheet_payment(cls, enrollment, base_day_rate):
        time_entries = enrollment.time_entries.filter(is_deleted=False)

        total_payment = sum(
            (entry.percent_complete / 100.0) * base_day_rate
            for entry in time_entries
        )

        return total_payment

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        entity = kwargs.get('entity', None)
        amount = kwargs.get('amount', None)
        payroll = kwargs.get('payroll', None)
        end_date = kwargs.get('end_date', None)
        converter = kwargs.get('converter')
        converter_item = kwargs.get('converter_item')
        converter_benefit = kwargs.get('converter_benefit')
        payment_cycle = kwargs.get('payment_cycle')
        convert_results = cls._convert_entity_to_bill(
            converter, converter_item, payment_plan, entity, amount, end_date, payment_cycle
        )
        convert_results['user'] = kwargs.get('user', None)
        convert_results_benefit = cls._convert_entity_to_benefit(
            converter_benefit, payment_plan, entity, amount, payment_cycle
        )
        user = convert_results['user']
        cls.create_and_save_business_entities(
            convert_results,
            convert_results_benefit,
            payroll.id,
            user
        )

    @classmethod
    def create_and_save_business_entities(
            cls, convert_results, convert_results_benefit, payroll_id, user, bill_status=None
    ):
        if bill_status is not None:
            convert_results['bill_data']['status'] = bill_status
        result_bill_creation = BillService.bill_create(convert_results=convert_results)
        if result_bill_creation["success"]:
            bill_id = result_bill_creation['data']['id']
            benefit_service = BenefitConsumptionService(user)
            benefit_result = benefit_service.create(convert_results_benefit['benefit_data'])
            if benefit_result["success"]:
                bill_queryset = Bill.objects.filter(id__in=[bill_id])
                benefit_id = benefit_result['data']['id']
                benefit_service.create_or_update_benefit_attachment(bill_queryset, benefit_id)
                if payroll_id:
                    payroll_service = PayrollService(user=user)
                    payroll_service.attach_benefit_to_payroll(payroll_id, benefit_id)
        return result_bill_creation

    @classmethod
    def _convert_entity_to_bill(
        cls, converter, converter_item, payment_plan, entity, amount, end_date, payment_cycle
    ):
        bill = converter.to_bill_obj(
            payment_plan, entity, amount, end_date, payment_cycle
        )
        bill_line_items = [
            converter_item.to_bill_item_obj(payment_plan, entity, amount)
        ]
        return {
            'bill_data': bill,
            'bill_data_line': bill_line_items,
            'type_conversion': 'beneficiary - bill'
        }

    @classmethod
    def _convert_entity_to_benefit(
            cls, converter_benefit, payment_plan, entity, amount, payment_cycle
    ):
        benefit = converter_benefit.to_benefit_obj(entity, amount, payment_plan, payment_cycle)
        return {
            'benefit_data': benefit,
            'type_conversion': 'beneficiary - benefit'
        }
