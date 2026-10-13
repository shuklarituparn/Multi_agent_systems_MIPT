"""Executable tools. Their contracts are visible to the model."""

DOCUMENTS = [
    {'id': 'D1', 'topic': 'Agent loop', 'minutes': 20,
     'text': 'An LLM chooses a tool or final answer; application code executes tools and returns results.'},
    {'id': 'D2', 'topic': 'Tool calling', 'minutes': 20,
     'text': 'A tool has a name, description and input schema. Validate arguments and restrict permissions.'},
    {'id': 'D3', 'topic': 'Specialist roles', 'minutes': 20,
     'text': 'Separate research, planning and review with distinct instructions and scoped tool access.'},
    {'id': 'D4', 'topic': 'Evaluation', 'minutes': 15,
     'text': 'Check groundedness, coverage, budget and stop limits; compare against a simpler baseline.'},
]


def search_documents(query: str) -> list[dict]:
    """Keyword search over four local fixtures; 'all' returns the full syllabus."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError('query must be a non-empty string')
    words = query.lower().split()
    return [dict(d) for d in DOCUMENTS if 'all' in words or any(
        word in (d['topic'] + ' ' + d['text']).lower() for word in words)]


def get_budget(days: int, daily_minutes: int) -> dict:
    if type(days) is not int or type(daily_minutes) is not int or days < 1 or daily_minutes < 1:
        raise ValueError('days and daily_minutes must be positive integers')
    return {'days': days, 'daily_minutes': daily_minutes, 'total_minutes': days * daily_minutes}


def validate_plan(plan: dict, documents: list[dict], days: int, daily_minutes: int) -> dict:
    """Deterministic acceptance gate; no LLM judge can waive these checks."""
    get_budget(days, daily_minutes)
    issues = []
    sessions = plan.get('sessions') if isinstance(plan, dict) else None
    if not isinstance(sessions, list) or not sessions:
        return {'passed': False, 'issues': ['sessions must be a non-empty list']}
    sources = {d['id']: d for d in documents}
    coverage = {d['id']: 0 for d in documents}
    totals = {day: 0 for day in range(1, days + 1)}
    for index, session in enumerate(sessions):
        prefix = f'Session {index + 1}'
        if not isinstance(session, dict):
            issues.append(f'{prefix}: expected an object')
            continue
        day, minutes, source = session.get('day'), session.get('minutes'), session.get('source_id')
        valid_day = type(day) is int and 1 <= day <= days
        valid_minutes = type(minutes) is int and minutes > 0
        if not valid_day:
            issues.append(f'{prefix}: day must be an integer between 1 and {days}')
        if not valid_minutes:
            issues.append(f'{prefix}: minutes must be a positive integer')
        if not isinstance(source, str) or source not in sources:
            issues.append(f'{prefix}: unknown source ID')
        elif session.get('topic') != sources[source]['topic']:
            issues.append(f'{prefix}: topic does not match source {source}')
        elif valid_minutes:
            coverage[source] += minutes
        if valid_day and valid_minutes:
            totals[day] += minutes
    for day, total in totals.items():
        if total > daily_minutes:
            issues.append(f'Day {day}: {total} minutes exceeds limit {daily_minutes}')
    for source, total in coverage.items():
        expected = sources[source]['minutes']
        if total != expected:
            issues.append(f'{source}: allocated {total} minutes, requires exactly {expected}')
    return {'passed': not issues, 'issues': issues, 'daily_totals': totals}


def schema(name: str, description: str, properties: dict) -> dict:
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties,
                       'required': list(properties), 'additionalProperties': False}}}


SEARCH_SCHEMA = schema('search_documents', 'Search local lesson facts; use all for the full syllabus.',
                       {'query': {'type': 'string'}})
BUDGET_SCHEMA = schema('get_budget', 'Calculate study-time capacity.',
                       {'days': {'type': 'integer'}, 'daily_minutes': {'type': 'integer'}})
# The reviewer tool binds task and evidence in code. The model supplies only a plan.
REVIEW_SCHEMA = schema('validate_plan', 'Check grounded coverage, integer minutes and daily limits.',
                       {'plan': {'type': 'object'}})
