from __future__ import annotations

import threading
import time


def test_singleflight_three_requests_compute_once():
    from app.services.company_v2_financial_fusion_singleflight import CompanyV2FinancialFusionSingleflight

    sf = CompanyV2FinancialFusionSingleflight()
    compute_count = 0
    barrier = threading.Barrier(3)
    results = []

    def work():
        nonlocal compute_count
        compute_count += 1
        time.sleep(0.05)
        return {"ok": True, "value": 1}

    def runner():
        barrier.wait()
        results.append(sf.run("same-key", work))

    threads = [threading.Thread(target=runner) for _ in range(3)]
    for item in threads:
        item.start()
    for item in threads:
        item.join()
    assert compute_count == 1
    assert sum(1 for item in results if item["singleflight_status"] == "completed") == 1
    assert sum(1 for item in results if item["singleflight_status"] == "reused") == 2
    assert all(item["value"] == 1 for item in results)
