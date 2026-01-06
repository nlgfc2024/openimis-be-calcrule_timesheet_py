from social_protection.models import GroupBeneficiary

from calcrule_timesheet.converters import (
    GroupToBillConverter,
    GroupToBillItemConverter,
    GroupToBenefitConverter
)
from calcrule_timesheet.strategies.timesheet_base_strategy import BaseTimesheetStrategy


class GroupTimesheetStrategy(BaseTimesheetStrategy):
    TYPE = "GROUP"
    BENEFICIARY_OBJECT = GroupBeneficiary
    BENEFICIARY_TYPE = "group"

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        group = kwargs.get('group', None)
        additional_parameters = {
            "entity": group,
            "converter": GroupToBillConverter,
            "converter_item": GroupToBillItemConverter,
            "converter_benefit": GroupToBenefitConverter,
            **kwargs
        }
        return super().convert(payment_plan, **additional_parameters)
