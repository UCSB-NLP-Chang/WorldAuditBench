import json

from agent.env.fake import FakeEnv
from agent.runner import EpisodeSpec, build_parser, run_one, specs_from_args
from agent.tests.fake_llm import FakeLLM

SCRIPT = [
    {"content": "expect a hall", "tools": [("move", {"distance_m": 2.0, "direction": "forward"})]},
    {"content": "", "tools": [("flag_bug", {"description": "floating pot", "category": "geometry", "status": "confirmed"})]},
    {"content": "", "tools": [("done", {"summary": "found one"})]},
]


def _spec(tmp_path, **kw):
    base = dict(task="audit_sp05_bug", seed=2, run_dir=tmp_path / "audit_sp05_bug-p1-s2", obs="final",
                film_dt=0.5, film_max=8, ctx_final=(960, 576), ctx_film=(480, 288), context_limit=64000,
                keep_recent=3, tools=("memory", "bugs", "notes"), expect=True, proprio=True, blocked_hint=False,
                max_actions=None, max_calls=300, temperature=1.0, max_tokens=4096, video=False, env="fake",
                gpu="swiftshader", model="fake", base_url=None, ue_url=None)
    base.update(kw)
    return EpisodeSpec(**base)


def test_run_one_writes_scoring_compatible_meta(tmp_path):
    spec = _spec(tmp_path)
    meta = run_one(spec, env_factory=lambda s: FakeEnv(), llm_factory=lambda s: FakeLLM(list(SCRIPT)))
    m = json.loads((spec.run_dir / "meta.json").read_text())
    assert m == meta
    # fields eval/judge_sem.py and the report scripts read
    assert m["kind"] == "audit" and m["task"] == "audit_sp05_bug" and m["config"] == "sp05-airwall"
    assert m["model"] == "fake-vlm" and m["seed"] == 2 and m["proprio"] == 1
    assert m["flags"] == [dict(pos=m["flags"][0]["pos"], note="floating pot", simT=m["flags"][0]["simT"], id="b1",
                               status="confirmed", category="geometry", evidence=[], action=1)]
    assert m["steps_budget"] == 25 and m["steps_used"] == 1           # max_actions=None in _spec -> the task's own steps (SP: 25)
    assert m["success"] is None and m["done_by_model"] is True and m["outcome"] == "done"
    assert "started" in m and "ended" in m and m["renderer"] == "fake"
    assert m["vlm_usage"]["calls"] == 3 and m["harness"] == "agent" and m["obs"] == "final"
    assert m["compactions"] == 0 and m["tool_counts"] == {"move": 1, "flag_bug": 1, "done": 1}


def test_run_one_output_feeds_old_metrics_and_video(tmp_path):
    from eval.metrics import episode_metrics, load_episode
    from eval.video import make_video
    spec = _spec(tmp_path, video=True)
    run_one(spec, env_factory=lambda s: FakeEnv(), llm_factory=lambda s: FakeLLM(list(SCRIPT)))
    steps, meta = load_episode(spec.run_dir)
    m = episode_metrics(steps, meta)
    assert m["steps"] == 1 and m["path_len"] == 2.0 and m["blocked"] == 0
    assert (spec.run_dir / "video.mp4").exists()                    # made by run_one via eval.video
    assert make_video(spec.run_dir, out_name="again.mp4") is not None


def test_max_actions_override_and_grid_specs(tmp_path):
    args = build_parser().parse_args(["--grid", "audit_sp05_bug,audit_sp00_clean", "--episodes", "2",
                                      "--tag", "t1", "--max-actions", "7", "--obs", "film",
                                      "--tools", "bugs", "--proprio", "0"])
    specs = specs_from_args(args, tmp_path)
    assert len(specs) == 4
    assert {s.task for s in specs} == {"audit_sp05_bug", "audit_sp00_clean"}
    assert [s.seed for s in specs if s.task == "audit_sp05_bug"] == [0, 1]
    assert specs[0].run_dir == tmp_path / "t1" / "audit_sp05_bug-p0-s0"
    assert specs[0].max_actions == 7 and specs[0].obs == "film" and specs[0].tools == ("bugs",)
    assert specs[0].proprio is False


def test_resume_skips_finished_episodes(tmp_path):
    args = build_parser().parse_args(["--grid", "audit_sp05_bug", "--episodes", "2", "--tag", "t2", "--resume"])
    specs = specs_from_args(args, tmp_path)
    done_dir = specs[0].run_dir
    done_dir.mkdir(parents=True)
    (done_dir / "meta.json").write_text(json.dumps({"ended": "2026-09-08 00:00:00"}))
    from agent.runner import filter_resume
    assert [s.seed for s in filter_resume(specs)] == [1]


def test_unknown_task_is_rejected():
    import pytest
    args = build_parser().parse_args(["--task", "no_such_task"])
    with pytest.raises(SystemExit):
        specs_from_args(args, __import__("pathlib").Path("/tmp"))


def test_cli_defaults_follow_the_recommended_sampling_and_reasoning_settings(tmp_path):
    args = build_parser().parse_args(["--task", "audit_sp05_bug"])
    spec = specs_from_args(args, tmp_path)[0]
    assert spec.max_tokens == 4096 and spec.temperature == 1.0
    assert spec.sampling == {"top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0,
                             "repetition_penalty": 1.0}
    assert spec.reasoning_effort == "low"
    args = build_parser().parse_args(["--task", "audit_sp05_bug", "--reasoning-effort", "none", "--top-k", "0"])
    spec = specs_from_args(args, tmp_path)[0]
    assert spec.reasoning_effort is None and spec.sampling["top_k"] == 0


def test_run_one_records_sampling_in_meta(tmp_path):
    spec = _spec(tmp_path)
    meta = run_one(spec, env_factory=lambda s: FakeEnv(), llm_factory=lambda s: FakeLLM(list(SCRIPT)))
    assert meta["max_tokens"] == 4096 and meta["temperature"] == 1.0
    assert meta["sampling"]["top_p"] == 0.95 and meta["reasoning_effort"] == "low"


def test_decision_flags_and_tick_film_rejection(tmp_path):
    args = build_parser().parse_args(["--task", "audit_sp05_bug", "--decision", "tick", "--tick", "0.25",
                                      "--obs", "final", "--max-sim-seconds", "60"])
    spec = specs_from_args(args, tmp_path)[0]
    assert spec.decision == "tick" and spec.tick == 0.25 and spec.max_sim_seconds == 60.0
    import pytest
    with pytest.raises(SystemExit):
        specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug", "--decision", "tick", "--obs", "film"]), tmp_path)
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug"]), tmp_path)[0]
    assert spec.decision == "macro" and spec.max_sim_seconds is None


def test_run_one_records_decision_settings(tmp_path):
    spec = _spec(tmp_path, decision="tick", tick=0.5, max_sim_seconds=3.0)
    meta = run_one(spec, env_factory=lambda s: FakeEnv(), llm_factory=lambda s: FakeLLM(list(SCRIPT)))
    assert meta["decision"] == "tick" and meta["tick"] == 0.5 and meta["max_sim_seconds"] == 3.0
    assert meta["sim_t"] == 0.5                                   # the one move filled a whole tick


def test_provider_sort_and_extra_body_flags(tmp_path):
    args = build_parser().parse_args(["--task", "audit_sp05_bug", "--provider-sort", "latency",
                                      "--extra-body", '{"seed": 3}'])
    spec = specs_from_args(args, tmp_path)[0]
    assert spec.extra_body == {"provider": {"sort": "latency"}, "seed": 3}
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug"]), tmp_path)[0]
    assert spec.extra_body == {}


def test_run_one_records_extra_body(tmp_path):
    spec = _spec(tmp_path, extra_body={"provider": {"sort": "latency"}})
    meta = run_one(spec, env_factory=lambda s: FakeEnv(), llm_factory=lambda s: FakeLLM(list(SCRIPT)))
    assert meta["extra_body"] == {"provider": {"sort": "latency"}}


def test_suite_and_variant_compose_the_grid(tmp_path):
    specs = specs_from_args(build_parser().parse_args(["--suite", "sp", "--variant", "l1", "--episodes", "2"]), tmp_path)
    assert len(specs) == 28 and {s.task for s in specs} == {f"audit_sp{i:02d}_l1" for i in range(1, 16) if i != 3}
    specs = specs_from_args(build_parser().parse_args(["--suite", "sp", "--variant", "all", "--episodes", "1"]), tmp_path)
    assert len(specs) == 15 and "audit_sp00_clean" in {s.task for s in specs}
    specs = specs_from_args(build_parser().parse_args(["--suite", "hs", "--variant", "bug", "--cases", "01,05", "--episodes", "1"]), tmp_path)
    assert [s.task for s in specs] == ["audit_hs01_bug", "audit_hs05_bug"]
    specs = specs_from_args(build_parser().parse_args(["--suite", "tc", "--variant", "clean", "--episodes", "1"]), tmp_path)
    assert len(specs) == 10 and all(t.task.endswith("_clean") for t in specs)
    specs = specs_from_args(build_parser().parse_args(["--suite", "ct", "--variant", "bug", "--episodes", "1"]), tmp_path)
    assert len(specs) == 16


def test_suite_conflicts_and_unknown_variants_are_rejected(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        specs_from_args(build_parser().parse_args(["--suite", "sp", "--variant", "l1", "--grid", "audit_sp01_l1"]), tmp_path)
    with pytest.raises(SystemExit):
        specs_from_args(build_parser().parse_args(["--suite", "wt", "--variant", "l3", "--episodes", "1"]), tmp_path)   # no ladder for WT


def test_gpu_native_is_accepted_by_the_cli(tmp_path):
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug", "--gpu", "native"]), tmp_path)[0]
    assert spec.gpu == "native"


def test_max_actions_default_and_task_keyword(tmp_path):
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug"]), tmp_path)[0]
    assert spec.max_actions == 100
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug", "--max-actions", "task"]), tmp_path)[0]
    assert spec.max_actions is None                                    # None = the task's own steps (25 for SP)
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug", "--rate-limit-wait", "120"]), tmp_path)[0]
    assert spec.rate_limit_wait == 120.0


def test_thinking_budget_flag_sets_dashscope_fields_and_drops_effort(tmp_path):
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug", "--thinking-budget", "1024"]), tmp_path)[0]
    assert spec.extra_body == {"enable_thinking": True, "thinking_budget": 1024}
    assert spec.reasoning_effort is None                    # effort levels do not bound reasoning; the budget does
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug", "--thinking-budget", "0"]), tmp_path)[0]
    assert spec.extra_body == {"enable_thinking": False} and spec.reasoning_effort is None


def test_preserve_thinking_flag(tmp_path):
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug"]), tmp_path)[0]
    assert spec.preserve_thinking is True
    spec = specs_from_args(build_parser().parse_args(["--task", "audit_sp05_bug", "--preserve-thinking", "off"]), tmp_path)[0]
    assert spec.preserve_thinking is False
    meta = run_one(_spec(tmp_path, preserve_thinking=False), env_factory=lambda s: FakeEnv(), llm_factory=lambda s: FakeLLM(list(SCRIPT)))
    assert meta["preserve_thinking"] is False
