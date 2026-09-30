import json
from pathlib import Path
import subprocess
from eval import judge, judge_human_baseline as human

def test_prompt_isolation():
    original = judge.PROMPT_PATH
    a,b=human.load_runtime(),human.load_runtime()
    assert a is not b
    assert a.PROMPT_PATH == human.PROMPT_PATH
    assert judge.PROMPT_PATH == original
    assert a.SCHEMA == judge.SCHEMA

def test_human_cli_reuses_binary_transport_with_custom_prompt(tmp_path,monkeypatch):
    rubric=tmp_path/'rubric.txt';report=tmp_path/'report.txt';output=tmp_path/'judge.json'
    rubric.write_text('目标异常');report.write_text('人类报告')
    monkeypatch.setattr(judge.shutil,'which',lambda _: '/fake/codex')
    def run(command,**kwargs):
        instructions=[x for x in command if x.startswith('developer_instructions=')]
        assert json.loads(instructions[0].split('=',1)[1]) == human.PROMPT_PATH.read_text()
        assert command[command.index('--model')+1]=='gpt-6-astra'
        assert 'model_reasoning_effort="medium"' in command
        Path(command[command.index('--output-last-message')+1]).write_text('{"reason":"命中核心异常","score":1}')
        return subprocess.CompletedProcess(command,0,stdout='',stderr='')
    monkeypatch.setattr(judge.subprocess,'run',run)
    assert human.main(['--rubrics',str(rubric),'--model-output',str(report),'--output',str(output)])==0
    assert json.loads(output.read_text())['score']==1
    assert judge.PROMPT_PATH.name=='judge_prompt.md'
