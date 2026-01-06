import importlib
import inspect

from calcrule_timesheet.strategies.timesheet_base_strategy import BaseTimesheetStrategy


class TimesheetStrategyStorage:

    BASE_CLASS = BaseTimesheetStrategy
    MODULE_NAME = "calcrule_timesheet.strategies"

    @classmethod
    def choose_strategy(cls, payment_plan):
        module = importlib.import_module(cls.MODULE_NAME)
        for name, class_object in inspect.getmembers(module, inspect.isclass):
            if issubclass(class_object, cls.BASE_CLASS) and class_object != cls.BASE_CLASS:
                if payment_plan.benefit_plan.type == class_object.TYPE:
                    return class_object
