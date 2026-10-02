import io
import json

from PIL import Image

from agent.vlm.archive import FrameArchive
from agent.vlm.tests.helpers import observation


def test_put_assigns_refs_and_writes_files(tmp_path):
    ar = FrameArchive(tmp_path)
    obs = observation(12, n_film=3)
    ar.put(obs)
    assert [f.ref for f in obs.frames] == ["a12.f0", "a12.f1", "a12.f2", "a12"]
    assert (tmp_path / "frames" / "a012_f00.jpg").exists()
    assert (tmp_path / "frames" / "a012.jpg").exists()
    rows = [json.loads(l) for l in (tmp_path / "frames" / "index.jsonl").read_text().splitlines()]
    assert [r["ref"] for r in rows] == ["a12.f0", "a12.f1", "a12.f2", "a12"]
    assert rows[-1]["kind"] == "final" and rows[-1]["action"] == 12
    assert rows[0]["t_sim"] == 0.0 and rows[0]["pose"]["x"] == 12.0


def test_get_returns_original_bytes_without_region(tmp_path):
    ar = FrameArchive(tmp_path)
    obs = observation(5)
    ar.put(obs)
    assert ar.get("a5") == obs.frames[-1].jpeg
    assert ar.get("a5") == (tmp_path / "frames" / "a005.jpg").read_bytes()


def test_get_with_region_crops_to_multiples_of_32(tmp_path):
    ar = FrameArchive(tmp_path)
    ar.put(observation(1))
    data = ar.get("a1", region=[0.25, 0.25, 0.75, 0.75])
    img = Image.open(io.BytesIO(data))
    assert img.width % 32 == 0 and img.height % 32 == 0
    assert img.width <= 960 and img.width > 320          # crop is upscaled toward max_side, not left tiny


def test_unknown_ref_raises_keyerror(tmp_path):
    ar = FrameArchive(tmp_path)
    ar.put(observation(1))
    try:
        ar.get("a7")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_ctx_image_is_data_url_at_requested_size_and_cached(tmp_path):
    ar = FrameArchive(tmp_path)
    ar.put(observation(3, n_film=1))
    url1 = ar.ctx_image("a3", (480, 288))
    url2 = ar.ctx_image("a3", (480, 288))
    assert url1 is url2                                   # same object: never re-encoded
    assert url1.startswith("data:image/jpeg;base64,")
    import base64
    img = Image.open(io.BytesIO(base64.b64decode(url1.split(",", 1)[1])))
    assert img.size == (480, 288)
    assert ar.ctx_image("a3", (960, 576)) is not url1


def test_refs_for_action_and_has(tmp_path):
    ar = FrameArchive(tmp_path)
    ar.put(observation(0))
    ar.put(observation(1, n_film=2))
    assert ar.refs_for(1) == ["a1.f0", "a1.f1", "a1"]
    assert ar.has("a1.f1") and not ar.has("a1.f2")


def test_index_survives_reopen(tmp_path):
    ar = FrameArchive(tmp_path)
    ar.put(observation(0))
    ar2 = FrameArchive(tmp_path)
    assert ar2.has("a0")
    assert ar2.get("a0") == ar.get("a0")


def test_derived_crops_are_archived_and_indexed(tmp_path):
    ar = FrameArchive(tmp_path)
    ar.put(observation(4, n_film=1))
    crop = ar.get("a4", region=[0.1, 0.55, 0.45, 1.0])
    ref = ar.put_derived("a4", crop, region=[0.1, 0.55, 0.45, 1.0])
    assert ref == "a4#c1" and ar.has(ref) and ar.get(ref) == crop
    row = ar.info(ref)
    assert row["kind"] == "crop" and row["parent"] == "a4" and row["region"] == [0.1, 0.55, 0.45, 1.0] and row["action"] == 4
    assert (tmp_path / "frames" / row["file"]).exists() and row["file"].startswith("a004")
    assert ar.refs_for(4) == ["a4.f0", "a4"]                    # capture frames only; crops are derived
    assert ar.put_derived("a4", crop, region=[0.1, 0.55, 0.45, 1.0]) == "a4#c1"   # same crop -> same ref
    assert ar.put_derived("a4", crop, region=[0.0, 0.0, 0.5, 0.5]) == "a4#c2"
    assert FrameArchive(tmp_path).has("a4#c1")
