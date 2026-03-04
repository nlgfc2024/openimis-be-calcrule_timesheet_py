import copy
from social_protection.models import (
    BeneficiaryProjectTimeEntry,
    GroupBeneficiaryProjectTimeEntry,
    BeneficiaryProjectEnrollment,
    GroupBeneficiaryProjectEnrollment,
)


def merge_dicts(original, override):
    updated = copy.deepcopy(original)
    for key, value in override.items():
        if isinstance(value, dict) and key in updated:
            updated[key] = merge_dicts(updated.get(key, {}), value)
        else:
            updated[key] = value
    return updated


def create_enrollment(beneficiary, project, user, is_group=False):
    """
    Create a project enrollment for a beneficiary (individual or group)

    Args:
        beneficiary: Beneficiary or GroupBeneficiary instance
        project: Project instance
        user: User instance for audit trail
        is_group: True if beneficiary is GroupBeneficiary, False for Beneficiary

    Returns:
        The created enrollment instance
    """
    if is_group:
        enrollment = GroupBeneficiaryProjectEnrollment(
            group_beneficiary=beneficiary,
            project=project
        )
    else:
        enrollment = BeneficiaryProjectEnrollment(
            beneficiary=beneficiary,
            project=project
        )

    enrollment.save(user=user)
    return enrollment


def create_time_entry(enrollment, day_number, percent_complete, username, is_group=False):
    """
    Create a ProjectTimeEntry for an enrollment (individual or group)

    Args:
        enrollment: BeneficiaryProjectEnrollment or GroupBeneficiaryProjectEnrollment instance
        day_number: Day number (1 to project.working_days)
        percent_complete: Percentage completed (0-100)
        username: Username for audit trail
        is_group: True if group enrollment, False for individual enrollment
    """
    if is_group:
        time_entry = GroupBeneficiaryProjectTimeEntry(
            enrollment=enrollment,
            day_number=day_number,
            percent_complete=percent_complete
        )
    else:
        time_entry = BeneficiaryProjectTimeEntry(
            enrollment=enrollment,
            day_number=day_number,
            percent_complete=percent_complete
        )

    time_entry.save(username=username)
    return time_entry


def create_multiple_time_entries(enrollment, entries_data, username, is_group=False):
    """
    Create multiple time entries for an enrollment

    Args:
        enrollment: BeneficiaryProjectEnrollment or GroupBeneficiaryProjectEnrollment instance
        entries_data: List of dicts with 'day_number' and 'percent_complete' keys
        username: Username for audit trail
        is_group: True if group enrollment, False for individual enrollment

    Returns:
        List of created time entries
    """
    time_entries = []
    for entry_data in entries_data:
        time_entry = create_time_entry(
            enrollment,
            entry_data['day_number'],
            entry_data['percent_complete'],
            username,
            is_group
        )
        time_entries.append(time_entry)
    return time_entries


def calculate_expected_payment(time_entries, base_day_rate):
    """
    Calculate expected payment based on time entries and base day rate

    Args:
        time_entries: List of time entry dicts or objects with day_number and percent_complete
        base_day_rate: Base rate per day

    Returns:
        Expected payment amount
    """
    total = 0
    for entry in time_entries:
        if isinstance(entry, dict):
            percent = entry['percent_complete']
        else:
            percent = entry.percent_complete
        total += (percent / 100.0) * base_day_rate
    return total
