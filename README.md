# 烘焙当日减损结算

面向门店值班的本地工作台。内置业务样例覆盖连锁烘焙余货回归、临期折扣与回款对账。样例采用确定性构造，适合复现实验和核查边界行为。

## 启动

```sh
docker compose up --build -d
```

打开 `http://127.0.0.1:18208/` 查看折价结算单。左侧六个入口可展开运行证据。调整「折扣预算（元）」，点击「重算折扣」比较处置结果。结束后执行 `docker compose down --remove-orphans`。

## 独立业务模块

- 炉次流水 `bake_lots`
- 损耗核算 `waste_reconcile`
- 余货拟合 `leftover_curve`
- 折价区间 `markdown_bands`
- 促销限量 `shelf_action`
- 日结汇总 `drawer_close`

## 查看运行结果

- `GET /api/overview` 返回默认运行及其指纹。
- `POST /api/scenario` 接收 `{"capacity": 3}`。入口接受 1–100 的整数，应用样例时使用该业务额度。
- `GET /api/stages/drawer_close` 查看该环节的独立证据，支持 `?capacity=3`。

```sh
docker compose exec -T app python -m bakerylot.delivery evaluate --capacity 3
docker compose exec -T app pytest -q
```

数据和模型约定见 [业务契约](docs/SPEC.md)。模块、例外规则与验证入口见 [业务深度](docs/DEPTH.md)。
