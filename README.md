
# 前言

感谢B站UP主[致敬大神](https://www.bilibili.com/video/BV1564y1b7PR)，这个项目是站在她的华泰金工的研报复现的基础上的一个项目。

她虽然已经给出了完整的代码，但是我更想在她的工作基础上，做成一个可以一键run的机器学习项目，方便更好的高效运行。

也通过对她的代码的重新梳理、理解和调试，更好的理解和掌握机器学习在量化投资中的应用。

这个项目计划会持续2~3个月，可以持续关注。

# 开发日志

7.28
- 为了防止macd之类出现nan，预加载了一些日期的数据，目前是观察后，设置为35，加载完再用start_date过滤掉之前的
- 过滤了那些全是nan的财务指标的股票，比如cash_in_subtotal_finance、cash_in_subtotal_invest，4077=>3263，比例20%
- 