class TimesheetStrategyInterface:

    TYPE = None
    BENEFICIARY_OBJECT = None
    BENEFICIARY_TYPE = None

    @classmethod
    def check_calculation(cls, payment_plan, **kwargs):
        pass

    @classmethod
    def calculate(cls, payment_plan, **kwargs):
        pass

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        pass
