"""Integration: the three.js adapter against env0-corridor in headless Chromium.
Needs assets/vendor (scripts/fetch_assets.sh) and `playwright install chromium`."""
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from agent.env.base import is_blocked
from agent.types import Action, ObsConfig

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.chromium
GPU = os.environ.get("AGENT_TEST_GPU", "swiftshader")

if not (REPO / "assets" / "vendor" / "three" / "three.module.js").exists():
    pytest.skip("three.js vendor assets missing", allow_module_level=True)


@pytest.fixture(scope="module")
def env():
    from agent.env.threejs import ThreeJSEnv
    e = ThreeJSEnv(gpu=GPU)
    yield e
    e.close()


def _size(frame):
    return Image.open(io.BytesIO(frame.jpeg)).size


def test_reset_final_mode_gives_one_full_res_start_frame(env):
    obs = env.reset("env0-corridor", 1, ObsConfig(mode="final"))
    assert obs.action_index == 0 and [f.kind for f in obs.frames] == ["final"]
    assert _size(obs.frames[0]) == (960, 600) and obs.frames[0].w == 960
    assert obs.pose.raw["pos"] and "renderer" in env.meta()


def test_move_forward_reports_displacement_and_one_frame(env):
    env.reset("env0-corridor", 1, ObsConfig(mode="final"))
    obs = env.step(Action("move", {"distance_m": 1.5, "direction": "forward"}))
    assert abs(obs.moved - 1.5) < 0.1
    assert [f.kind for f in obs.frames] == ["final"] and obs.sim_elapsed > 0
    assert not is_blocked(Action("move", {"distance_m": 1.5}), obs)


def test_film_mode_returns_sim_time_spaced_full_res_frames(env):
    env.reset("env0-corridor", 1, ObsConfig(mode="film", film_dt=0.5, film_max=8))
    obs = env.step(Action("wait", {"seconds": 2.0}))
    film = [f for f in obs.frames if f.kind == "film"]
    assert 4 <= len(film) <= 5
    for a, b in zip(film, film[1:]):
        assert abs((b.t_sim - a.t_sim) - 0.5) < 0.15
    assert all(_size(f) == (960, 600) for f in film)
    assert obs.frames[-1].kind == "final" and abs(obs.sim_elapsed - 2.0) < 0.2


def test_walking_into_the_corridor_wall_is_blocked(env):
    env.reset("env0-corridor", 1, ObsConfig(mode="final"))
    env.step(Action("turn", {"degrees": 90}))
    obs = env.step(Action("move", {"distance_m": 4.0, "direction": "forward"}))
    assert obs.moved < 2.5                                     # corridor is 4 m wide, spawn at centre
    assert is_blocked(Action("move", {"distance_m": 4.0}), obs)


def test_turn_and_look_change_the_pose(env):
    obs0 = env.reset("env0-corridor", 1, ObsConfig(mode="final"))
    obs = env.step(Action("turn", {"degrees": 45}))
    assert abs(((obs.pose.yaw - obs0.pose.yaw) + 180) % 360 - 180) == pytest.approx(45, abs=1.5)
    obs = env.step(Action("look", {"degrees": 20}))
    assert abs(obs.pose.pitch - obs0.pose.pitch) == pytest.approx(20, abs=1.5)


def test_max_sec_cuts_actions_and_hold_sec_pads_the_tick(env):
    env.reset("env0-corridor", 1, ObsConfig(mode="final"))
    obs = env.step(Action("wait", {"seconds": 5.0, "max_sec": 0.5}))
    assert abs(obs.sim_elapsed - 0.5) < 0.1
    obs = env.step(Action("move", {"distance_m": 4.0, "direction": "forward", "max_sec": 0.3}))
    assert 1.0 < obs.moved < 2.0 and abs(obs.sim_elapsed - 0.3) < 0.1
    y0 = env.step(Action("wait", {"seconds": 0.5})).pose.yaw
    obs = env.step(Action("turn", {"degrees": 30, "hold_sec": 0.5}))
    assert abs(((obs.pose.yaw - y0) + 180) % 360 - 180) == pytest.approx(30, abs=1.5)
    assert abs(obs.sim_elapsed - 0.5) < 0.1
    obs = env.step(Action("interact", {"max_sec": 0.5, "hold_sec": 0.5}))
    assert abs(obs.sim_elapsed - 0.5) < 0.1
    assert env.speed_mps == 5.2
