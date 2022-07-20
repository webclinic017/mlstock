import logging
from abc import ABC, abstractmethod

from pandas import DataFrame

from mlstock.ml.train import StocksInfo

logger = logging.getLogger(__name__)


class Factor(ABC):
    """
    因子，也就是指标
    """

    def __init__(self, datasource, stocks_info: StocksInfo):
        self.datasource = datasource
        self.stocks_info = stocks_info

    # 英文名
    @property
    def name(self):
        return "Unknown"

    # 中文名
    @property
    def cname(self):
        return "未定义"

    @abstractmethod
    def calculate(self, df: DataFrame):
        raise ImportError()

    def _extract_fields(self, df: DataFrame):
        if "ann_date" in df.columns:
            df.rename({"ann_date", "trade_date"})
        df = df[['ts_code', 'ann_date'] + self.tushare_name]
        df = self._rename(self.tushare_name, df, self.name)
        return df

    def _rename(self, df: DataFrame, _from: list, _to: list):
        name_pair = dict(zip(_from, _to))
        return df.rename(name_pair)
