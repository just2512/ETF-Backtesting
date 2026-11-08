from __future__ import annotations

from datetime import date

import pytest

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter
from etf_backtesting.data.index_history import export_index_snapshots
from etf_backtesting.data.provider_errors import ProviderQuotaExceeded


def test_novapi_quota_error_is_not_misclassified_as_transient():
    with pytest.raises(ProviderQuotaExceeded, match="测试期超2000次"):
        StockSDKAdapter._raise_on_service_error(
            "测试期超2000次，24小时内会重置",
            "get_index_weights",
            "000300.XSHG",
        )


def test_index_export_stops_after_provider_quota_exhaustion(tmp_path):
    class QuotaAdapter:
        calls = 0

        def read_history_constituents(self, index_id, snapshot_date):
            self.calls += 1
            raise ProviderQuotaExceeded("provider quota exhausted")

    adapter = QuotaAdapter()
    dates = [date(2022, 2, 8), date(2022, 2, 28), date(2022, 3, 31)]

    manifest = export_index_snapshots(
        adapter,
        "000300.XSHG",
        dates,
        symbol_field="code",
        weight_field="weight",
        weight_scale="fraction",
        output_dir=tmp_path,
    )

    assert adapter.calls == 1
    assert [row["status"] for row in manifest["results"]] == [
        "UNKNOWN", "NOT_ATTEMPTED", "NOT_ATTEMPTED"
    ]
    assert manifest["results"][0]["error_type"] == "ProviderQuotaExceeded"
