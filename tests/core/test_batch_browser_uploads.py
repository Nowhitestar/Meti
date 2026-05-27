from pathlib import Path

import pytest


def _write_png(path: Path) -> None:
    # Minimal PNG signature is enough for this layer; browser JS gets base64 bytes only.
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)


@pytest.mark.parametrize(
    "module_name,max_mb",
    [
        ("providers.xiaohongshu.internal.browser_flow", 32),
        ("providers.wechat_image.internal.browser_flow", 30),
    ],
)
def test_upload_images_batch_stages_payload_then_runs_upload_eval(
    tmp_path, monkeypatch, module_name, max_mb
):
    module = __import__(module_name, fromlist=["dummy"])
    image1 = tmp_path / "one.png"
    image2 = tmp_path / "two.png"
    _write_png(image1)
    _write_png(image2)

    staged = []
    eval_calls = []

    def fake_stage_text_payload(payload, **kwargs):
        staged.append((payload, kwargs))
        return "payload-key"

    def fake_evaluate(js):
        eval_calls.append(js)
        return {"ok": True, "uploaded": 2, "expected": 2}

    import core.browser as br

    monkeypatch.setattr(br, "stage_text_payload", fake_stage_text_payload)
    monkeypatch.setattr(br, "evaluate", fake_evaluate)
    monkeypatch.setattr(
        module.time,
        "sleep",
        lambda *_args, **_kwargs: pytest.fail("batch upload should not use fixed per-image sleep"),
    )

    module._upload_images_batch([str(image1), str(image2)])

    assert len(staged) == 1
    assert "one.png" in staged[0][0]
    assert "two.png" in staged[0][0]
    assert str(max_mb) in staged[0][0] or staged[0][0]
    assert staged[0][1]["prefix"].startswith("meti-")
    assert len(eval_calls) == 2
    assert "payload-key" in eval_calls[0]
    assert "payload-key" in eval_calls[1]
    assert "DataTransfer" in eval_calls[1]


@pytest.mark.parametrize(
    "module_name",
    [
        "providers.xiaohongshu.internal.browser_flow",
        "providers.wechat_image.internal.browser_flow",
    ],
)
def test_upload_images_batch_rejects_partial_upload_ack(tmp_path, monkeypatch, module_name):
    module = __import__(module_name, fromlist=["dummy"])
    image1 = tmp_path / "one.png"
    image2 = tmp_path / "two.png"
    _write_png(image1)
    _write_png(image2)

    import core.browser as br

    responses = iter(
        [
            {"ok": True, "chunks": 1, "expected": 1},
            {"ok": False, "uploaded": 1, "expected": 2},
        ]
    )

    monkeypatch.setattr(br, "stage_text_payload", lambda _payload, **_kwargs: "payload-key")
    monkeypatch.setattr(br, "evaluate", lambda _js: next(responses))

    with pytest.raises(RuntimeError, match="batch image upload"):
        module._upload_images_batch([str(image1), str(image2)])


@pytest.mark.parametrize(
    "module_name",
    [
        "providers.xiaohongshu.internal.browser_flow",
        "providers.wechat_image.internal.browser_flow",
    ],
)
def test_wait_for_js_condition_polls_until_ready(monkeypatch, module_name):
    module = __import__(module_name, fromlist=["dummy"])
    states = iter(
        [
            {"ready": False, "count": 0},
            {"ready": False, "count": 1},
            {"ready": True, "count": 2},
        ]
    )
    sleeps = []

    import core.browser as br

    monkeypatch.setattr(br, "evaluate", lambda _js: next(states))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = module._wait_for_js_condition(
        "(() => JSON.stringify({ready:true}))()", timeout_s=1, interval_s=0.01
    )

    assert result["ready"] is True
    assert len(sleeps) == 2
