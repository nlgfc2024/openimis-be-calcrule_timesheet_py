from social_protection.models import Beneficiary
from project_social_protection.models import BeneficiaryProjectEnrollment
from calcrule_timesheet.converters import (
    BeneficiaryToBillConverter,
    BeneficiaryToBillItemConverter,
    BeneficiaryToBenefitConverter
)
from calcrule_timesheet.strategies.timesheet_base_strategy import BaseTimesheetStrategy


class IndividualTimesheetStrategy(BaseTimesheetStrategy):
    TYPE = "INDIVIDUAL"
    BENEFICIARY_OBJECT = Beneficiary
    ENROLLMENT_OBJECT = BeneficiaryProjectEnrollment
    BENEFICIARY_TYPE = "beneficiary"
    BENEFICIARY_FIELD = "beneficiary"

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        beneficiary = kwargs.get('beneficiary', None)
        additional_parameters = {
            "entity": beneficiary,
            "converter": BeneficiaryToBillConverter,
            "converter_item": BeneficiaryToBillItemConverter,
            "converter_benefit": BeneficiaryToBenefitConverter,
            **kwargs
        }
        return super().convert(payment_plan, **additional_parameters)
