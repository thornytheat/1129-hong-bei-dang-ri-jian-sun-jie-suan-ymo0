# 烘焙当日减损结算功能与验证

领域为 AI/ML / 传统ML。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 炉次流水 | 追踪炉口转柜，查验修订冲突和下架边界 | 运行证据第 1 段 | `src/bakerylot/bake_lots/contracts.py` `src/bakerylot/bake_lots/analysis.py` `src/bakerylot/bake_lots/service.py` | `tests/test_bake_lots.py` |
| M2 损耗核算 | 核对出炉量、捐赠、破损和销售过账 | 运行证据第 2 段 | `src/bakerylot/waste_reconcile/contracts.py` `src/bakerylot/waste_reconcile/analysis.py` `src/bakerylot/waste_reconcile/service.py` | `tests/test_waste_reconcile.py` |
| M3 余货拟合 | 按商品回放尾段销量，隔离迟到和右删失样本 | 运行证据第 3 段 | `src/bakerylot/leftover_curve/contracts.py` `src/bakerylot/leftover_curve/analysis.py` `src/bakerylot/leftover_curve/service.py` | `tests/test_leftover_curve.py` |
| M4 折价区间 | 复核校准误差、库存风险上界和工况距离 | 运行证据第 4 段 | `src/bakerylot/markdown_bands/contracts.py` `src/bakerylot/markdown_bands/analysis.py` `src/bakerylot/markdown_bands/service.py` | `tests/test_markdown_bands.py` |
| M5 促销限量 | 按柜台和商品占用折扣预算与授予量 | 运行证据第 5 段 | `src/bakerylot/shelf_action/contracts.py` `src/bakerylot/shelf_action/analysis.py` `src/bakerylot/shelf_action/service.py` | `tests/test_shelf_action.py` |
| M6 日结汇总 | 核对现金、抵扣券和授予额度，跟踪待查单 | 运行证据第 6 段 | `src/bakerylot/drawer_close/contracts.py` `src/bakerylot/drawer_close/analysis.py` `src/bakerylot/drawer_close/service.py` | `tests/test_drawer_close.py` |

## 陷阱登记

| TRAP | 输入情形 | 错误风险 | 处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-23 | 临期下架边界 | 到期分钟仍准许销售 | 采用半开营业区间 | `src/bakerylot/bake_lots/analysis.py` | `tests/test_bake_lots.py::test_shelf_expiry_is_exclusive` |
| TRAP-26 | 迟到的旧修订 | 按接收顺序覆盖当前炉次 | 显式最大修订并冻结冲突 | `src/bakerylot/bake_lots/analysis.py` | `tests/test_bake_lots.py::test_newer_revision_wins_independent_of_order` |
| TRAP-24 | 多收据分摊优惠券 | 逐行舍入导致总账差一分 | 按整数最大余数分摊 | `src/bakerylot/shelf_action/analysis.py` | `tests/test_shelf_action.py::test_largest_remainder_conserves_voucher_cents` |
| TRAP-31 | 极端下架紧迫度 | 指数上溢使排队中断 | 对符号分支计算稳定 sigmoid | `src/bakerylot/markdown_bands/analysis.py` | `tests/test_markdown_bands.py::test_extreme_logits_do_not_overflow` |
| TRAP-32 | 均值大而变化小 | 二阶矩方差抵消 | 先中心化再累加偏差平方 | `src/bakerylot/leftover_curve/analysis.py` | `tests/test_leftover_curve.py::test_welford_equivalent_variance_stays_scaled` |
| TRAP-42 | 营业目标晚到账或从未来回流 | 偷偷学习未来销量 | 对业务日期与可见日期双重截断，过滤删失 | `src/bakerylot/leftover_curve/analysis.py` | `tests/test_leftover_curve.py::test_late_posted_history_does_not_change_training` |
| TRAP-43 | 校准桶没有验证样本 | 空集合误显示为百分之零 | 用 None 明示不可用并挂起审批 | `src/bakerylot/markdown_bands/analysis.py` | `tests/test_markdown_bands.py::test_no_validation_history_has_explicit_state` |
| TRAP-44 | 当前样本远超历史支持 | 相信高销量误把余货放行 | 分位误差区间并拒绝超距离样本 | `src/bakerylot/markdown_bands/analysis.py` | `tests/test_markdown_bands.py::test_distribution_shift_holds_high_forecast` |
| TRAP-53 | 一条与多条库存合并推断 | 按推断批重估缩放参数 | 存储不可变训练矩并逐样本计算 | `src/bakerylot/leftover_curve/analysis.py` | `tests/test_leftover_curve.py::test_mixed_batches_do_not_shift_predictions` |
