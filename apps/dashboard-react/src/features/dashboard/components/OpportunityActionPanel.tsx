import { Link } from 'react-router-dom';

import type { BuyWorkbench } from '../../buy/types/buy';
import { categoryLabel, formatCurrency, formatNumber, formatPercent, formatRelative } from '../lib/formatters';
import { buildWorkspaceLocation } from '../lib/urlState';
import type { QueryState } from '../types/dashboard';

type OpportunityActionPanelProps = {
  error: string | null;
  isLoading: boolean;
  query: QueryState;
  workbench: BuyWorkbench | null;
};

export function OpportunityActionPanel(props: OpportunityActionPanelProps) {
  const summary = props.workbench?.summary;
  const opportunities = (props.workbench?.opportunities ?? []).slice(0, 3);
  const buyWorkbenchTarget = buildWorkspaceLocation('/buy/opportunities', props.query);
  const selectedScopeLabel = props.query.productLabel
    ? props.query.specLabel
      ? `${props.query.productLabel} / ${props.query.specLabel}`
      : props.query.productLabel
    : null;
  const description = selectedScopeLabel
    ? `当前证据工作区聚焦 ${selectedScopeLabel}，但真正应该先处理的是 ${categoryLabel(props.query.categoryCode)} 机会队列。先做动作，再回到证据页核验。`
    : `先处理 ${categoryLabel(props.query.categoryCode)} 今天最值得看的机会，再回到下面的证据看板确认价格线、成交锚点和风险解释。`;

  return (
    <section className="opportunity-action-panel">
      <div className="opportunity-action-header">
        <div>
          <p className="eyebrow">Opportunity First</p>
          <h2>先处理今天最值得看的机会</h2>
          <p className="panel-subtitle">{description}</p>
        </div>
        <div className="opportunity-action-cta">
          <Link className="nav-pill is-action" to={buyWorkbenchTarget}>
            打开机会队列
          </Link>
          <span className="soft-pill">{categoryLabel(props.query.categoryCode)}</span>
          {selectedScopeLabel ? <span className="soft-pill">证据上下文 {selectedScopeLabel}</span> : null}
        </div>
      </div>

      <div className="opportunity-action-stats" aria-label="机会工作区摘要">
        <div className="opportunity-action-stat">
          <span>机会池</span>
          <strong>{formatNumber(summary?.opportunityCount)}</strong>
          <small>基线 {formatNumber(summary?.baselineCount)} · 目标 {formatNumber(summary?.watchTargetCount)}</small>
        </div>
        <div className="opportunity-action-stat">
          <span>今日机会</span>
          <strong>{formatNumber(summary?.todayOpportunityCount)}</strong>
          <small>按 last_detected_at 近 24 小时统计</small>
        </div>
        <div className="opportunity-action-stat">
          <span>提醒命中</span>
          <strong>{formatPercent((summary?.alertHitRate ?? 0) * 100, 1)}</strong>
          <small>{formatNumber(summary?.alertHitCount)} / {formatNumber(summary?.alertCount)} 条提醒被判定值得看</small>
        </div>
        <div className="opportunity-action-stat">
          <span>反馈回流</span>
          <strong>{formatNumber(summary?.feedbackCount)}</strong>
          <small>采纳 {formatNumber(summary?.acceptCount)} · 拒绝 {formatNumber(summary?.rejectCount)}</small>
        </div>
        <div className="opportunity-action-stat">
          <span>校准动作</span>
          <strong>{formatNumber(summary?.calibrationRecommendationCount)}</strong>
          <small>优先用真实反馈去修正阈值、模板字段和排序权重</small>
        </div>
      </div>

      {props.error ? <div className="error-banner">{props.error}</div> : null}

      <div className="opportunity-preview-grid">
        {props.isLoading && !props.workbench ? (
          <div className="opportunity-preview-empty">
            正在同步机会池与反馈校准，完成后这里会优先展示今天最该处理的标的。
          </div>
        ) : opportunities.length ? (
          opportunities.map((opportunity) => {
            const evidenceItemId = opportunity.itemId ?? opportunity.itemIdRef;
            const detailTarget = buildWorkspaceLocation(`/buy/opportunities/${opportunity.id}`, props.query);
            const evidenceTarget = evidenceItemId
              ? buildWorkspaceLocation(`/items/${evidenceItemId}`, props.query)
              : null;
            const stateLabel = [opportunity.status, opportunity.decision].filter(Boolean).join(' · ') || '待处理';

            return (
              <article className="opportunity-preview-card" key={opportunity.id}>
                <div className="opportunity-preview-head">
                  <div>
                    <p className="eyebrow">{stateLabel}</p>
                    <h3>{opportunity.title ?? opportunity.itemId ?? opportunity.itemIdRef ?? '未命名商品'}</h3>
                  </div>
                  <div className="opportunity-preview-score">
                    <span className="soft-pill is-accent">机会 {formatNumber(opportunity.opportunityScore)}</span>
                    <span className="soft-pill">风险 {formatNumber(opportunity.riskScore)}</span>
                  </div>
                </div>

                <div className="opportunity-preview-metrics">
                  <div>
                    <small>当前价</small>
                    <strong>{formatCurrency(opportunity.currentPrice)}</strong>
                  </div>
                  <div>
                    <small>买入线</small>
                    <strong>{formatCurrency(opportunity.buyCeiling)}</strong>
                  </div>
                  <div>
                    <small>最近发现</small>
                    <strong>{formatRelative(opportunity.lastDetectedAt)}</strong>
                  </div>
                </div>

                <p className="panel-subtitle">
                  {opportunity.explanation?.readinessSummary ?? '等待更多证据与反馈信号。'}
                </p>

                <div className="opportunity-preview-actions">
                  <Link className="nav-pill is-action" to={detailTarget}>
                    查看详情
                  </Link>
                  {evidenceTarget ? (
                    <Link className="nav-pill" to={evidenceTarget}>
                      看证据
                    </Link>
                  ) : null}
                  <Link className="nav-pill" to={buyWorkbenchTarget}>
                    去机会队列处理
                  </Link>
                  {opportunity.listingUrl ? (
                    <a className="nav-pill" href={opportunity.listingUrl} rel="noreferrer" target="_blank">
                      打开原始商品
                    </a>
                  ) : null}
                </div>
              </article>
            );
          })
        ) : (
          <div className="opportunity-preview-empty">
            当前品类还没有可执行机会。先继续积累样本或回到运行后台刷新 baseline / opportunity 作业。
          </div>
        )}
      </div>
    </section>
  );
}
