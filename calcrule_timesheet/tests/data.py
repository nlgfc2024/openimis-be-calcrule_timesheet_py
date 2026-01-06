from core.datetimes.ad_datetime import datetime

payment_plan_timesheet_individual = {
    "benefit_plan_id": None,
    "calculation": None,
    "json_ext": {
        "calculation_rule": {
            "base_day_rate": "50.00",
            "limit_per_single_transaction": ""
        }
    }
}

payment_plan_timesheet_individual_with_limit = {
    "benefit_plan_id": None,
    "calculation": None,
    "json_ext": {
        "calculation_rule": {
            "base_day_rate": "50.00",
            "limit_per_single_transaction": "1000.00"
        }
    }
}

payment_plan_timesheet_group = {
    "benefit_plan_id": None,
    "calculation": None,
    "json_ext": {
        "calculation_rule": {
            "base_day_rate": "100.00",
            "limit_per_single_transaction": ""
        }
    }
}

payment_plan_timesheet_group_with_limit = {
    "benefit_plan_id": None,
    "calculation": None,
    "json_ext": {
        "calculation_rule": {
            "base_day_rate": "100.00",
            "limit_per_single_transaction": "2000.00"
        }
    }
}
