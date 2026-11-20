# openIMIS Backend calcrule_timesheet reference module
# description
This calculation rule calculates payment amounts based on time worked/attendance tracking. It computes payments by multiplying a base day rate by the percentage of time worked/attended each day (from ProjectTimeEntry records) and summing across all working days for each project under a benefit plan.

Only COMPLETED projects of the payment plan's benefit plan are paid. Training sessions
(projects whose `project_type` is `TRAINING`) are always skipped: training attendance
never becomes a timesheet Bill or BenefitConsumption. It is paid by the attendance-grant
calculation rule instead. WORK projects are paid as described above.
