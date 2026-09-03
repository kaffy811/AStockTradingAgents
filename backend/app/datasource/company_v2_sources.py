from __future__ import annotations


def get_akshare_quote_provider():
    from app.datasource.akshare_coverage_providers import akshare_quote_provider
    return akshare_quote_provider


def get_akshare_financial_providers():
    from app.datasource.akshare_coverage_providers import (
        akshare_indicator_provider,
        akshare_statement_provider,
    )
    return akshare_statement_provider, akshare_indicator_provider
