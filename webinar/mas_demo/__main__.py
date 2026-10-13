import argparse
import json
import sys
from pathlib import Path

from .backends import ScriptedBackend, CompatibleBackend
from .pipeline import Task, run_demo
from .report import save_report
from .runner import AgentError


def main():
    parser = argparse.ArgumentParser(description='Observable three-role LLM workflow; offline mode is simulated.')
    parser.add_argument('--backend', choices=['scripted', 'live'], default='scripted')
    parser.add_argument('--days', type=int, default=3)
    parser.add_argument('--daily-minutes', type=int, default=45)
    parser.add_argument('--inject-bad-draft', action='store_true')
    parser.add_argument('--max-revisions', type=int, default=1)
    parser.add_argument('--show-prompts', action='store_true')
    parser.add_argument('--out', type=Path, default=Path('runs/latest'))
    args = parser.parse_args()

    def observer(event):
        if event['kind'] == 'start' and not args.show_prompts:
            data = {'allowed_tools': event['data']['allowed_tools']}
        else:
            data = event['data']
        print(f"[{event['seq']:02d}] {event['agent']} / {event['kind']}: " +
              json.dumps(data, ensure_ascii=False))

    try:
        backend = ScriptedBackend() if args.backend == 'scripted' else CompatibleBackend.from_env()
        print('MODE: ' + backend.mode, flush=True)
        result = run_demo(Task(args.days, args.daily_minutes), backend,
                          args.inject_bad_draft, args.max_revisions, observer)
        if isinstance(backend, CompatibleBackend):
            result['usage'] = {'requests': backend.requests, **backend.usage}
        save_report(result, args.out)
        print('\nSTATUS: ' + result['status'])
        if result['status'] == 'accepted':
            for session in result['plan'].get('sessions', []):
                print(f"Day {session['day']}: {session['topic']} · {session['minutes']} min [{session['source_id']}]")
        elif result['review']:
            print('Review issues: ' + json.dumps(result['review']['issues']))
        print('Report: ' + str((args.out / 'report.html').resolve()))
        return 0 if result['status'] == 'accepted' else 2
    except (AgentError, ValueError, OSError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
