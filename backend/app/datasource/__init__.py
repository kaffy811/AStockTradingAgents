"""
app/datasource — 数据源客户端层

提供对 Tushare Pro（主要）和 AkShare（可选备用）的统一封装。

使用方式：
    from app.datasource.tushare_client import tushare_client
    from app.datasource.akshare_client import akshare_fs_client  # 需 ENABLE_AKSHARE=true
"""
