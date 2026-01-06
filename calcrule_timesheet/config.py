CLASS_RULE_PARAM_VALIDATION = [
    {
        "class": "PaymentPlan",
        "parameters": [
            {
                "type": "number",
                "name": "base_day_rate",
                "label": {
                    "en": "Base Day Rate",
                    "fr": "Taux de base journalier"
                },
                "rights": {
                    "read": "157101",
                    "write": "157102",
                    "update": "157103",
                    "replace": "157206"
                },
                "relevance": "True",
                "condition": "INPUT>=0",
                "default": "0"
            },
            {
                "type": "number",
                "name": "limit_per_single_transaction",
                "label": {
                    "en": "Limit Per Single Transaction",
                    "fr": "Limite par transaction unique"
                },
                "rights": {
                    "read": "157101",
                    "write": "157102",
                    "update": "157103",
                    "replace": "157206"
                },
                "relevance": "True",
                "condition": "INPUT>=0",
                "default": ""
            }
        ]
    }
]

FROM_TO = None

DESCRIPTION_TIMESHEET_CALCULATION = (
    "Calculation rule for timesheet-based payments. "
    "Calculates payment based on base day rate multiplied by percentage of time worked/attended "
    "each day (from ProjectTimeEntry records), summed across all working days."
)
