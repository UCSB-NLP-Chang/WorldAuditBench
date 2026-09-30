from agent.env.fake import FakeEnv
from agent.types import Action, ObsConfig


def test_reset_gives_one_final_frame_and_move_advances_pose():
    env = FakeEnv()
    obs0 = env.reset("fake", 0, ObsConfig(mode="final"))
    assert [f.kind for f in obs0.frames] == ["final"] and obs0.moved == 0.0
    obs = env.step(Action("move", {"distance_m": 2.0, "direction": "forward"}))
    assert abs(obs.moved - 2.0) < 1e-6
    assert abs(obs.pose.x - obs0.pose.x - 2.0) < 1e-6         # yaw 0 = +x
    assert [f.kind for f in obs.frames] == ["final"]


def test_film_mode_samples_frames_at_fixed_sim_dt():
    env = FakeEnv()
    env.reset("fake", 0, ObsConfig(mode="film", film_dt=0.5, film_max=8))
    obs = env.step(Action("wait", {"seconds": 3.0}))
    film = [f for f in obs.frames if f.kind == "film"]
    assert [f.t_sim for f in film] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert obs.frames[-1].kind == "final" and obs.sim_elapsed == 3.0
    obs = env.step(Action("wait", {"seconds": 5.0}))
    assert len([f for f in obs.frames if f.kind == "film"]) == 8   # capped


def test_blocked_wall_stops_the_move_short():
    env = FakeEnv(wall_x=1.0)
    env.reset("fake", 0, ObsConfig(mode="final"))
    obs = env.step(Action("move", {"distance_m": 3.0, "direction": "forward"}))
    assert abs(obs.moved - 1.0) < 1e-6


def test_turn_changes_yaw_and_frames_differ():
    env = FakeEnv()
    a = env.reset("fake", 0, ObsConfig(mode="final")).frames[-1].jpeg
    obs = env.step(Action("turn", {"degrees": 90}))
    assert obs.pose.yaw == 90 and obs.frames[-1].jpeg != a


def test_max_sec_caps_the_action_and_hold_sec_extends_the_tick():
    env = FakeEnv()
    env.reset("fake", 0, ObsConfig(mode="final"))
    obs = env.step(Action("move", {"distance_m": 4.0, "direction": "forward", "max_sec": 0.25}))
    assert obs.sim_elapsed == 0.25 and abs(obs.moved - 5.2 * 0.25) < 1e-6      # cut short by time
    obs = env.step(Action("turn", {"degrees": 30, "hold_sec": 0.5}))
    assert obs.pose.yaw == 30 and obs.sim_elapsed == 0.5                        # turn done, then held still
    obs = env.step(Action("wait", {"seconds": 5.0, "max_sec": 0.5}))
    assert obs.sim_elapsed == 0.5
    obs = env.step(Action("interact", {"max_sec": 0.5, "hold_sec": 0.5}))
    assert obs.sim_elapsed == 0.5
    assert env.speed_mps == 5.2 and env.turn_dps == 120.0
