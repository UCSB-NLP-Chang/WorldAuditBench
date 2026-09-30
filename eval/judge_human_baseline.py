"""Human-baseline scoring prompt with the original judge CLI and transport.

Run: python -m eval.judge_human_baseline [the same arguments as eval.judge].
The original module and its default prompt are never modified. An isolated module
instance permits simultaneous/default judge use without global prompt mutation.
"""
import importlib.util
from pathlib import Path

PROMPT_PATH = Path(__file__).with_name('judge_human_baseline_prompt.md')

def load_runtime():
    spec = importlib.util.spec_from_file_location(
        'eval._human_baseline_judge_runtime', Path(__file__).with_name('judge.py'))
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    runtime.PROMPT_PATH = PROMPT_PATH
    return runtime

def main(argv=None):
    return load_runtime().main(argv)

if __name__ == '__main__':
    raise SystemExit(main())
