import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowUpRight,
  CircleDollarSign,
  ClipboardCheck,
  MessageCircle,
  Radar,
  ShieldAlert,
  SkipForward,
  Sparkles,
  Target,
} from 'lucide-react';

import { Badge } from '../../../shared/components/ui/badge';
import { Button } from '../../../shared/components/ui/button';
import { TerminalScreen } from '../../../shared/components/TerminalScreen';
import { PageHero } from '../../../shared/components/PageHero';
import { formatCurrency, formatNumber, formatPercent, formatRelative } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation, readInitialQuery } from '../../dashboard/lib/urlState';
import { useBuyWorkbench } from '../hooks/useBuyWorkbench';
import type { BuyDataValueReport, BuyFeedbackRequest, BuyOpportunity, BuyWorkbench } from '../types/buy';
import { PurchaseOutcomeForm } from './PurchaseOutcomeForm';

import '../../dashboard/styles/dashboard.css';
import '../styles/buy-workbench.css';

type FeedbackState = {
  kind: 'idle' | 'success' | 'error';
  message: string;
};

function formatDecimal(value: number | null | undefined, digits = 2): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  return numeric.toFixed(digits);
}

export function BuyWorkbenchPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const workspaceQuery = useMemo(() => readInitialQuery(location.search), [location.search]);
  const categoryCode = workspaceQuery.categoryCode;
  const {
    workbench,
    error,
    isLoading,
    isRefreshing,
    submitFeedback,
    feedbackPendingId,
    applyCalibration,
    calibrationPending,
  } = useBuyWorkbench(categoryCode, 50);
  const [feedbackByOpportunity, setFeedbackByOpportunity] = useState<Record<string, FeedbackState>>({});
  const [calibrationState, setCalibrationState] = useState<FeedbackState>({
    kind: 'idle',
    message: '',
  });
  const [purchaseOutcomeOpportunityId, setPurchaseOutcomeOpportunityId] = useState<string | null>(null);

  const feedback = workbench?.feedbackQuality;
  const calibration = workbench?.feedbackCalibration;
  const recommendations = calibration?.recommendations;
  const effectiveCalibrationConfig = calibration?.effectiveCalibrationConfig;
  const dataValue = workbench?.dataValue;
  const dailyOpportunityPack = workbench?.dailyOpportunityPack;
  const outcomeFunnel = workbench?.outcomeFunnel;
  const summary = workbench?.summary;
  const opportunities = workbench?.opportunities ?? [];
  const baselines = workbench?.baselines ?? [];
  const watchTargets = workbench?.watchTargets ?? [];
  const guidanceThresholds = effectiveCalibrationConfig?.pricingThresholds?.guidanceReady;
  const referenceThresholds = effectiveCalibrationConfig?.pricingThresholds?.referenceOnly;
  const scoringConfig = effectiveCalibrationConfig?.opportunityScoring;
  const lastAppliedRecommendationCount = effectiveCalibrationConfig?.lastAppliedRecommendationIds?.length ?? 0;
  const calibrationRecommendations = useMemo(
    () => [
      ...(recommendations?.templateFieldRecommendations ?? []),
      ...(recommendations?.thresholdRecommendations ?? []),
      ...(recommendations?.rankingRecommendations ?? []),
    ],
    [recommendations],
  );
  const selectableRecommendationIds = useMemo(
    () => calibrationRecommendations.map((recommendation) => recommendation.id).filter((id): id is string => Boolean(id)),
    [calibrationRecommendations],
  );
  const [selectedRecommendationIds, setSelectedRecommendationIds] = useState<string[]>([]);
  const selectedRecommendationIdSet = useMemo(
    () => new Set(selectedRecommendationIds),
    [selectedRecommendationIds],
  );
  const hasSelectableRecommendations = selectableRecommendationIds.length > 0;
  const selectedRecommendationCount = selectedRecommendationIds.length;

  const dashboardTarget = useMemo(
    () => buildWorkspaceLocation('/', workspaceQuery),
    [workspaceQuery],
  );
  const runtimeTarget = useMemo(
    () => buildWorkspaceLocation('/runtime', workspaceQuery),
    [workspaceQuery],
  );

  useEffect(() => {
    setSelectedRecommendationIds(selectableRecommendationIds);
  }, [selectableRecommendationIds]);

  async function handleFeedback(opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) {
    const linkToAlertCandidate = feedbackLabel === 'contacted';
    setFeedbackByOpportunity((current) => ({
      ...current,
      [opportunity.id]: {
        kind: 'idle',
        message: '提交中...',
      },
    }));

    try {
      const result = await submitFeedback({
        opportunityId: opportunity.id,
        feedbackLabel,
        linkToAlertCandidate,
      });
      const stateLabel = [result.status, result.decision].filter(Boolean).join(' · ') || feedbackLabel;
      setFeedbackByOpportunity((current) => ({
        ...current,
        [opportunity.id]: {
          kind: 'success',
          message: `已回写：${stateLabel}`,
        },
      }));
    } catch (mutationError) {
      const message = mutationError instanceof Error ? mutationError.message : '提交失败';
      setFeedbackByOpportunity((current) => ({
        ...current,
        [opportunity.id]: {
          kind: 'error',
          message,
        },
      }));
    }
  }

  async function handlePurchasedOutcome(
    opportunity: BuyOpportunity,
    outcome: Pick<BuyFeedbackRequest, 'purchasePrice' | 'expectedResalePrice' | 'feedbackNote'>,
  ) {
    setFeedbackByOpportunity((current) => ({
      ...current,
      [opportunity.id]: {
        kind: 'idle',
        message: '正在记录成交和 ROI 证据...',
      },
    }));

    try {
      const result = await submitFeedback({
        opportunityId: opportunity.id,
        feedbackLabel: 'purchased',
        purchasePrice: outcome.purchasePrice,
        expectedResalePrice: outcome.expectedResalePrice,
        feedbackNote: outcome.feedbackNote,
      });
      const stateLabel = [result.status, result.decision].filter(Boolean).join(' · ') || 'purchased';
      setPurchaseOutcomeOpportunityId(null);
      setFeedbackByOpportunity((current) => ({
        ...current,
        [opportunity.id]: {
          kind: 'success',
          message: `已回写成交：${stateLabel}，ROI 证据已进入结果漏斗。`,
        },
      }));
    } catch (mutationError) {
      const message = mutationError instanceof Error ? mutationError.message : '成交记录失败';
      setFeedbackByOpportunity((current) => ({
        ...current,
        [opportunity.id]: {
          kind: 'error',
          message,
        },
      }));
    }
  }

  async function handleApplyCalibration() {
    if (!categoryCode) {
      setCalibrationState({
        kind: 'error',
        message: '缺少 category_code，暂时无法应用校准。',
      });
      return;
    }
    if (!selectedRecommendationCount) {
      setCalibrationState({
        kind: 'error',
        message: '至少选择 1 条校准建议后再应用。',
      });
      return;
    }

    setCalibrationState({
      kind: 'idle',
      message: '正在应用校准建议并重算基线/机会...',
    });
    try {
      const result = await applyCalibration({
        categoryCode,
        windowDays: calibration?.windowDays ?? 30,
        recommendationIds: selectedRecommendationIds,
      });
      const baselineCount = Number((result.baselineRebuild as { baselineCount?: number } | null | undefined)?.baselineCount ?? 0);
      const opportunityCount = Number((result.opportunityRefresh as { opportunityCount?: number } | null | undefined)?.opportunityCount ?? 0);
      setCalibrationState({
        kind: 'success',
        message: `已应用 ${formatNumber(result.appliedRecommendationCount)} 条建议，重建 ${formatNumber(baselineCount)} 条基线，刷新 ${formatNumber(opportunityCount)} 条机会。`,
      });
    } catch (mutationError) {
      const message = mutationError instanceof Error ? mutationError.message : '校准应用失败';
      setCalibrationState({
        kind: 'error',
        message,
      });
    }
  }

  function toggleRecommendationSelection(recommendationId: string) {
    setSelectedRecommendationIds((current) =>
      current.includes(recommendationId)
        ? current.filter((id) => id !== recommendationId)
        : [...current, recommendationId],
    );
  }

  function recordListingOpen(opportunity: BuyOpportunity) {
    void submitFeedback({
      opportunityId: opportunity.id,
      feedbackType: 'engagement',
      feedbackLabel: 'listing_opened',
    }).catch(() => undefined);
  }

  return (
    <TerminalScreen className="buy-opportunity-os">
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack buy-workbench-page">
            <PageHero
              eyebrow="AI Buy-Side Copilot"
              title="人机协同买入工作台"
              description="AI 副驾驶常驻读取机会、价格、反馈和 ROI 上下文，帮助操作员把 OPEN 机会尽快转成联系、跳过、成交与证据。"
              meta={
                <>
                  <span className="soft-pill">{formatNumber(summary?.opportunityCount)} 个机会</span>
                  <span className="soft-pill is-accent">{formatPercent((summary?.alertHitRate ?? 0) * 100, 1)} 命中率</span>
                  <span className="soft-pill">{formatNumber(summary?.feedbackCount)} 条反馈</span>
                </>
              }
            >
              <Link className="nav-pill" to={dashboardTarget}>
                回到看板首页
              </Link>
              <button
                className="nav-pill"
                type="button"
                onClick={() => {
                  navigate(runtimeTarget);
                }}
              >
                打开运行控制
              </button>
              {isRefreshing ? <span className="soft-pill">正在刷新</span> : null}
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !workbench ? (
              <section className="panel">
                <p className="eyebrow">Workbench</p>
                <h2>正在同步买入机会与反馈校准...</h2>
                <p className="panel-subtitle">首轮会拉取机会池、价格基线、监控目标和反馈建议，完成后可以直接留在 React 主路径里做动作。</p>
              </section>
            ) : null}

            <div className="buy-ai-command-layout">
              <div className="buy-ai-primary">
                <section className="panel buy-summary-panel">
                  <div className="buy-summary-grid">
                    <article className="buy-summary-card">
                      <p className="eyebrow">当前机会</p>
                      <strong>{formatNumber(summary?.opportunityCount)}</strong>
                      <p className="panel-subtitle">基线 {formatNumber(summary?.baselineCount)} · 监控目标 {formatNumber(summary?.watchTargetCount)}</p>
                    </article>
                    <article className="buy-summary-card">
                      <p className="eyebrow">反馈闭环</p>
                      <strong>{formatNumber(summary?.feedbackCount)}</strong>
                      <p className="panel-subtitle">采纳 {formatNumber(summary?.acceptCount)} · 拒绝 {formatNumber(summary?.rejectCount)}</p>
                    </article>
                    <article className="buy-summary-card">
                      <p className="eyebrow">校准建议</p>
                      <strong>{formatNumber(summary?.calibrationRecommendationCount)}</strong>
                      <p className="panel-subtitle">{formatNumber(summary?.alertHitCount)} / {formatNumber(summary?.alertCount)} 条提醒命中</p>
                    </article>
                    <article className="buy-summary-card">
                      <p className="eyebrow">结果证据</p>
                      <strong>{formatNumber(outcomeFunnel?.purchasedOpportunityCount)}</strong>
                      <p className="panel-subtitle">
                        打开 {formatNumber(outcomeFunnel?.openedOpportunityCount)} · 联系 {formatNumber(outcomeFunnel?.contactedOpportunityCount)} · ROI 证据 {formatNumber(outcomeFunnel?.roiEvidenceCount)}
                      </p>
                      <p className="panel-subtitle">
                        提醒→打开 {formatPercent((outcomeFunnel?.alertToOpenRate ?? 0) * 100, 1)} · 打开→联系 {formatPercent((outcomeFunnel?.openToContactRate ?? 0) * 100, 1)}
                      </p>
                    </article>
                  </div>
                </section>

                {dailyOpportunityPack ? (
                  <DailyOpportunityPack
                    feedbackByOpportunity={feedbackByOpportunity}
                    feedbackPendingId={feedbackPendingId}
                    pack={dailyOpportunityPack}
                    purchaseOutcomeOpportunityId={purchaseOutcomeOpportunityId}
                    workspaceQuery={workspaceQuery}
                    onFeedback={(opportunity, feedbackLabel) => {
                      void handleFeedback(opportunity, feedbackLabel);
                    }}
                    onListingOpen={recordListingOpen}
                    onPurchaseCancel={() => {
                      setPurchaseOutcomeOpportunityId(null);
                    }}
                    onPurchaseIntent={(opportunity) => {
                      setPurchaseOutcomeOpportunityId(opportunity.id);
                    }}
                    onPurchasedOutcome={handlePurchasedOutcome}
                  />
                ) : null}

                {dataValue ? <DataValueCockpit dataValue={dataValue} /> : null}

                <section className="buy-layout">
                  <div className="buy-main">
                    <article className="panel">
                  <div className="panel-header buy-panel-header">
                    <div>
                      <p className="eyebrow">Opportunity Pool</p>
                      <h2>机会池</h2>
                      <p className="panel-subtitle">优先处理折扣足、风险低、基线匹配更细的商品，反馈动作直接回写，不再开新窗口。</p>
                    </div>
                    <span className="soft-pill">{opportunities.length} 条候选</span>
                  </div>

                  <div className="buy-opportunity-list">
                    {opportunities.length ? opportunities.map((opportunity) => {
                      const feedbackState = feedbackByOpportunity[opportunity.id];
                      const stateLabel = [opportunity.status, opportunity.decision].filter(Boolean).join(' · ') || '-';
                      const isPending = feedbackPendingId === opportunity.id;
                      const detailTarget = buildWorkspaceLocation(`/buy/opportunities/${opportunity.id}`, workspaceQuery);
                      return (
                        <article className="buy-opportunity-card" key={opportunity.id}>
                          <div className="buy-opportunity-head">
                            <div>
                              <h3>{opportunity.title ?? opportunity.itemId ?? opportunity.itemIdRef ?? '未命名商品'}</h3>
                              <p className="panel-subtitle">
                                {(opportunity.region ?? '-') + ' · ' + (opportunity.baselineMatchLevel ?? '-')}
                              </p>
                            </div>
                            <div className="buy-score-pair">
                              <span className="soft-pill is-accent">机会 {formatNumber(opportunity.opportunityScore)}</span>
                              <span className="soft-pill">风险 {formatNumber(opportunity.riskScore)}</span>
                            </div>
                          </div>

                          <div className="buy-opportunity-metrics">
                            <div>
                              <small>当前价</small>
                              <strong>{formatCurrency(opportunity.currentPrice)}</strong>
                            </div>
                            <div>
                              <small>合理价</small>
                              <strong>{formatCurrency(opportunity.fairPrice)}</strong>
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

                          <div className="buy-opportunity-notes">
                            <p>{opportunity.explanation?.readinessSummary ?? '等待更多价格与反馈信息。'}</p>
                            <p>review {opportunity.explanation?.reviewGateSummary ?? '-'} · spec {opportunity.explanation?.specGateSummary ?? '-'}</p>
                            {opportunity.explanation?.missingRequiredFields?.length ? (
                              <p>缺字段：{opportunity.explanation.missingRequiredFields.join('、')}</p>
                            ) : null}
                          </div>

                          <div className="buy-opportunity-footer">
                            <div className="buy-state-block">
                              <strong>{stateLabel}</strong>
                              <small>spec {opportunity.specContract?.status ?? '-'} · conf {formatNumber(opportunity.specConfidence)}</small>
                            </div>
                            <div className="buy-feedback-actions">
                              <Link className="nav-pill" to={detailTarget}>
                                查看详情
                              </Link>
                              <button
                                className="quick-pill"
                                disabled={isPending}
                                type="button"
                                onClick={() => {
                                  setPurchaseOutcomeOpportunityId(opportunity.id);
                                }}
                              >
                                已成交
                              </button>
                              <button
                                className="quick-pill is-active"
                                disabled={isPending}
                                type="button"
                                onClick={() => {
                                  void handleFeedback(opportunity, 'contacted');
                                }}
                              >
                                感兴趣
                              </button>
                              <button
                                className="quick-pill"
                                disabled={isPending}
                                type="button"
                                onClick={() => {
                                  void handleFeedback(opportunity, 'not_worth_it');
                                }}
                              >
                                不感兴趣
                              </button>
                              {opportunity.listingUrl ? (
                                <a
                                  className="nav-pill"
                                  href={opportunity.listingUrl}
                                  rel="noreferrer"
                                  target="_blank"
                                  onClick={() => {
                                    recordListingOpen(opportunity);
                                  }}
                                >
                                  打开原始商品
                                </a>
                              ) : null}
                            </div>
                          </div>

                          <p className={`buy-feedback-result ${feedbackState?.kind === 'error' ? 'is-error' : feedbackState?.kind === 'success' ? 'is-success' : ''}`}>
                            {feedbackState?.message ?? '可直接在这里回写反馈并联动候选池。'}
                          </p>
                          {purchaseOutcomeOpportunityId === opportunity.id ? (
                            <PurchaseOutcomeForm
                              buyCeiling={opportunity.buyCeiling}
                              currentPrice={opportunity.currentPrice}
                              fairPrice={opportunity.fairPrice}
                              isPending={isPending}
                              onCancel={() => {
                                setPurchaseOutcomeOpportunityId(null);
                              }}
                              onSubmit={(outcome) => handlePurchasedOutcome(opportunity, outcome)}
                            />
                          ) : null}
                        </article>
                      );
                    }) : (
                      <div className="buy-empty-state">
                        暂无机会。先运行 `build-buy-baselines` 和 `refresh-buy-opportunities`。
                      </div>
                    )}
                  </div>
                </article>
              </div>

              <aside className="buy-side">
                <article className="panel buy-side-panel">
                  <p className="eyebrow">Feedback Loop</p>
                  <h3>反馈校准</h3>
                  <div className="mini-card">
                    <strong>采纳 {formatNumber(summary?.acceptCount)} · 拒绝 {formatNumber(summary?.rejectCount)}</strong>
                    <small>
                      反馈覆盖 {formatPercent((((feedback?.feedbackCount ?? 0) / Math.max(feedback?.opportunityCount ?? 1, 1)) * 100), 1)}
                    </small>
                  </div>
                  {Object.entries(feedback?.tierStats ?? {}).map(([tier, stats]) => (
                    <div className="mini-card" key={tier}>
                      <strong>{tier}</strong>
                      <small>机会 {formatNumber(stats.opportunityCount)} · 反馈 {formatNumber(stats.feedbackCount)}</small>
                      <small>采纳率 {formatPercent((stats.acceptanceRate ?? 0) * 100, 1)}</small>
                    </div>
                  ))}
                  {Object.entries(feedback?.rejectReasonCounts ?? {}).map(([reason, count]) => (
                    <div className="mini-card" key={reason}>
                      <strong>{reason}</strong>
                      <small>{formatNumber(count)} 次拒绝反馈</small>
                    </div>
                  ))}
                </article>

                <article className="panel buy-side-panel">
                  <p className="eyebrow">Calibration Plan</p>
                  <h3>校准动作建议</h3>
                  {effectiveCalibrationConfig ? (
                    <div className="buy-calibration-grid">
                      <div className="mini-card">
                        <strong>当前 guidance 门槛</strong>
                        <small>
                          卖家样本 {formatNumber(guidanceThresholds?.seller_sample_count)} · 不同卖家 {formatNumber(guidanceThresholds?.unique_seller_count)}
                        </small>
                        <small>
                          exact spec {formatPercent((guidanceThresholds?.exact_spec_ratio ?? 0) * 100, 1)} · reliability {formatNumber(guidanceThresholds?.reliability_score)}
                        </small>
                        <small>freshness {formatNumber(guidanceThresholds?.freshness_days)} 天</small>
                      </div>
                      <div className="mini-card">
                        <strong>当前 reference 门槛</strong>
                        <small>
                          卖家样本 {formatNumber(referenceThresholds?.seller_sample_count)} · 不同卖家 {formatNumber(referenceThresholds?.unique_seller_count)}
                        </small>
                        <small>
                          exact spec {formatPercent((referenceThresholds?.exact_spec_ratio ?? 0) * 100, 1)} · reliability {formatNumber(referenceThresholds?.reliability_score)}
                        </small>
                        <small>freshness {formatNumber(referenceThresholds?.freshness_days)} 天</small>
                      </div>
                      <div className="mini-card">
                        <strong>当前机会分旋钮</strong>
                        <small>
                          buy ceiling 收紧 {formatDecimal(scoringConfig?.buyCeilingTightenPct, 1)}% · risk penalty {formatDecimal(scoringConfig?.riskPenaltyWeight, 2)}
                        </small>
                        <small>
                          折扣权重 {formatDecimal(scoringConfig?.discountRateWeight, 2)} · ceiling gap 权重 {formatDecimal(scoringConfig?.ceilingGapWeight, 2)}
                        </small>
                        <small>
                          conf 权重 {formatDecimal(scoringConfig?.confidenceWeight, 2)} · 默认 conf {formatDecimal(scoringConfig?.defaultConfidence, 2)}
                        </small>
                      </div>
                      <div className="mini-card">
                        <strong>最近一次应用</strong>
                        <small>
                          {effectiveCalibrationConfig.lastAppliedAt ? `${formatRelative(effectiveCalibrationConfig.lastAppliedAt)} · ${effectiveCalibrationConfig.lastAppliedBy ?? 'system'}` : '尚未自动应用过校准'}
                        </small>
                        <small>
                          source {effectiveCalibrationConfig.lastApplySource ?? '-'} · 本次窗口 {formatNumber(effectiveCalibrationConfig.lastCalibrationWindowDays ?? calibration?.windowDays ?? 30)} 天
                        </small>
                        <small>最近落地 {formatNumber(lastAppliedRecommendationCount)} 条建议</small>
                      </div>
                    </div>
                  ) : null}
                  <div className="buy-feedback-actions">
                    <button
                      className="quick-pill is-active"
                      disabled={calibrationPending || !selectedRecommendationCount}
                      type="button"
                      onClick={() => {
                        void handleApplyCalibration();
                      }}
                    >
                      {calibrationPending ? '应用中...' : '应用所选校准'}
                    </button>
                    {hasSelectableRecommendations ? (
                      <>
                        <button
                          className="quick-pill"
                          disabled={calibrationPending || selectedRecommendationCount === selectableRecommendationIds.length}
                          type="button"
                          onClick={() => {
                            setSelectedRecommendationIds(selectableRecommendationIds);
                          }}
                        >
                          全选
                        </button>
                        <button
                          className="quick-pill"
                          disabled={calibrationPending || selectedRecommendationCount === 0}
                          type="button"
                          onClick={() => {
                            setSelectedRecommendationIds([]);
                          }}
                        >
                          清空
                        </button>
                      </>
                    ) : null}
                  </div>
                  {recommendations?.totalRecommendationCount ? (
                    <div className="mini-card">
                      <strong>{formatNumber(recommendations.totalRecommendationCount)} 条建议</strong>
                      <small>
                        自动可执行 {formatNumber(recommendations.autoApplicableRecommendationCount)} 条 · {formatNumber(calibration?.windowDays ?? 30)} 天窗口
                      </small>
                      <small>
                        已选择 {formatNumber(selectedRecommendationCount)} / {formatNumber(selectableRecommendationIds.length)} 条可应用建议
                      </small>
                    </div>
                  ) : null}
                  {calibrationRecommendations.slice(0, 6).map((recommendation) => {
                    const recommendationId = recommendation.id ?? null;
                    const isSelectable = Boolean(recommendationId);
                    const isSelected = recommendationId ? selectedRecommendationIdSet.has(recommendationId) : false;
                    return (
                      <label
                        className={`mini-card buy-recommendation-card ${isSelectable && isSelected ? 'is-selected' : ''}`}
                        key={`${recommendation.id ?? recommendation.title}:${recommendation.recommendedAction}`}
                      >
                        <div className="buy-recommendation-head">
                          <strong>{recommendation.title}</strong>
                          {isSelectable ? (
                            <input
                              aria-label={`选择建议 ${recommendation.title}`}
                              checked={isSelected}
                              type="checkbox"
                              onChange={() => {
                                if (recommendationId) {
                                  toggleRecommendationSelection(recommendationId);
                                }
                              }}
                            />
                          ) : (
                            <span className="soft-pill">只读</span>
                          )}
                        </div>
                        <small>{recommendation.summary}</small>
                        <small>{recommendation.recommendedAction}</small>
                      </label>
                    );
                  })}
                  {calibrationState.message ? (
                    <p className={`buy-feedback-result ${calibrationState.kind === 'error' ? 'is-error' : calibrationState.kind === 'success' ? 'is-success' : ''}`}>
                      {calibrationState.message}
                    </p>
                  ) : null}
                  {!recommendations?.totalRecommendationCount ? <p className="panel-subtitle">当前窗口暂无明确校准动作，继续积累反馈样本。</p> : null}
                  {recommendations?.totalRecommendationCount && !selectedRecommendationCount ? (
                    <p className="panel-subtitle">至少保留 1 条建议为选中状态，才能真正应用到当前类目的 runtime profile。</p>
                  ) : null}
                </article>

                <article className="panel buy-side-panel">
                  <p className="eyebrow">Watch Targets</p>
                  <h3>监控目标</h3>
                  {watchTargets.length ? watchTargets.map((target) => (
                    <div className="mini-card" key={target.id}>
                      <strong>{target.targetName}</strong>
                      <small>{target.profileKey ?? '-'} · {target.status ?? '-'} · cooldown {formatNumber(target.notifyCooldownMinutes)}m</small>
                    </div>
                  )) : <p className="panel-subtitle">暂无监控目标。刷新机会池时会自动创建默认目标。</p>}
                </article>

                <article className="panel buy-side-panel">
                  <p className="eyebrow">Price Baselines</p>
                  <h3>最新价格基线</h3>
                  {baselines.length ? baselines.slice(0, 12).map((baseline) => (
                    <div className="mini-card" key={baseline.id}>
                      <strong>{baseline.baselineKey}</strong>
                      <small>fair {formatCurrency(baseline.fairPrice)} · buy {formatCurrency(baseline.buyCeiling)} · n={formatNumber(baseline.sampleSize)}</small>
                      <small>{baseline.explanation?.readinessSummary ?? '-'}</small>
                      <small>{baseline.explanation?.confidenceSummary ?? '-'}</small>
                    </div>
                  )) : <p className="panel-subtitle">暂无 baseline。先运行 `build-buy-baselines --view all`。</p>}
                </article>
              </aside>
                </section>
              </div>

              <BuyCopilotPanel
                dailyOpportunityPack={dailyOpportunityPack}
                dataValue={dataValue}
                error={error}
                isRefreshing={isRefreshing}
                outcomeFunnel={outcomeFunnel}
                summary={summary}
                workspaceQuery={workspaceQuery}
              />
            </div>
          </div>
        </div>
      </main>
    </TerminalScreen>
  );
}

type DailyOpportunityPackModel = NonNullable<BuyWorkbench['dailyOpportunityPack']>;
type DailyOpportunityTask = DailyOpportunityPackModel['groups'][number]['tasks'][number];
type WorkspaceQuery = ReturnType<typeof readInitialQuery>;

function BuyCopilotPanel(props: {
  dailyOpportunityPack?: DailyOpportunityPackModel | null;
  dataValue?: BuyDataValueReport | null;
  error?: string | null;
  isRefreshing: boolean;
  outcomeFunnel?: BuyWorkbench['outcomeFunnel'];
  summary?: BuyWorkbench['summary'];
  workspaceQuery: WorkspaceQuery;
}) {
  const tasks = useMemo(
    () => props.dailyOpportunityPack?.groups.flatMap((group) => group.tasks) ?? [],
    [props.dailyOpportunityPack],
  );
  const firstTask = tasks[0] ?? null;
  const packSummary = props.dailyOpportunityPack?.summary;
  const dataSummary = props.dataValue?.summary;
  const feedbackGap = Math.max(
    0,
    Number(packSummary?.packOpportunityCount ?? 0) - Number(packSummary?.feedbackCount ?? 0),
  );
  const firstTaskTarget = firstTask
    ? buildWorkspaceLocation(`/buy/opportunities/${firstTask.opportunity.id}`, props.workspaceQuery)
    : null;
  const copilotStatus = props.error
    ? '上下文同步异常'
    : props.isRefreshing
      ? '正在同步最新上下文'
      : '已读取当前工作上下文';
  const primaryInstruction = feedbackGap > 0
    ? `先处理今日任务包前 ${formatNumber(Math.min(3, feedbackGap))} 条，高分低风险机会必须给出联系或跳过。`
    : '今日任务包已无明显反馈缺口，检查成交与 ROI 证据是否完整。';

  function scrollTo(selector: string) {
    document.querySelector(selector)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  return (
    <aside className="buy-ai-copilot" aria-label="AI 副驾驶">
      <motion.div
        animate={{ opacity: 1, x: 0 }}
        className="buy-ai-copilot-shell"
        initial={{ opacity: 0, x: 18 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="buy-ai-copilot-head">
          <div className="buy-ai-orb" aria-hidden="true">
            <span />
            <span />
            <i />
          </div>
          <div>
            <p className="eyebrow">Goofish AI Copilot</p>
            <h3>副驾驶在线</h3>
            <small>{copilotStatus}</small>
          </div>
        </div>

        <div className="buy-ai-live-context">
          <span className={props.error ? 'is-error' : props.isRefreshing ? 'is-syncing' : 'is-ready'} />
          <strong>{props.error ? '需要人工确认 API 状态' : '正在跟随当前页面数据'}</strong>
        </div>

        <div className="buy-ai-bubble">
          <Sparkles size={16} aria-hidden="true" />
          <p>{primaryInstruction}</p>
        </div>

        <div className="buy-ai-context-grid">
          <div>
            <span>今日入队</span>
            <strong>{formatNumber(packSummary?.packOpportunityCount)}</strong>
          </div>
          <div>
            <span>OPEN backlog</span>
            <strong>{formatNumber(packSummary?.openBacklogCount)}</strong>
          </div>
          <div>
            <span>数据价值</span>
            <strong>{formatNumber(dataSummary?.dataValueScore)}</strong>
          </div>
          <div>
            <span>ROI 证据</span>
            <strong>{formatNumber(props.outcomeFunnel?.roiEvidenceCount)}</strong>
          </div>
        </div>

        <div className="buy-ai-plan">
          <div className="buy-ai-section-label">
            <Radar size={14} aria-hidden="true" />
            下一步建议
          </div>
          <ol>
            <li>
              <strong>先消化，不扩采</strong>
              <span>把 {formatNumber(packSummary?.openBacklogCount)} 条 OPEN 机会拆成今日可完成动作。</span>
            </li>
            <li>
              <strong>每条只做一个判断</strong>
              <span>联系、跳过、成交三选一，减少“看过但无结果”的空转。</span>
            </li>
            <li>
              <strong>成交必须带 ROI</strong>
              <span>记录买入价和预期转售价，才能让后续机会分校准变聪明。</span>
            </li>
          </ol>
        </div>

        <div className="buy-ai-actions">
          {firstTaskTarget ? (
            <Link className="buy-ai-command is-primary" to={firstTaskTarget}>
              打开 #1 机会
              <ArrowUpRight size={14} aria-hidden="true" />
            </Link>
          ) : null}
          <button
            className="buy-ai-command"
            type="button"
            onClick={() => {
              scrollTo('.buy-daily-panel');
            }}
          >
            回到今日任务
          </button>
          <button
            className="buy-ai-command"
            type="button"
            onClick={() => {
              scrollTo('.buy-value-panel');
            }}
          >
            查看数据利用率
          </button>
        </div>

        <div className="buy-ai-memory">
          <div className="buy-ai-section-label">
            <ClipboardCheck size={14} aria-hidden="true" />
            Copilot 记忆
          </div>
          <p>
            当前工作模式：{packSummary?.operatingMode ?? 'opportunity_digest_first'}。系统会优先追踪反馈、联系、成交和 ROI，
            不再让采集增长掩盖业务价值。
          </p>
        </div>
      </motion.div>
    </aside>
  );
}

function DailyOpportunityPack(props: {
  feedbackByOpportunity: Record<string, FeedbackState>;
  feedbackPendingId: string | null;
  pack: DailyOpportunityPackModel;
  purchaseOutcomeOpportunityId: string | null;
  workspaceQuery: WorkspaceQuery;
  onFeedback: (opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) => void;
  onListingOpen: (opportunity: BuyOpportunity) => void;
  onPurchaseCancel: () => void;
  onPurchaseIntent: (opportunity: BuyOpportunity) => void;
  onPurchasedOutcome: (
    opportunity: BuyOpportunity,
    outcome: Pick<BuyFeedbackRequest, 'purchasePrice' | 'expectedResalePrice' | 'feedbackNote'>,
  ) => Promise<void>;
}) {
  const { pack } = props;
  const summary = pack.summary;
  const tasks = useMemo(() => pack.groups.flatMap((group) => group.tasks), [pack.groups]);
  const taskCount = tasks.length;
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string | null>(tasks[0]?.opportunity.id ?? null);
  const selectedTask = tasks.find((task) => task.opportunity.id === selectedOpportunityId) ?? tasks[0] ?? null;
  const selectedGroup = selectedTask
    ? pack.groups.find((group) => group.key === selectedTask.groupKey)
    : null;

  useEffect(() => {
    if (!tasks.length) {
      setSelectedOpportunityId(null);
      return;
    }
    if (!selectedOpportunityId || !tasks.some((task) => task.opportunity.id === selectedOpportunityId)) {
      setSelectedOpportunityId(tasks[0]?.opportunity.id ?? null);
    }
  }, [selectedOpportunityId, tasks]);

  return (
    <motion.section
      animate={{ opacity: 1, y: 0 }}
      className="panel buy-daily-panel relative overflow-hidden"
      initial={{ opacity: 0, y: 18 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="panel-header buy-panel-header">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge>
              <Radar size={14} aria-hidden="true" />
              Daily Opportunity Pack
            </Badge>
            <Badge variant="success">
              <Sparkles size={14} aria-hidden="true" />
              数据兑现优先
            </Badge>
          </div>
          <h2 className="text-3xl font-black tracking-[-0.04em] text-slate-50">今日机会任务包</h2>
          <p className="panel-subtitle">
            {summary.northStar ?? '把 OPEN 机会消化成反馈、联系、成交和 ROI 证据'}。
          </p>
        </div>
        <div className="buy-daily-target">
          <Badge variant="success">今日目标 {formatNumber(summary.targetProcessingCount)}</Badge>
          <strong>{formatNumber(summary.packOpportunityCount)} 条入队</strong>
          <small>OPEN backlog {formatNumber(summary.openBacklogCount)} · 未入队 {formatNumber(summary.ungroupedOpenCount)}</small>
        </div>
      </div>

      <div className="buy-signal-strip">
        <motion.article whileHover={{ y: -3 }} transition={{ duration: 0.18 }}>
          <ClipboardCheck size={18} aria-hidden="true" />
          <span>反馈覆盖</span>
          <strong>{formatPercent((summary.feedbackCoverageRate ?? 0) * 100, 1)}</strong>
          <small>{formatNumber(summary.feedbackCount)} 条反馈</small>
        </motion.article>
        <motion.article whileHover={{ y: -3 }} transition={{ duration: 0.18 }}>
          <MessageCircle size={18} aria-hidden="true" />
          <span>已联系</span>
          <strong>{formatNumber(summary.contactedOpportunityCount)}</strong>
          <small>今天优先补足联系证据</small>
        </motion.article>
        <motion.article whileHover={{ y: -3 }} transition={{ duration: 0.18 }}>
          <CircleDollarSign size={18} aria-hidden="true" />
          <span>成交证明</span>
          <strong>{formatNumber(summary.purchasedOpportunityCount)}</strong>
          <small>ROI {formatNumber(summary.roiEvidenceCount)}</small>
        </motion.article>
      </div>

      {taskCount ? (
        <div className="buy-signal-layout">
          <div className="buy-signal-queue">
            <div className="buy-signal-queue-head">
              <div>
                <strong>机会队列</strong>
                <span>{formatNumber(taskCount)} 个待处理信号</span>
              </div>
              <Badge variant="success">Queue first</Badge>
            </div>
            <div className="buy-daily-groups">
              {pack.groups.map((group, groupIndex) => {
                const GroupIcon = group.key === 'needs_review'
                  ? ShieldAlert
                  : group.key === 'negotiate'
                    ? CircleDollarSign
                    : Target;
                return (
                  <motion.article
                    animate={{ opacity: 1, y: 0 }}
                    className="buy-daily-group"
                    initial={{ opacity: 0, y: 16 }}
                    key={group.key}
                    transition={{ delay: 0.08 * groupIndex, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <div className="buy-daily-group-head">
                      <div>
                        <h3 className="flex items-center gap-2">
                          <GroupIcon size={18} aria-hidden="true" />
                          {group.label}
                        </h3>
                        <p>{group.recommendedAction}</p>
                      </div>
                      <Badge variant={group.key === 'needs_review' ? 'danger' : group.key === 'negotiate' ? 'action' : 'success'}>
                        {formatNumber(group.count)} 条
                      </Badge>
                    </div>
                    <div className="buy-daily-task-list">
                      {group.tasks.map((task, taskIndex) => (
                        <DailyOpportunityTaskCard
                          feedbackByOpportunity={props.feedbackByOpportunity}
                          isSelected={selectedTask?.opportunity.id === task.opportunity.id}
                          key={`${task.groupKey}:${task.opportunity.id}`}
                          task={task}
                          visualIndex={taskIndex}
                          onSelect={() => {
                            setSelectedOpportunityId(task.opportunity.id);
                          }}
                        />
                      ))}
                    </div>
                  </motion.article>
                );
              })}
            </div>
          </div>
          <DailyOpportunityInspector
            feedbackByOpportunity={props.feedbackByOpportunity}
            feedbackPendingId={props.feedbackPendingId}
            groupLabel={selectedGroup?.label ?? selectedTask?.groupLabel ?? '当前机会'}
            purchaseOutcomeOpportunityId={props.purchaseOutcomeOpportunityId}
            task={selectedTask}
            workspaceQuery={props.workspaceQuery}
            onFeedback={props.onFeedback}
            onListingOpen={props.onListingOpen}
            onPurchaseCancel={props.onPurchaseCancel}
            onPurchaseIntent={props.onPurchaseIntent}
            onPurchasedOutcome={props.onPurchasedOutcome}
          />
        </div>
      ) : (
        <div className="buy-empty-state">
          当前没有可入队 OPEN 机会。先处理已有反馈，或按需刷新 baseline / opportunity，不要无目的扩采集。
        </div>
      )}

      {pack.marketIntel.length ? (
        <div className="buy-daily-market">
          <div>
            <strong className="flex items-center gap-2">
              <CircleDollarSign size={18} aria-hidden="true" />
              今日议价锚点
            </strong>
            <small>从可靠价格基线里抽取，帮助联系卖家时快速判断目标买入线。</small>
          </div>
          {pack.marketIntel.slice(0, 4).map((entry) => (
            <motion.article className="mini-card" key={entry.baselineKey ?? `${entry.fairPrice}:${entry.buyCeiling}`} whileHover={{ y: -2 }}>
              <strong>{entry.baselineKey ?? '未命名基线'}</strong>
              <small>
                fair {formatCurrency(entry.fairPrice)} · buy {formatCurrency(entry.buyCeiling)} · n={formatNumber(entry.sampleSize)}
              </small>
              <small>confidence {formatNumber(entry.confidence)} · {entry.reason}</small>
            </motion.article>
          ))}
        </div>
      ) : null}
    </motion.section>
  );
}

function DailyOpportunityTaskCard(props: {
  feedbackByOpportunity: Record<string, FeedbackState>;
  isSelected: boolean;
  task: DailyOpportunityTask;
  onSelect: () => void;
  visualIndex: number;
}) {
  const { task } = props;
  const opportunity = task.opportunity;
  const feedbackState = props.feedbackByOpportunity[opportunity.id];
  return (
    <motion.article
      animate={{ opacity: 1, y: 0 }}
      className={`buy-daily-task-card ${props.isSelected ? 'is-selected' : ''}`}
      initial={{ opacity: 0, y: 12 }}
      layout
      transition={{ delay: 0.04 * props.visualIndex, duration: 0.3 }}
      whileHover={{ y: -3 }}
      onClick={props.onSelect}
    >
      <div className="buy-daily-task-top">
        <Badge variant="dark">#{formatNumber(task.rank)}</Badge>
        <Badge variant="action">机会 {formatNumber(opportunity.opportunityScore)}</Badge>
        <Badge variant={(opportunity.riskScore ?? 0) > 35 ? 'danger' : 'default'}>
          风险 {formatNumber(opportunity.riskScore)}
        </Badge>
        <button
          className="buy-task-focus"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            props.onSelect();
          }}
        >
          聚焦
        </button>
      </div>
      <h4>{opportunity.title ?? opportunity.itemId ?? opportunity.itemIdRef ?? '未命名商品'}</h4>
      <p>{task.reason}</p>
      <div className="buy-daily-task-metrics">
        <span>现价 {formatCurrency(opportunity.currentPrice)}</span>
        <span>买入线 {formatCurrency(opportunity.buyCeiling)}</span>
        <span>{task.slaLabel}</span>
      </div>
      {task.valueSignals?.length ? (
        <div className="buy-daily-chip-row">
          {task.valueSignals.slice(0, 5).map((signal) => (
            <Badge key={signal}>{signal}</Badge>
          ))}
        </div>
      ) : null}
      {task.riskFlags?.length ? (
        <div className="buy-daily-chip-row">
          {task.riskFlags.slice(0, 4).map((flag) => (
            <Badge key={flag} variant="danger">{flag}</Badge>
          ))}
        </div>
      ) : null}
      <AnimatePresence initial={false}>
        {feedbackState?.message ? (
          <motion.p
            animate={{ opacity: 1, y: 0 }}
            className={`buy-feedback-result ${feedbackState.kind === 'error' ? 'is-error' : feedbackState.kind === 'success' ? 'is-success' : ''}`}
            exit={{ opacity: 0, y: -6 }}
            initial={{ opacity: 0, y: 6 }}
          >
            {feedbackState.message}
          </motion.p>
        ) : null}
      </AnimatePresence>
    </motion.article>
  );
}

function DailyOpportunityInspector(props: {
  feedbackByOpportunity: Record<string, FeedbackState>;
  feedbackPendingId: string | null;
  groupLabel: string;
  purchaseOutcomeOpportunityId: string | null;
  task: DailyOpportunityTask | null;
  workspaceQuery: WorkspaceQuery;
  onFeedback: (opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) => void;
  onListingOpen: (opportunity: BuyOpportunity) => void;
  onPurchaseCancel: () => void;
  onPurchaseIntent: (opportunity: BuyOpportunity) => void;
  onPurchasedOutcome: (
    opportunity: BuyOpportunity,
    outcome: Pick<BuyFeedbackRequest, 'purchasePrice' | 'expectedResalePrice' | 'feedbackNote'>,
  ) => Promise<void>;
}) {
  if (!props.task) {
    return (
      <aside className="buy-signal-inspector">
        <p className="eyebrow">Inspector</p>
        <h3>等待机会入队</h3>
        <p className="panel-subtitle">当前没有可处理信号。先刷新机会池，或处理已有反馈。</p>
      </aside>
    );
  }

  const opportunity = props.task.opportunity;
  const feedbackState = props.feedbackByOpportunity[opportunity.id];
  const isPending = props.feedbackPendingId === opportunity.id;
  const detailTarget = buildWorkspaceLocation(`/buy/opportunities/${opportunity.id}`, props.workspaceQuery);
  const priceGap = Number(opportunity.fairPrice ?? 0) - Number(opportunity.currentPrice ?? 0);
  const buyGap = Number(opportunity.buyCeiling ?? 0) - Number(opportunity.currentPrice ?? 0);
  const missingFields = opportunity.explanation?.missingRequiredFields ?? [];

  return (
    <motion.aside
      animate={{ opacity: 1, x: 0 }}
      className="buy-signal-inspector"
      initial={{ opacity: 0, x: 18 }}
      transition={{ duration: 0.28 }}
    >
      <div className="buy-inspector-header">
        <div>
          <p className="eyebrow">Opportunity Inspector</p>
          <Badge variant="success">{props.groupLabel}</Badge>
        </div>
        <Badge variant="action">#{formatNumber(props.task.rank)}</Badge>
      </div>
      <h3 className="buy-inspector-title">
        {opportunity.title ?? opportunity.itemId ?? opportunity.itemIdRef ?? '未命名商品'}
      </h3>
      <p className="panel-subtitle">{props.task.reason}</p>

      <div className="buy-inspector-price-grid">
        <div>
          <span>当前价</span>
          <strong>{formatCurrency(opportunity.currentPrice)}</strong>
        </div>
        <div>
          <span>公平价差</span>
          <strong>{formatCurrency(priceGap)}</strong>
        </div>
        <div>
          <span>买入线差</span>
          <strong>{formatCurrency(buyGap)}</strong>
        </div>
        <div>
          <span>风险分</span>
          <strong>{formatNumber(opportunity.riskScore)}</strong>
        </div>
      </div>

      <div className="buy-inspector-action-rail" aria-label="当前机会动作">
        <Button
          disabled={isPending}
          type="button"
          variant="action"
          onClick={() => {
            props.onFeedback(opportunity, 'contacted');
          }}
        >
          <MessageCircle size={14} aria-hidden="true" />
          标记联系
        </Button>
        <Button
          disabled={isPending}
          type="button"
          variant="secondary"
          onClick={() => {
            props.onPurchaseIntent(opportunity);
          }}
        >
          <CircleDollarSign size={14} aria-hidden="true" />
          记录成交
        </Button>
        <Button
          disabled={isPending}
          type="button"
          variant="ghost"
          onClick={() => {
            props.onFeedback(opportunity, 'not_worth_it');
          }}
        >
          <SkipForward size={14} aria-hidden="true" />
          跳过
        </Button>
        <Button asChild variant="secondary">
          <Link to={detailTarget}>
            看详情
            <ArrowUpRight size={14} aria-hidden="true" />
          </Link>
        </Button>
        {opportunity.listingUrl ? (
          <Button asChild variant="secondary">
            <a
              href={opportunity.listingUrl}
              rel="noreferrer"
              target="_blank"
              onClick={() => {
                props.onListingOpen(opportunity);
              }}
            >
              原始商品
              <ArrowUpRight size={14} aria-hidden="true" />
            </a>
          </Button>
        ) : null}
      </div>

      <AnimatePresence initial={false}>
        {feedbackState?.message ? (
          <motion.p
            animate={{ opacity: 1, y: 0 }}
            className={`buy-feedback-result ${feedbackState.kind === 'error' ? 'is-error' : feedbackState.kind === 'success' ? 'is-success' : ''}`}
            exit={{ opacity: 0, y: -6 }}
            initial={{ opacity: 0, y: 6 }}
          >
            {feedbackState.message}
          </motion.p>
        ) : null}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {props.purchaseOutcomeOpportunityId === opportunity.id ? (
          <motion.div
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            initial={{ opacity: 0, height: 0 }}
          >
            <PurchaseOutcomeForm
              buyCeiling={opportunity.buyCeiling}
              currentPrice={opportunity.currentPrice}
              fairPrice={opportunity.fairPrice}
              isPending={isPending}
              onCancel={props.onPurchaseCancel}
              onSubmit={(outcome) => props.onPurchasedOutcome(opportunity, outcome)}
            />
          </motion.div>
        ) : null}
      </AnimatePresence>

      <div className="buy-inspector-evidence">
        <strong>证据状态</strong>
        <div className="buy-evidence-list">
          <span>readiness</span>
          <small>{opportunity.explanation?.readinessSummary ?? '等待更多价格与反馈信息'}</small>
          <span>review</span>
          <small>{opportunity.explanation?.reviewGateSummary ?? '-'}</small>
          <span>spec</span>
          <small>{opportunity.explanation?.specGateSummary ?? opportunity.specContract?.status ?? '-'}</small>
          <span>SLA</span>
          <small>{props.task.slaLabel}</small>
        </div>
        {missingFields.length ? (
          <div className="buy-daily-chip-row">
            {missingFields.slice(0, 4).map((field) => (
              <Badge key={field} variant="danger">缺 {field}</Badge>
            ))}
          </div>
        ) : null}
        {props.task.valueSignals?.length ? (
          <div className="buy-daily-chip-row">
            {props.task.valueSignals.slice(0, 6).map((signal) => (
              <Badge key={signal}>{signal}</Badge>
            ))}
          </div>
        ) : null}
      </div>
    </motion.aside>
  );
}

function DataValueCockpit(props: { dataValue: BuyDataValueReport }) {
  const { dataValue } = props;
  const summary = dataValue.summary;
  const diagnosis = dataValue.diagnosis;
  const primaryCategories = dataValue.categoryBreakdown.slice(0, 6);
  return (
    <section className="panel buy-value-panel">
      <div className="panel-header buy-panel-header">
        <div>
          <p className="eyebrow">Data Value Cockpit</p>
          <h2>数据资产利用率</h2>
          <p className="panel-subtitle">
            不再用采集量自我安慰，而是追踪数据有没有被消费成机会、行动、成交和 ROI 证据。
          </p>
        </div>
        <div className="buy-value-diagnosis">
          <span className={`soft-pill ${diagnosis.severity === 'critical' ? 'is-danger' : 'is-accent'}`}>
            {diagnosis.statusLabel ?? '待诊断'}
          </span>
          <strong>{formatNumber(summary.dataValueScore)} / 100</strong>
        </div>
      </div>

      <div className="buy-value-hero">
        <article>
          <span>有效商品</span>
          <strong>{formatNumber(summary.itemCount)}</strong>
          <small>活跃 {formatNumber(summary.activeItemCount)} · 快照 {formatNumber(summary.snapshotCount)}</small>
        </article>
        <article>
          <span>结构化覆盖</span>
          <strong>{formatPercent((summary.specCoverageRate ?? 0) * 100, 1)}</strong>
          <small>规格 {formatNumber(summary.specItemCount)} · 完整 {formatNumber(summary.completeSpecItemCount)}</small>
        </article>
        <article>
          <span>机会产出</span>
          <strong>{formatNumber(summary.openOpportunityCount)}</strong>
          <small>总机会 {formatNumber(summary.opportunityCount)} · guidance {formatNumber(summary.guidanceReadyOpportunityCount)}</small>
        </article>
        <article>
          <span>结果证明</span>
          <strong>{formatNumber(summary.purchasedOpportunityCount)}</strong>
          <small>反馈 {formatNumber(summary.feedbackCount)} · ROI {formatNumber(summary.roiEvidenceCount)}</small>
        </article>
      </div>

      <div className="buy-value-diagnosis-copy">
        <strong>{diagnosis.summary}</strong>
        <span>{diagnosis.nextBestAction}</span>
      </div>

      <div className="buy-value-stages" aria-label="数据价值漏斗">
        {dataValue.stages.map((stage) => {
          const rate = Math.max(0, Math.min((stage.conversionRate ?? 0) * 100, 100));
          return (
            <article className="buy-value-stage" key={stage.key}>
              <div>
                <strong>{stage.label}</strong>
                <span>{formatNumber(stage.count)} / {formatNumber(stage.denominator)}</span>
              </div>
              <div className="buy-value-track" aria-hidden="true">
                <span style={{ width: `${Math.max(rate, stage.count ? 4 : 0)}%` }} />
              </div>
              <small>转化 {formatPercent(rate, 1)} · 漏损 {formatNumber(stage.leakageCount)}</small>
            </article>
          );
        })}
      </div>

      <div className="buy-value-grid">
        <article className="mini-card buy-value-table-card">
          <strong>品类利用率</strong>
          <div className="buy-value-table">
            {primaryCategories.map((category) => (
              <div className="buy-value-row" key={category.categoryCode}>
                <span>{category.categoryCode}</span>
                <span>{formatNumber(category.itemCount)} 商品</span>
                <span>{formatNumber(category.openOpportunityCount)} OPEN</span>
                <span>{formatPercent((category.feedbackCoverageRate ?? 0) * 100, 1)} 反馈</span>
                <span>{formatNumber(category.utilizationScore)} 分</span>
              </div>
            ))}
          </div>
        </article>
        <article className="mini-card">
          <strong>下一步动作</strong>
          {dataValue.recommendations.slice(0, 4).map((recommendation) => (
            <div className="buy-value-recommendation" key={`${recommendation.priority}:${recommendation.title}`}>
              <span>{recommendation.priority ?? 'P?'}</span>
              <div>
                <strong>{recommendation.title}</strong>
                <small>{recommendation.reason}</small>
                <small>{recommendation.action}</small>
              </div>
            </div>
          ))}
        </article>
      </div>
    </section>
  );
}
