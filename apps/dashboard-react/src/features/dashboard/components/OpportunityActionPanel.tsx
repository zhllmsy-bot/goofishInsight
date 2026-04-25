import { Link } from 'react-router-dom';

import { AnalyticsCard, KpiTile, OpportunityCard, type DecisionBucket } from '../../../shared/components/business';
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
  const buyWorkbenchTarget = buildWorkspaceLocation('/', props.query);
  const selectedScopeLabel = props.query.productLabel
    ? props.query.specLabel
      ? `${props.query.productLabel} / ${props.query.specLabel}`
      : props.query.productLabel
    : null;
  const description = selectedScopeLabel
    ? `当前证据工作区聚焦 ${selectedScopeLabel}，但真正应该先处理的是 ${categoryLabel(props.query.categoryCode)} 机会队列。先做动作，再回到证据页核验。`
    : `先处理 ${categoryLabel(props.query.categoryCode)} 今天最值得看的机会，再回到下面的证据看板确认价格线、成交锚点和风险解释。`;

  return (
    <AnalyticsCard
      actions={
        <>
          <Link className="nav-pill is-action" to={buyWorkbenchTarget}>
            打开机会队列
          </Link>
          <span className="soft-pill">{categoryLabel(props.query.categoryCode)}</span>
          {selectedScopeLabel ? <span className="soft-pill">证据上下文 {selectedScopeLabel}</span> : null}
        </>
      }
      className="opportunity-action-panel"
      description={description}
      eyebrow="Opportunity First"
      title="先处理今天最值得看的机会"
    >

      <div className="opportunity-action-stats" aria-label="机会工作区摘要">
        <KpiTile
          label="机会池"
          subtitle={`基线 ${formatNumber(summary?.baselineCount)} · 目标 ${formatNumber(summary?.watchTargetCount)}`}
          value={formatNumber(summary?.opportunityCount)}
        />
        <KpiTile
          label="今日机会"
          subtitle="按 last_detected_at 近 24 小时统计"
          tone="info"
          value={formatNumber(summary?.todayOpportunityCount)}
        />
        <KpiTile
          label="提醒命中"
          subtitle={`${formatNumber(summary?.alertHitCount)} / ${formatNumber(summary?.alertCount)} 条提醒被判定值得看`}
          tone="success"
          value={formatPercent((summary?.alertHitRate ?? 0) * 100, 1)}
        />
        <KpiTile
          label="反馈回流"
          subtitle={`采纳 ${formatNumber(summary?.acceptCount)} · 拒绝 ${formatNumber(summary?.rejectCount)}`}
          value={formatNumber(summary?.feedbackCount)}
        />
        <KpiTile
          label="校准动作"
          subtitle="优先用真实反馈去修正阈值、模板字段和排序权重"
          tone="warning"
          value={formatNumber(summary?.calibrationRecommendationCount)}
        />
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
            const detailTarget = buildWorkspaceLocation(`/opportunity/${opportunity.id}`, props.query);
            const evidenceTarget = evidenceItemId
              ? buildWorkspaceLocation(`/items/${evidenceItemId}`, props.query)
              : null;
            const stateLabel = [opportunity.status, opportunity.decision].filter(Boolean).join(' · ') || '待处理';

            return (
              <OpportunityCard
                actions={
                  <>
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
                  </>
                }
                className="opportunity-preview-card"
                decision={resolveDecisionBucket(opportunity.decision)}
                decisionLabel={stateLabel}
                eyebrow={stateLabel}
                key={opportunity.id}
                price={formatCurrency(opportunity.currentPrice)}
                score={formatNumber(opportunity.opportunityScore)}
                title={opportunity.title ?? opportunity.itemId ?? opportunity.itemIdRef ?? '未命名商品'}
              >

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
              </OpportunityCard>
            );
          })
        ) : (
          <div className="opportunity-preview-empty">
            当前品类还没有可执行机会。先继续积累样本或回到运行后台刷新 baseline / opportunity 作业。
          </div>
        )}
      </div>
    </AnalyticsCard>
  );
}

function resolveDecisionBucket(decision: string | null | undefined): DecisionBucket {
  const value = decision?.toLowerCase() ?? '';
  if (value.includes('buy') || value.includes('action')) {
    return 'buy';
  }
  if (value.includes('watch')) {
    return 'watch';
  }
  if (value.includes('high') || value.includes('expensive')) {
    return 'high';
  }
  if (value.includes('market')) {
    return 'market';
  }
  return 'neutral';
}
