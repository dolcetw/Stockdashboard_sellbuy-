# broker-top15

每個交易日自動抓上市櫃個股「主力進出前 15 大買超 / 賣超分點」(單位：張)。

- 排程：GitHub Actions，台北時間週一~五 19:07（21:07 補跑，已有當日資料自動跳過）
- 來源：富邦 DJ 個股主力進出頁 (zco)，近一日
- 輸出：`data/YYYY/broker_top15_YYYYMMDD.csv.gz`、`data/latest.csv.gz`、`data/latest.json`
- NAS：`nas/pull_broker_top15.sh` 放進 DSM 任務排程表，每天 21:30 拉回

欄位：date, stock_id, name, market, side(買超/賣超), rank, broker_id, broker, buy, sell, net(賣超為負), pct_of_volume
