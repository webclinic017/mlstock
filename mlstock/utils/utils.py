import calendar
import datetime
import logging
import os
import time
import warnings
import numpy as np

import chinese_calendar
import matplotlib.pyplot as plt
import pandas as pd
import requests
import yaml
from backtrader.plot import Plot_OldSync
from backtrader_plotting.schemes import Tradimo
from dateutil.relativedelta import relativedelta
from empyrical import max_drawdown
from pandas import Series
import statsmodels.api as sm
from mlstock import const


logger = logging.getLogger(__name__)

DB_FILE = "../data/tushare.db"


def load_config():
    if not os.path.exists(const.CONF_PATH):
        raise ValueError("配置文件[conf/config.yml]不存在，请先创建它! (详细格式，可参考conf/config.sample.yml):" + const.CONF_PATH)
    f = open(const.CONF_PATH, 'r', encoding='utf-8')
    result = f.read()
    # 转换成字典读出来
    data = yaml.load(result, Loader=yaml.FullLoader)
    logger.info("读取配置文件:%r", const.CONF_PATH)
    return data


CONF = load_config()


class StockQuery():
    def __init__(self, stock_code, start_date=None, end_date=None, baseline=None):
        self.stock_code = stock_code
        self.start_date = start_date
        self.end_date = end_date
        self.baseline = baseline


def compile_stock_code(stock_code):
    """
    从 "600600=>600600.SH"
    股票编码：https://zhidao.baidu.com/question/340092837.html
    """
    if stock_code.endswith(".SH") or stock_code.endswith(".SZ"): return stock_code
    if stock_code.startswith("6"): return stock_code + ".SH"
    return stock_code + ".SZ"


def uncompile_stock_code(stock_code):
    """
    从 "600600.SH=>600600"
    股票编码：https://zhidao.baidu.com/question/340092837.html
    """
    if not "." in stock_code: return stock_code
    return stock_code[:stock_code.index(".")]


def uncomply_code(func):
    """
    一个包装器，用于方法中包含code的参数，把股票代码的后缀去掉（tushare是带后缀的，但是服务器不带）
    从 "600600.SH=>600600"
    这个用于把发往服务器的代码都统一成实盘代码
    """

    def wrapper_it(*args, **kw):
        import inspect
        args_spec = inspect.getfullargspec(func)
        args_names = args_spec.args
        index = args_names.index('code') if 'code' in args_names else -1
        if index == -1: return func(*args, **kw)
        args = list(args)
        args[index] = uncompile_stock_code(args[index])

        args = tuple(args)
        return func(*args, **kw)

    return wrapper_it


def str2date(s_date, format="%Y%m%d"):
    return datetime.datetime.strptime(s_date, format)


def str2pandasdate(s_date, format="%Y%m%d"):
    return pd.Timestamp(datetime.datetime.strptime(s_date, format))


def get_monthly_duration(start_date, end_date):
    """
    把开始日期到结束日期，分割成每月的信息
    比如20210301~20220515 =>
    [   [20210301,20210331],
        [20210401,20210430],
        ...,
        [20220401,20220430],
        [20220501,20220515]
    ]
    """

    start_date = str2date(start_date)
    end_date = str2date(end_date)
    years = list(range(start_date.year, end_date.year + 1))
    scopes = []
    for year in years:
        if start_date.year == year:
            start_month = start_date.month
        else:
            start_month = 1

        if end_date.year == year:
            end_month = end_date.month + 1
        else:
            end_month = 12 + 1

        for month in range(start_month, end_month):

            if start_date.year == year and start_date.month == month:
                s_start_date = date2str(datetime.date(year=year, month=month, day=start_date.day))
            else:
                s_start_date = date2str(datetime.date(year=year, month=month, day=1))

            if end_date.year == year and end_date.month == month:
                s_end_date = date2str(datetime.date(year=year, month=month, day=end_date.day))
            else:
                _, last_day = calendar.monthrange(year, month)
                s_end_date = date2str(datetime.date(year=year, month=month, day=last_day))

            scopes.append([s_start_date, s_end_date])

    return scopes


def get_yearly_duration(start_date, end_date):
    """
    把开始日期到结束日期，分割成每年的信息
    比如20210301~20220501 => [[20210301,20211231],[20220101,20220501]]
    """
    start_date = str2date(start_date)
    end_date = str2date(end_date)
    years = list(range(start_date.year, end_date.year + 1))
    scopes = [[f'{year}0101', f'{year}1231'] for year in years]

    if start_date.year == years[0]:
        scopes[0][0] = date2str(start_date)
    if end_date.year == years[-1]:
        scopes[-1][1] = date2str(end_date)

    return scopes


def duration(start, end, unit='day'):
    d0 = str2date(start)
    d1 = str2date(end)
    delta = d1 - d0
    if unit == 'day': return delta.days
    return None


def tomorrow(s_date=None):
    if s_date is None: s_date = today()
    return future('day', 1, s_date)


def yesterday(s_date=None):
    if s_date is None: s_date = today()
    return last_day(s_date, 1)


def last(date_type, unit, s_date):
    return __date_span(date_type, unit, -1, s_date)


def last_year(s_date, num=1):
    return last('year', num, s_date)


def last_month(s_date, num=1):
    return last('month', num, s_date)


def last_week(s_date, num=1):
    return last('week', num, s_date)


def last_day(s_date, num=1):
    return last('day', num, s_date)


def today():
    now = datetime.datetime.now()
    return datetime.datetime.strftime(now, "%Y%m%d")


def now():
    return datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%d%H%M%S")


def strf_delta(tdelta, fmt):
    d = {"days": tdelta.days}
    d["hours"], rem = divmod(tdelta.seconds, 3600)
    d["minutes"], d["seconds"] = divmod(rem, 60)
    d["milliseconds"], _ = divmod(tdelta.microseconds, 1000)
    return fmt.format(**d)


def time_elapse(start_time, title='', debug_level='info'):
    if debug_level == 'debug':
        logger.debug("%s耗时: %s ", title,
                     strf_delta(datetime.timedelta(seconds=time.time() - start_time),
                                "{days}天{hours}小时{minutes}分{seconds}秒{milliseconds}毫秒"))
    else:
        logger.info("%s耗时: %s ", title,
                    strf_delta(datetime.timedelta(seconds=time.time() - start_time),
                               "{days}天{hours}小时{minutes}分{seconds}秒"))
    return time.time()


def nowtime():
    now = datetime.datetime.now()
    return datetime.datetime.strftime(now, "%H:%M:%S")


def future(date_type, unit, s_date):
    return __date_span(date_type, unit, 1, s_date)


def __date_span(date_type, unit, direction, s_date):
    """
    last('year',1,'2020.1.3')=> '2019.1.3'
    :param unit:
    :param date_type: year|month|day
    :return:
    """
    the_date = str2date(s_date)
    if date_type == 'year':
        return date2str(the_date + relativedelta(years=unit) * direction)
    elif date_type == 'month':
        return date2str(the_date + relativedelta(months=unit) * direction)
    elif date_type == 'week':
        return date2str(the_date + relativedelta(weeks=unit) * direction)
    elif date_type == 'day':
        return date2str(the_date + relativedelta(days=unit) * direction)
    else:
        raise ValueError(f"无法识别的date_type:{date_type}")


def date2str(date, format="%Y%m%d"):
    return datetime.datetime.strftime(date, format)


def dataframe2series(df):
    if type(df) == Series: return df
    assert len(df.columns) == 1, df.columns
    return df.iloc[:, 0]


def get_last_trade_date_of_month(df):
    """
    得到每个月的最后一天的交易日
    :param df_trade_date: 所有交易日
    :return: 只保留每个月的最后一个交易日，其他剔除掉
    """
    df[df.index.day == df.index.days_in_month]


def get_last_trade_date(end_date, trade_dates, include_today=False):
    """
    得到日期范围内的最后的交易日，end_date可能不在交易日里，所以要找一个最近的日子
    :param df_trade_date: 所有交易日
    :return: 只保留每个月的最后一个交易日，其他剔除掉
    """
    # 反向排序
    trade_dates = trade_dates.tolist()
    trade_dates.reverse()

    # 寻找合适的交易日期
    for trade_date in trade_dates:

        if include_today:
            # 从最后一天开始找，如果交易日期(trade_date)比目标日期(end_date)小了，就找到了
            if trade_date <= end_date:
                return trade_date
        else:
            if trade_date < end_date:
                return trade_date

    return None


def get_holidays(from_year=2004, include_weekends=False):
    """
    获取所有节假日，默认从2004年开始,chinese_calendar只支持到2004
    """
    to_year = datetime.datetime.now().year
    start = datetime.date(from_year, 1, 1)
    end = datetime.date(to_year, 12, 31)
    holidays = chinese_calendar.get_holidays(start, end, include_weekends)
    return holidays


def get_period_ohlc(df_day, date, unit=4, unit_type='W'):
    """
    计算4周前这段时间的OHLC,
    这个必须要用day2week,day2month出来的结果，因为里面有这周的开始和结束
    """

    # 得到4周前的第一个工作日
    date_index = df_day.index
    # import pdb;pdb.set_trace()
    four_week_ago_first_weekday = \
        date_index[
            date_index > (date - pd.to_timedelta(unit, unit=unit_type)).to_period(unit_type).start_time
            ][0]

    df_period = df_day.loc[four_week_ago_first_weekday:date]
    df_result = pd.DataFrame()
    df_result['open'] = df_period.iloc[0]['open']
    df_result['close'] = df_period.iloc[-1]['close']
    df_result['high'] = df_period['high'].max()
    df_result['low'] = df_period['low'].min()
    df_result['volume'] = df_period['volume'].sum()
    df_result['from'] = df_period.head(1).index
    df_result['to'] = df_result.index
    df_result['pct_chg'] = (df_period.iloc[-1]['close'] - df_period.iloc[0]['open']) / df_period.iloc[0]['open']

    return df_result


class MyPlot(Plot_OldSync):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def show(self):
        plt.savefig("debug/backtrader回测.jpg")


def init_logger(file=False, simple=False, log_level=logging.DEBUG):
    print("开始初始化日志：file=%r, simple=%r" % (file, simple))

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').disabled = True
    logging.getLogger('matplotlib.colorbar').disabled = True
    logging.getLogger('matplotlib').disabled = True
    logging.getLogger('fontTools.ttLib.ttFont').disabled = True
    logging.getLogger('PIL').setLevel(logging.WARNING)
    warnings.filterwarnings("ignore")
    warnings.filterwarnings("ignore", module="matplotlib")
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    if simple:
        formatter = logging.Formatter('%(message)s')
    else:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d P%(process)d: %(message)s')

    root_logger = logging.getLogger()
    root_logger.setLevel(level=log_level)

    def is_any_handler(handlers, cls):
        for t in handlers:
            if type(t) == cls: return True
        return False

    # 加入控制台
    if not is_any_handler(root_logger.handlers, logging.StreamHandler):
        stream_handler = logging.StreamHandler()
        root_logger.addHandler(stream_handler)
        print("日志：创建控制台处理器")

    # 加入日志文件
    if file and not is_any_handler(root_logger.handlers, logging.FileHandler):
        if not os.path.exists("./logs"): os.makedirs("./logs")
        filename = "./logs/{}.log".format(time.strftime('%Y%m%d%H%M', time.localtime(time.time())))
        t_handler = logging.FileHandler(filename, encoding='utf-8')
        root_logger.addHandler(t_handler)
        print("日志：创建文件处理器", filename)

    handlers = root_logger.handlers
    for handler in handlers:
        handler.setLevel(level=log_level)
        handler.setFormatter(formatter)


def get_url(host=None, port=None, url=None, token=None):
    if host is None:
        host = CONF['broker_client']['host']
        port = CONF['broker_client']['port']
        url = CONF['broker_client']['url']
        token = CONF['broker_client']['token']
    return f"http://{host}:{port}/{url}?token={token}"


class AStockPlotScheme(Tradimo):
    """
    自定义的bar和volumn的显示颜色，follow A股风格
    """

    def _set_params(self):
        super()._set_params()
        self.barup = "#FC5D45"
        self.bardown = "#009900"
        self.barup_wick = self.barup
        self.bardown_wick = self.bardown
        self.barup_outline = self.barup
        self.bardown_outline = self.bardown
        self.volup = self.barup
        self.voldown = self.bardown


def http_json_post(url, dict_msg):
    logger.debug("向[%s]推送消息：%r", url, dict_msg)
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=dict_msg, headers=headers)
    logger.info('接口返回原始报文:%r', response.text if len(response.text) < 50 else response.text[:50] + "......")
    data = response.json()
    logger.info('接口返回Json报文:%r', data)
    return data


def logging_time(title=''):
    """
    一个包装器，用于记录函数耗时
    """

    def decorate(func):
        def wrapper_it(*args, **kw):
            start_time = time.time()
            result = func(*args, **kw)
            time_elapse(start_time, title, 'debug')
            return result

        return wrapper_it

    return decorate


def OLS(X, y):
    """
    做线性回归，返回 β0（截距）、β0（系数）和残差
    参考：https://blog.csdn.net/chongminglun/article/details/104242342
    :param X: shape(N,M)，M位X的维度，一般M=1
    :param y: shape(N)
    :return:
    """
    assert not np.isnan(X).any(), f'X序列包含nan:{X}'
    assert not np.isnan(y).any(), f'y序列包含nan:{y}'

    # 增加一个截距项
    X = sm.add_constant(X)
    # 定义模型
    model = sm.OLS(y, X)  # 定义x，y
    results = model.fit()
    return results.params, results.resid


def check_file_path(file_path):
    if not os.path.exists(file_path):
        msg = f"文件[{file_path}]不存在！"
        logger.error(msg)
        raise ValueError(msg)


# python -m mlstock.utils.utils
if __name__ == '__main__':
    import traceback

    X = np.array([1, 2, 3, 4, 5, 6])
    y = np.array([0.1, 2.1, 4.5, 0.3, 2.4, 5.0])
    print(OLS(X, y))

    X = np.array([1, 2, 3, 4, 5, 6])
    y = np.array([0.1, 2.1, np.nan, 0.3, 2.4, 5.0])
    print(OLS(X, y))

    X = np.array([1, 2, np.nan, 3, 4, 5])
    y = np.array([0.1, 2.1, 4.5, 0.3, 2.4, 5.0])
    print(OLS(X, y))
