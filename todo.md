**整体功能总结（咸鱼 Insight）**

1. **核心目标**  
把闲鱼商品流转成“可执行的买方决策”：自动采集、清洗判定、定价分层、机会排序、运行可控。

2. **数据采集能力**  
支持附着浏览器的批量采集与首页监控，按任务配置持续拉取在售数据并入库。  
关键位置：[monitor_tasks.json](<repo-root>/apps/collector/configs/monitor_tasks.json)

3. **清洗与判定能力（Review V3）**  
有 first-pass 全量清洗与 second-pass 复审机制，对条目做有效性/置信度/待复审分流，并支持长跑与续跑。  
关键位置：[run_review_v3_top_items_orchestrator.py](<repo-root>/scripts/run_review_v3_top_items_orchestrator.py)

4. **定价与机会判断能力**  
基于模板属性与样本证据输出三条价格线（安全收货/正常收货/市场中位），并给出可靠度、利润区间和机会标签。  
关键位置：[PricingPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/PricingPanel.tsx)

5. **看板能力（3 个主页面）**  
- `/`：交易主看板（筛选、定价、挂牌机会、焦点卡、趋势/校准参考）  
- `/llm-devops`：LLM 调用追踪与 Token 成本分析  
- `/runtime`：本机常驻任务控制台（状态、建议动作、执行回声）  
关键位置：[App.tsx](<repo-root>/apps/dashboard-react/src/app/App.tsx)

6. **配置与运营能力**  
提供大类、属性、任务、模板、型号、raw cate policy 等配置页面，以及 onboarding 页面，支持持续迭代规则与词典。  
关键位置：[config.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/config.py)

7. **运维与可观测能力**  
有进度脚本、runtime 动作入口、常驻服务控制（launchd），可持续监控“是否在跑、跑到哪、哪里坏”。  
关键位置：[show-review-v3-progress.sh](<repo-root>/scripts/show-review-v3-progress.sh)

一句话：这套系统已经形成了“采集 -> 清洗 -> 定价 -> 决策 -> 运维闭环”的完整本地交易分析平台。