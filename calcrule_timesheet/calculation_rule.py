from calcrule_timesheet.strategies import (
    TimesheetStrategyStorage
)
from calcrule_timesheet.config import CLASS_RULE_PARAM_VALIDATION, DESCRIPTION_TIMESHEET_CALCULATION, FROM_TO
from core.abs_calculation_rule import AbsStrategy
from core.signals import *
from core import datetime
from contribution_plan.models import PaymentPlan
from django.contrib.contenttypes.models import ContentType


class TimesheetCalculationRule(AbsStrategy):
    version = 1
    uuid = "8a3c7d2e-4f1b-4c8a-9e5f-6d7b8c9a0b1c"
    calculation_rule_name = "Calculation rule: timesheet"
    description = DESCRIPTION_TIMESHEET_CALCULATION
    impacted_class_parameter = CLASS_RULE_PARAM_VALIDATION
    date_valid_from = datetime.datetime(2000, 1, 1)
    date_valid_to = None
    status = "active"
    from_to = FROM_TO
    type = "social_protection"
    sub_type = "benefit_plan"
    CLASS_NAME_CHECK = ['PaymentPlan']



    @classmethod
    def run_calculation_rules(cls, sender, instance, user, context, **kwargs):
        if isinstance(instance, PaymentPlan):
            return cls.calculate_if_active_for_object(instance, **kwargs)
        else:
            return False

    @classmethod
    def calculate_if_active_for_object(cls, payment_plan, **kwargs):
        if cls.active_for_object(payment_plan):
            return cls.calculate(payment_plan, **kwargs)

    @classmethod
    def active_for_object(cls, payment_plan, **kwargs):
        return cls.check_calculation(payment_plan)

    @classmethod
    def get_linked_class(cls, sender, class_name, **kwargs):
        list_class = super().get_linked_class(sender, class_name, **kwargs)
        if class_name == "PaymentPlan":
            list_class.append("Calculation")
        if class_name == "BenefitPlan":
            list_class.append("PaymentPlan")
        if class_name == "Beneficiary":
            list_class.append("BenefitPlan")
        return list_class

    @classmethod
    def get_parameters(cls, sender, class_name, instance, **kwargs):
        rule_details = cls.get_rule_details(sender=sender, class_name=class_name)
        if rule_details:
            if instance.__class__.__name__ in cls.CLASS_NAME_CHECK:
                if cls.check_calculation(payment_plan=instance):
                    return rule_details["parameters"] if "parameters" in rule_details else []
            elif instance.__class__.__name__ == 'ABCMeta' and cls.uuid == str(instance.uuid):
                return rule_details["parameters"] if "parameters" in rule_details else []

    @classmethod
    def run_convert(cls, payment_plan, **kwargs):
        return cls.convert(payment_plan=payment_plan, **kwargs)

    @classmethod
    def check_calculation(cls, payment_plan, **kwargs):
        return TimesheetStrategyStorage.choose_strategy(payment_plan).check_calculation(cls, payment_plan)

    @classmethod
    def calculate(cls, payment_plan, **kwargs):
        return TimesheetStrategyStorage.choose_strategy(payment_plan).calculate(cls, payment_plan, **kwargs)

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        TimesheetStrategyStorage.choose_strategy(payment_plan).convert(payment_plan, **kwargs)

    @classmethod
    def get_payment_cycle_parameters(cls, **kwargs):
        user_id = kwargs.get('user_id', None)
        start_date = kwargs.get('start_date', None)
        end_date = kwargs.get('end_date', None)
        payment_cycle = kwargs.get('payment_cycle', None)
        return user_id, start_date, end_date, payment_cycle
