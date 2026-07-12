from __future__ import annotations

import threading
import time


def test_singleflight_reuses_completed_result():
    from app.services.company_v2_financial_fusion_singleflight import company_v2_financial_fusion_singleflight

    company_v2_financial_fusion_singleflight.clear()
    calls = {"count": 0}
    first_started = threading.Event()
    release = threading.Event()

    def work():
        calls["count"] += 1
        first_started.set()
        release.wait(1)
        time.sleep(0.01)
        return {"ok": True}

    result = {}

    def run_first():
        result["first"] = company_v2_financial_fusion_singleflight.run("key", work, request_id="r1")

    def run_second():
        first_started.wait(1)
        result["second"] = company_v2_financial_fusion_singleflight.run("key", work, request_id="r2")

    t1 = threading.Thread(target=run_first)
    t2 = threading.Thread(target=run_second)
    t1.start()
    t2.start()
    first_started.wait(1)
    release.set()
    t1.join(2)
    t2.join(2)

    assert calls["count"] == 1
    assert result["first"]["singleflight_status"] == "completed"
    assert result["second"]["singleflight_status"] == "reused"
