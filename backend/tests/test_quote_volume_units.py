from unittest.mock import MagicMock
import pytest
from app.data.providers.sina_provider import SinaQuoteProvider
from app.services.stock_data_service import StockDataService


def test_sina_quantity_is_already_shares(monkeypatch):
    fields = [''] * 33
    for i,v in {0:'测试公司',1:'9.61',2:'9.77',3:'9.55',4:'9.67',5:'9.31',
                8:'83790350',9:'797136996',30:'2026-10-26',31:'15:00:00'}.items():
        fields[i] = v
    response = MagicMock()
    response.text = 'var hq_str_sh600186="' + ','.join(fields) + '";'
    response.content = response.text.encode('gb18030')
    monkeypatch.setattr('app.data.providers.sina_provider.requests.get', lambda *a,**kw: response)
    result = SinaQuoteProvider().get_quote('CN','600186')
    assert result['volume'] == 83790350
    assert 9.31 <= result['amount']/result['volume'] <= 9.67


@pytest.mark.parametrize('market,expected', [('CN',1000),('HK',10)])
def test_kline_proxy_normalizes_lots_to_quote_shares(monkeypatch,market,expected):
    import app.services.stock_data_service as module
    monkeypatch.setattr(module.cache,'get_kline_stale',lambda *a: ({'bars':[{'close':10,'volume':10}]},True))
    service = object.__new__(StockDataService)
    assert service._kline_proxy_quote(market,'600186')['volume'] == expected
