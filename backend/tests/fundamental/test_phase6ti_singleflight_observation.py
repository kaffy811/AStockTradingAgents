from __future__ import annotations

import threading
import time


def test_singleflight_reuses_concurrent_requests():
    from app.services.company_v2_financial_fusion_singleflight import company_v2_financial_fusion_singleflight

    company_v2_financial_fusion_singleflight.clear()
    results = [None, None, None]
    barrier = threading.Barrier(3)

    def work():
        time.sleep(0.05)
        return {"status": "passed", "value": 1}

    def worker(idx: int) -> None:
        barrier.wait()
        results[idx] = company_v2_financial_fusion_singleflight.run("stage1-singleflight", work, request_id=f"req-{idx}")

    threads = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(1 for item in results if item["singleflight_status"] == "completed") == 1
    assert sum(1 for item in results if item["singleflight_status"] == "reused") == 2
    assert len({item["value"] for item in results}) == 1
