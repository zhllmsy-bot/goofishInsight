# apps/web

`apps/web` 现在是 legacy Jinja 支持面，不是产品主路径。

当前保留范围：

- 运维与配置页
- 少量历史详情页和进度页
- 仍被 `serve-web` 承载的模板与静态资产

约束：

- 新的买方主流程优先落到 `apps/dashboard-react`
- 不再把 Jinja 页面当作首页、机会主队列或新功能默认落点
- 如果继续保留，必须明确 support/admin 边界；否则进入归档候选
