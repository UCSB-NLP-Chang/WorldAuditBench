import io

import pytest
from PIL import Image

from agent.vlm.env.ue import UEEnv
from agent.vlm.tests.fake_ue_server import FakeUEServer
from agent.vlm.types import Action, ObsConfig


@pytest.fixture
def server():
    s = FakeUEServer()
    yield s
    s.close()


def test_reset_creates_env_and_returns_start_frame_in_metres(server):
    env = UEEnv(server.url)
    obs = env.reset("/Game/Maps/demo_1", 0, ObsConfig(mode="final", capture_w=512, capture_h=384))
    assert env.capabilities == frozenset({"move", "turn", "wait"})
    assert server.requests[0]["path"] == "/envs" and server.requests[0]["body"]["map_path"] == "/Game/Maps/demo_1"
    assert server.requests[1]["path"].endswith("/reset")
    assert [f.kind for f in obs.frames] == ["final"] and Image.open(io.BytesIO(obs.frames[0].jpeg)).size == (512, 384)
    assert obs.pose.z == pytest.approx(0.9) and obs.pose.raw["position"] == [0.0, 0.0, 90.0]
    env.close()
    assert server.deleted == ["env-1"]


def test_move_uses_tick_clock_and_converts_units(server):
    env = UEEnv(server.url, speed_cms=200.0)
    env.reset(None, 0, ObsConfig(mode="final"))
    obs = env.step(Action("move", {"distance_m": 2.0, "direction": "forward"}))
    req = server.requests[-1]["body"]
    assert req["clock"] == "tick" and "film" not in req
    assert req["action"] == {"choice": 1, "duration": 1.0, "direction": 0}
    assert obs.moved == pytest.approx(2.0) and obs.pose.x == pytest.approx(2.0) and obs.sim_elapsed == 1.0
    obs = env.step(Action("move", {"distance_m": 1.0, "direction": "back"}))
    assert server.requests[-1]["body"]["action"]["direction"] == 1 and obs.pose.x == pytest.approx(1.0)


def test_turn_maps_sign_to_clockwise_and_wait_to_do_nothing(server):
    env = UEEnv(server.url)
    env.reset(None, 0, ObsConfig(mode="final"))
    obs = env.step(Action("turn", {"degrees": -30}))
    a = server.requests[-1]["body"]["action"]
    assert a["choice"] == 2 and a["angle"] == 30 and a["clockwise"] is False and obs.pose.yaw == 330
    env.step(Action("wait", {"seconds": 2.0}))
    a = server.requests[-1]["body"]["action"]
    assert a["choice"] == 0 and a["duration"] == 2.0


def test_film_mode_requests_and_decodes_strip(server):
    env = UEEnv(server.url)
    env.reset(None, 0, ObsConfig(mode="film", film_dt=0.5, film_max=8))
    obs = env.step(Action("wait", {"seconds": 2.0}))
    assert server.requests[-1]["body"]["film"] == {"dt": 0.5, "max_frames": 8}
    film = [f for f in obs.frames if f.kind == "film"]
    assert [f.t_sim for f in film] == [0.0, 0.5, 1.0, 1.5, 2.0] and obs.frames[-1].kind == "final"


def test_existing_env_id_is_reused_and_not_deleted(server):
    env = UEEnv(server.url, env_id="env-9")
    env.reset(None, 0, ObsConfig(mode="final"))
    assert server.requests[0]["path"] == "/envs/env-9/reset"
    env.close()
    assert server.deleted == []


def test_max_sec_and_hold_sec_map_to_duration_and_hold(server):
    env = UEEnv(server.url, speed_cms=200.0)
    env.reset(None, 0, ObsConfig(mode="final"))
    env.step(Action("move", {"distance_m": 2.0, "direction": "forward", "max_sec": 0.5, "hold_sec": 0.5}))
    body = server.requests[-1]["body"]
    assert body["action"]["duration"] == 0.5 and body["hold"] == 0.5
    env.step(Action("turn", {"degrees": 30, "hold_sec": 0.5}))
    body = server.requests[-1]["body"]
    assert body["action"]["duration"] == 0.25 and body["hold"] == 0.5
    assert env.speed_mps == 2.0 and env.turn_dps == 120.0
