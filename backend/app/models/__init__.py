from app.models.user import User                      # noqa: F401 — keeps ORM metadata populated
from app.models.analysis_report import AnalysisReport  # noqa: F401
from app.models.industry import IndustryMaster, StockIndustryMap  # noqa: F401
from app.models.industry_hot_stock import IndustryHotStockSnapshot  # noqa: F401
from app.models.watchlist_item import WatchlistItem                  # noqa: F401
from app.models.stock_master import StockMaster                      # noqa: F401
from app.models.data_coverage import (                               # noqa: F401
    DataCoverageSnapshot, ProviderErrorLog, MissingFieldQueue,
)
from app.models.company_v2_report_rag import ReportRagDocument, ReportRagChunk  # noqa: F401
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob  # noqa: F401
