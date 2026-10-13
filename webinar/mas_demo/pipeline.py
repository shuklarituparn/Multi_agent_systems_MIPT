"""Code-controlled orchestration, with an evaluator/revision branch."""
import copy
from dataclasses import dataclass

from . import prompts
from .runner import Agent, AgentError, emit, run_agent
from .tools import DOCUMENTS, SEARCH_SCHEMA, BUDGET_SCHEMA, REVIEW_SCHEMA
from .tools import search_documents, get_budget, validate_plan


@dataclass(frozen=True)
class Task:
    days: int = 3
    daily_minutes: int = 45
    question: str = 'Make a study schedule for all four lessons about LLM agents.'

    def __post_init__(self):
        get_budget(self.days, self.daily_minutes)
        if not isinstance(self.question, str) or not self.question.strip():
            raise ValueError('question must be non-empty')


def run_demo(task: Task, backend, inject_bad_draft: bool = False,
             max_revisions: int = 1, observer=None) -> dict:
    if type(max_revisions) is not int or not 0 <= max_revisions <= 3:
        raise ValueError('max_revisions must be an integer between 0 and 3')
    trace = []
    retrieved = {}

    def retrieve(query):
        docs = search_documents(query)
        retrieved.update({d['id']: d for d in docs})
        return docs

    researcher = Agent('Researcher', prompts.RESEARCHER,
                       {'search_documents': (retrieve, SEARCH_SCHEMA)})
    evidence = run_agent(researcher, {'question': task.question}, backend, trace, observer,
                         required_tools={'search_documents'})
    ids = evidence.get('source_ids')
    required = {d['id'] for d in DOCUMENTS}
    # An LLM may claim to know D1-D4 even when its searches returned only D1.
    # Give it one grounded recovery pass, showing the failure in the trace.
    valid_ids = isinstance(ids, list) and all(isinstance(x, str) for x in ids)
    if not (valid_ids and set(ids) == required and required.issubset(retrieved)):
        emit(trace, 'Coordinator', 'research_retry', {
            'claimed_ids': ids,
            'retrieved_ids': sorted(retrieved),
            'missing_ids': sorted(required - set(retrieved)),
            'reason': 'The Researcher cited documents that its tools did not retrieve.'
        }, observer)
        evidence = run_agent(researcher, {
            'question': task.question,
            'retrieved_ids': sorted(retrieved),
            'missing_ids': sorted(required - set(retrieved)),
            'correction': ('Previous retrieval was incomplete. Call search_documents '
                           'with query exactly "all". Then cite ONLY documents '
                           'actually returned by the tool.')
        }, backend, trace, observer)
        ids = evidence.get('source_ids')
        valid_ids = isinstance(ids, list) and all(isinstance(x, str) for x in ids)
    if not valid_ids or set(ids) != required or not required.issubset(retrieved):
        raise AgentError('Researcher: incomplete evidence after retry; use query "all" to retrieve D1-D4')
    documents = [retrieved[d['id']] for d in DOCUMENTS]
    capacity = get_budget(task.days, task.daily_minutes)['total_minutes']
    needed = sum(d['minutes'] for d in documents)
    base = {'mode': backend.mode, 'task': vars(task), 'documents': documents,
            'plan': None, 'review': None, 'revisions': 0, 'trace': trace}
    if needed > capacity:
        emit(trace, 'Coordinator', 'insufficient_budget',
             {'required_minutes': needed, 'available_minutes': capacity}, observer)
        return {**base, 'status': 'insufficient_budget',
                'message': f'Need {needed} minutes; only {capacity} available. Increase the budget or reduce scope.'}

    planner = Agent('Planner', prompts.PLANNER, {'get_budget': (get_budget, BUDGET_SCHEMA)})
    reviewer = Agent('Reviewer', prompts.REVIEWER, {'validate_plan': (
        lambda plan: validate_plan(plan, documents, task.days, task.daily_minutes), REVIEW_SCHEMA)})
    payload = {'question': task.question, 'days': task.days,
               'daily_minutes': task.daily_minutes, 'documents': documents, 'feedback': []}
    for revision in range(max_revisions + 1):
        plan = run_agent(planner, payload, backend, trace, observer,
                         required_tools={'get_budget'})
        if inject_bad_draft and revision == 0:
            plan = copy.deepcopy(plan)
            sessions = plan.get('sessions')
            if isinstance(sessions, list) and sessions and isinstance(sessions[0], dict):
                sessions[0]['minutes'] = task.daily_minutes + 1
            else:
                plan = {'sessions': []}
            emit(trace, 'Coordinator', 'injected_fault',
                 {'explanation': 'Presenter deliberately corrupts the first draft; this is not a model mistake.'}, observer)
        review_payload = {'plan': plan, 'days': task.days,
                          'daily_minutes': task.daily_minutes, 'documents': documents}
        model_review = run_agent(reviewer, review_payload, backend, trace, observer,
                                 required_tools={'validate_plan'})
        review = validate_plan(plan, documents, task.days, task.daily_minutes)
        if model_review.get('passed') != review['passed']:
            emit(trace, 'Coordinator', 'review_disagreement',
                 {'explanation': 'Executable validation overrides the model verdict.'}, observer)
        emit(trace, 'Coordinator', 'review', review, observer)
        base.update(plan=plan, review=review, revisions=revision)
        if review['passed']:
            return {**base, 'status': 'accepted'}
        payload.update(feedback=review['issues'], previous_plan=plan)
        if revision < max_revisions:
            emit(trace, 'Coordinator', 'revision_requested', {'issues': review['issues']}, observer)
    return {**base, 'status': 'needs_revision'}
