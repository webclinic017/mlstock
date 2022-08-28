import argparse
import logging
import time

import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import matplotlib.ticker as ticker

plt.rcParams['font.sans-serif'] = 'Microsoft YaHei'  # 中文和负号的正常显示
plt.rcParams['axes.unicode_minus'] = False

import joblib

from mlstock.ml.data import factor_service
from mlstock.utils import utils

logger = logging.getLogger(__name__)


def main(args):
    # 查看数据文件和模型文件路径是否正确
    utils.check_file_path(args.data)
    if args.model_pct: utils.check_file_path(args.model_pct)
    if args.model_winloss: utils.check_file_path(args.model_winloss)

    # 加载数据
    df_data = factor_service.load_from_file(args.data)
    original_size = len(df_data)
    original_start_date = df_data.trade_date.min()
    original_end_date = df_data.trade_date.max()
    df_data = df_data[df_data.trade_date >= args.start_date]
    df_data = df_data[df_data.trade_date <= args.end_date]
    logger.debug("数据%s~%s %d行，过滤后=> %s~%s %d行",
                 original_start_date, original_end_date, original_size,
                 args.start_date, args.end_date, len(df_data))

    # 加载模型；如果参数未提供，为None
    model_pct = joblib.load(args.model_pct) if args.model_pct else None
    model_winloss = joblib.load(args.model_winloss) if args.model_winloss else None

    if model_pct:
        start_time = time.time()
        df_data['pred_pct'] = df_data.apply(lambda x: model_pct.predict(x), axis=1)
        utils.time_elapse(start_time, f"预测下期收益: {len(df_data)}行 ")

    if model_pct:
        start_time = time.time()
        df_data['pred_winloss'] = df_data.apply(lambda x: model_winloss.predict(x), axis=1)
        utils.time_elapse(start_time, f"预测下期涨跌: {len(df_data)}行 ")

    df_pct = calculate_pct_chg(df_data)
    plot(df_pct)


def calculate_pct_chg(df):
    # 先把所有预测为跌的全部过滤掉
    original_size = len(df)
    df = df[df.pred_winloss == 1]
    logger.debug("根据涨跌模型结果，过滤数据 %d=>%d", original_size, len(df))

    # 先按照日期 + 预测的rank排序
    df = df.sort_values(['trade_date', 'y_pred'])
    # 按照日期分组，每组里面取前30，然后算收益率，作为组合资产的收益率
    # 注意！这里是下期收益"next_pct_change"的均值，实际上是提前了一期（这个细节可以留意一下）
    df_pct = df.groupby('trade_date')['next_pct_change', 'pct_chg_baseline'].apply(
        lambda df_group: df_group[:30].mean())
    df_pct[['cumulative_pct_chg', 'cumulative_pct_chg_baseline']] = df_pct.apply(lambda x: (x + 1).cumprod() - 1)
    return df_pct


def plot(df):
    """
    1. 每期实际收益
    2. 每期实际累计收益
    3. 基准累计收益率
    4. 上证指数
    :param df:
    :return:
    """

    x = df.trade_date.values
    y1 = df.next_pct_chg.values
    y2 = df.cumulative_pct_chg.values
    y3 = df.cumulative_pct_chg_basline.values
    color_y1 = '#2A9CAD'
    color_y2 = "#FAB03D"
    color_y3 = "#FAFF0D"
    title = '资产组合收益率及累积收益率'
    label_x = '周'
    label_y1 = '资产组合周收益率'
    label_y2 = '资产组合累积收益率'
    label_y3 = '基准累积收益率'
    fig, ax1 = plt.subplots(figsize=(10, 6), dpi=300)
    plt.xticks(rotation=60)
    # ax2.set_xticks(x[::2])
    # ax2.set_xticklabels(x[::2], rotation=60)
    ax2 = ax1.twinx()  # 做镜像处理

    ax1.bar(x=x, height=y1, label=label_y1, color=color_y1, alpha=0.7)
    ax2.plot(x, y2, color=color_y2, ms=10, label=label_y2)
    ax2.plot(x, y3, color=color_y3, ms=10, label=label_y3)

    ax1.set_xlabel(label_x)  # 设置x轴标题
    ax1.set_ylabel(label_y1)  # 设置Y1轴标题
    ax2.set_ylabel(label_y2 + "/" + label_y3)  # 设置Y2轴标题
    ax1.grid(False)
    ax2.grid(False)
    # 设置横轴显示,设置密度，比如横坐标9个，设置这个为3,到时候横坐标上就显示 9/3=3个横坐标，
    ax1.xaxis.set_major_locator(ticker.MultipleLocator(tick_spacing=6))
    # 添加标签
    ax1.legend(loc='upper left')
    ax2.legend(loc='upper right')
    plt.title(title)  # 添加标题
    plt.grid(axis="y")  # 背景网格

    # 保存图片
    save_path = 'data/plot.jpg'
    plt.savefig(save_path)
    plt.show()


if __name__ == '__main__':
    utils.init_logger(file=True)
    parser = argparse.ArgumentParser()

    # 数据相关的
    parser.add_argument('-s', '--start_date', type=str, default="20190101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20220901", help="结束日期")
    parser.add_argument('-d', '--data', type=str, default=None, help="数据文件")
    parser.add_argument('-mp', '--model_pct', type=str, default=None, help="收益率模型")
    parser.add_argument('-mw', '--model_winloss', type=str, default=None, help="涨跌模型")

    args = parser.parse_args()

    main(args)