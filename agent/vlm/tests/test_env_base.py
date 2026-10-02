from agent.vlm.env.base import is_blocked
from agent.vlm.tests.helpers import observation
from agent.vlm.types import Action


def test_move_that_falls_short_is_blocked():
    assert is_blocked(Action("move", {"distance_m": 2.0, "direction": "forward"}), observation(1, moved=0.0))
    assert is_blocked(Action("move", {"distance_m": 2.0, "direction": "forward"}), observation(1, moved=1.5))


def test_move_within_tolerance_is_not_blocked():
    assert not is_blocked(Action("move", {"distance_m": 2.0, "direction": "forward"}), observation(1, moved=1.85))
    assert not is_blocked(Action("move", {"distance_m": 0.5, "direction": "back"}), observation(1, moved=0.3))


def test_teleport_and_non_move_actions_are_never_blocked():
    assert not is_blocked(Action("move", {"distance_m": 2.0}), observation(1, moved=0.0, teleported=True))
    assert not is_blocked(Action("turn", {"degrees": 45}), observation(1, moved=0.0))
    assert not is_blocked(Action("wait", {"seconds": 1}), observation(1, moved=0.0))


def test_bridge_static_server_has_a_deep_listen_backlog():
    from agent.vla.bridge import _StaticServer
    assert _StaticServer.request_queue_size >= 64      # simultaneous Chromium launches reset connections otherwise


def test_native_gpu_mode_uses_full_chromium_in_new_headless_mode():
    from agent.vla.bridge import GPU_FLAGSETS, Bridge
    assert "--headless=new" in GPU_FLAGSETS["native"]
    assert Bridge(gpu="native").launch_headless is False          # full Chromium binary (GPU-capable), windowless via the flag
    assert Bridge(gpu="swiftshader").launch_headless is True
