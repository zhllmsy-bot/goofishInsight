import { type CSSProperties, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  ArrowUpRight,
  Check,
  ExternalLink,
  Heart,
  SlidersHorizontal,
  X,
} from 'lucide-react';

import { AppFrame } from '../../../shared/components/AppFrame';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '../../../shared/components/ui/sheet';
import { formatCurrency, formatNumber, formatPercent, formatRelative } from '../../dashboard/lib/formatters';
import { readInitialQuery } from '../../dashboard/lib/urlState';
import { useBuyWorkbench } from '../hooks/useBuyWorkbench';
import type { BuyDataValueReport, BuyFeedbackRequest, BuyOpportunity, BuyWorkbench } from '../types/buy';
import { PurchaseOutcomeForm } from './PurchaseOutcomeForm';

import '../../dashboard/styles/dashboard.css';
import '../styles/buy-workbench.css';

type FeedbackState = {
  kind: 'idle' | 'success' | 'error';
  message: string;
};

type DailyOpportunityPackModel = NonNullable<BuyWorkbench['dailyOpportunityPack']>;

type DeskTask = {
  groupLabel?: string | null;
  rank?: number | null;
  reason?: string | null;
  recommendedAction?: string | null;
  slaLabel?: string | null;
  opportunity: BuyOpportunity;
  valueSignals?: string[];
  riskFlags?: string[];
};

type BaselineEvidence = {
  baselineKey?: string | null;
  buyCeiling?: number | null;
  confidence?: number | null;
  fairPrice?: number | null;
  sampleSize?: number | null;
};

const yuanFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat('en-CA', {
  day: '2-digit',
  month: '2-digit',
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
});

function formatDecimal(value: number | null | undefined, digits = 2): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  return numeric.toFixed(digits);
}

function numeric(value: number | null | undefined): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatYuan(value: number | null | undefined): string {
  const parsed = numeric(value);
  if (parsed === null) {
    return '¥-';
  }
  return `¥${yuanFormatter.format(parsed)}`;
}

function formatCompactRelative(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) {
    return '-';
  }
  const deltaMs = Date.now() - timestamp;
  const deltaSeconds = Math.max(1, Math.floor(deltaMs / 1000));
  if (deltaSeconds < 60) {
    return `${deltaSeconds}s ago`;
  }
  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) {
    return `${deltaMinutes}m ago`;
  }
  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) {
    return `${deltaHours}h ago`;
  }
  return `${Math.floor(deltaHours / 24)}d ago`;
}

function normalizeBaselineKey(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  return value.trim().toLowerCase();
}

function opportunityTitle(opportunity: BuyOpportunity): string {
  return opportunity.title ?? opportunity.itemId ?? opportunity.itemIdRef ?? '未命名商品';
}

function opportunityFingerprint(opportunity: BuyOpportunity): string {
  return opportunity.baselineMatchKey ?? opportunity.itemIdRef ?? opportunity.itemId ?? opportunity.id;
}

function opportunityTier(opportunity: BuyOpportunity): string {
  const rawTier = opportunity.baselineMatchLevel ?? opportunity.templateAvailabilityTier ?? opportunity.specContract?.status ?? 'S';
  const normalized = rawTier.trim().toUpperCase();
  if (['S', 'A', 'B', 'C', 'D'].includes(normalized)) {
    return normalized;
  }
  return 'S';
}

function discountVsFair(opportunity: BuyOpportunity): number | null {
  const current = numeric(opportunity.currentPrice);
  const fair = numeric(opportunity.fairPrice);
  if (current === null || fair === null || fair === 0) {
    const rawDiscount = numeric(opportunity.discountRate);
    if (rawDiscount === null) {
      return null;
    }
    const normalized = Math.abs(rawDiscount) <= 1 ? rawDiscount * 100 : rawDiscount;
    return normalized > 0 ? -normalized : normalized;
  }
  return ((current - fair) / fair) * 100;
}

function formatDiscount(opportunity: BuyOpportunity): string {
  const discount = discountVsFair(opportunity);
  if (discount === null) {
    return '-';
  }
  const marker = discount <= 0 ? '▾' : '▴';
  return `${marker} ${discount.toFixed(1)}%`;
}

function priceTip(opportunity: BuyOpportunity): string {
  const current = numeric(opportunity.currentPrice);
  const fair = numeric(opportunity.fairPrice);
  const buy = numeric(opportunity.buyCeiling);
  if (current === null) {
    return '价格证据不足';
  }
  const fairGap = fair === null ? '-' : formatYuan(fair - current);
  const buyGap = buy === null ? '-' : formatYuan(buy - current);
  return `比 P50 低 ${fairGap} · 比 P15 低 ${buyGap}`;
}

function baselineEvidenceFor(
  opportunity: BuyOpportunity,
  evidenceByKey: Map<string, BaselineEvidence>,
): BaselineEvidence | null {
  const keys = [
    opportunity.baselineMatchKey,
    opportunityFingerprint(opportunity),
  ].map(normalizeBaselineKey).filter((key): key is string => Boolean(key));
  for (const key of keys) {
    const evidence = evidenceByKey.get(key);
    if (evidence) {
      return evidence;
    }
  }
  return null;
}

function p15Price(opportunity: BuyOpportunity, evidence: BaselineEvidence | null): number | null {
  return numeric(evidence?.buyCeiling) ?? numeric(opportunity.buyCeiling) ?? numeric(opportunity.currentPrice);
}

function p50Price(opportunity: BuyOpportunity, evidence: BaselineEvidence | null): number | null {
  return numeric(evidence?.fairPrice) ?? numeric(opportunity.fairPrice) ?? numeric(opportunity.currentPrice);
}

function p35Price(opportunity: BuyOpportunity, evidence: BaselineEvidence | null): number | null {
  const p15 = p15Price(opportunity, evidence);
  const p50 = p50Price(opportunity, evidence);
  if (p15 === null && p50 === null) {
    return numeric(opportunity.currentPrice);
  }
  if (p15 === null) {
    return p50;
  }
  if (p50 === null) {
    return p15;
  }
  return p15 + (p50 - p15) * 0.35;
}

function baselineSampleLabel(opportunity: BuyOpportunity, evidence: BaselineEvidence | null): string {
  const sampleSize = numeric(evidence?.sampleSize);
  return `n=${sampleSize === null ? '--' : formatNumber(sampleSize)} · ${opportunityTier(opportunity)}`;
}

function schemaTag(opportunity: BuyOpportunity): string | null {
  const schemaId = numeric(opportunity.schemaId);
  return schemaId === null ? null : `schema ${formatNumber(schemaId)}`;
}

function fingerprintTag(opportunity: BuyOpportunity): string | null {
  const fingerprint = opportunity.sampleSnapshot?.fingerprintHash?.trim();
  if (!fingerprint) {
    return null;
  }
  return `fp ${fingerprint.slice(0, 8)}`;
}

function sampleStateLabel(opportunity: BuyOpportunity): string | null {
  switch (opportunity.sampleSnapshot?.sampleState) {
    case 'eligible':
      return '样本可用';
    case 'missing_required_attrs':
      return '指纹缺字段';
    case 'condition_unknown':
      return '成色待判';
    case 'rejected':
      return '样本已挡';
    default:
      return null;
  }
}

function feedbackTag(opportunity: BuyOpportunity): string | null {
  const label = opportunity.feedbackSummary?.feedbackLabel?.trim();
  if (!label) {
    return null;
  }
  const recordedAt = formatCompactRelative(opportunity.feedbackSummary?.recordedAt);
  return recordedAt === '-' ? `反馈 ${label}` : `反馈 ${label} ${recordedAt}`;
}

function isTextEditingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return tagName === 'input' || tagName === 'textarea' || tagName === 'select' || target.isContentEditable;
}

function useRelativeClock(): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setTick((current) => current + 1);
    }, 30000);
    return () => {
      window.clearInterval(interval);
    };
  }, []);

  return tick;
}

export function BuyWorkbenchPage() {
  const location = useLocation();
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
  const [sheetOpportunity, setSheetOpportunity] = useState<BuyOpportunity | null>(null);
  const relativeClockTick = useRelativeClock();

  const feedback = workbench?.feedbackQuality;
  const calibration = workbench?.feedbackCalibration;
  const recommendations = calibration?.recommendations;
  const effectiveCalibrationConfig = calibration?.effectiveCalibrationConfig;
  const dataValue = workbench?.dataValue;
  const dailyOpportunityPack = workbench?.dailyOpportunityPack;
  const outcomeFunnel = workbench?.outcomeFunnel;
  const summary = workbench?.summary;
  const opportunities = workbench?.opportunities ?? [];
  const baselines = useMemo(() => workbench?.baselines ?? [], [workbench?.baselines]);
  const watchTargets = workbench?.watchTargets ?? [];
  const generatedAtLabel = dailyOpportunityPack?.generatedAt
    ? dateFormatter.format(new Date(dailyOpportunityPack.generatedAt))
    : dateFormatter.format(new Date());
  const baselineEvidenceByKey = useMemo(() => {
    const evidence = new Map<string, BaselineEvidence>();
    dailyOpportunityPack?.marketIntel.forEach((entry) => {
      const key = normalizeBaselineKey(entry.baselineKey);
      if (key) {
        evidence.set(key, entry);
      }
    });
    baselines.forEach((baseline) => {
      const key = normalizeBaselineKey(baseline.baselineKey);
      if (key && !evidence.has(key)) {
        evidence.set(key, baseline);
      }
    });
    return evidence;
  }, [baselines, dailyOpportunityPack?.marketIntel]);

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
  const selectedRecommendationCount = selectedRecommendationIds.length;

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
    <AppFrame className="buy-desk-app">
      <main className="buy-desk">
        {error ? <div className="error-banner">{error}</div> : null}

        {isLoading && !workbench ? (
          <section className="desk-section">
            <p className="eyebrow">Workbench</p>
            <h2>正在同步买入机会与反馈校准...</h2>
            <p className="panel-subtitle">正在拉取机会池、价格基线、监控目标和反馈建议。</p>
          </section>
        ) : null}

        <section className="buy-desk-grid">
          <MarketSidebar
            categoryCode={categoryCode}
            baselinesCount={baselines.length}
            opportunityCount={summary?.opportunityCount}
            watchTargetCount={watchTargets.length}
          />

          <div className="buy-desk-desk">
            <header className="buy-desk-header">
              <div>
                <h1>今日机会</h1>
                <p className="panel-subtitle">
                  {generatedAtLabel} · {formatNumber(summary?.opportunityCount ?? summary?.todayOpportunityCount)} opp · <span className={isRefreshing ? 'desk-live is-syncing' : 'desk-live'}>● live</span>
                </p>
              </div>
              <button className="desk-filter" type="button">
                <SlidersHorizontal size={14} aria-hidden="true" />
                Filters
              </button>
            </header>

            <MetricTape summary={summary} outcomeFunnel={outcomeFunnel} />

            {dailyOpportunityPack ? (
              <DailyOpportunityPack
                feedbackByOpportunity={feedbackByOpportunity}
                feedbackPendingId={feedbackPendingId}
                baselineEvidenceByKey={baselineEvidenceByKey}
                pack={dailyOpportunityPack}
                purchaseOutcomeOpportunityId={purchaseOutcomeOpportunityId}
                relativeClockTick={relativeClockTick}
                onFeedback={(opportunity, feedbackLabel) => {
                  void handleFeedback(opportunity, feedbackLabel);
                }}
                onListingOpen={recordListingOpen}
                onOpenOpportunity={setSheetOpportunity}
                onPurchaseCancel={() => {
                  setPurchaseOutcomeOpportunityId(null);
                }}
                onPurchaseIntent={(opportunity) => {
                  setPurchaseOutcomeOpportunityId(opportunity.id);
                }}
                onPurchasedOutcome={handlePurchasedOutcome}
              />
            ) : null}

            {!dailyOpportunityPack ? (
              <OpportunityPool
                feedbackByOpportunity={feedbackByOpportunity}
                feedbackPendingId={feedbackPendingId}
                baselineEvidenceByKey={baselineEvidenceByKey}
                opportunities={opportunities}
                purchaseOutcomeOpportunityId={purchaseOutcomeOpportunityId}
                relativeClockTick={relativeClockTick}
                onFeedback={(opportunity, feedbackLabel) => {
                  void handleFeedback(opportunity, feedbackLabel);
                }}
                onListingOpen={recordListingOpen}
                onOpenOpportunity={setSheetOpportunity}
                onPurchaseCancel={() => {
                  setPurchaseOutcomeOpportunityId(null);
                }}
                onPurchaseIntent={(opportunity) => {
                  setPurchaseOutcomeOpportunityId(opportunity.id);
                }}
                onPurchasedOutcome={handlePurchasedOutcome}
              />
            ) : null}
          </div>
        </section>

        <section className="buy-desk-support-grid" aria-label="买方辅助面板">
          {dataValue ? <DataValueCockpit dataValue={dataValue} /> : null}
          <CalibrationPanel
            calibration={calibration}
            calibrationPending={calibrationPending}
            calibrationRecommendations={calibrationRecommendations}
            calibrationState={calibrationState}
            effectiveCalibrationConfig={effectiveCalibrationConfig}
            feedback={feedback}
            lastAppliedRecommendationCount={effectiveCalibrationConfig?.lastAppliedRecommendationIds?.length ?? 0}
            outcomeFunnel={outcomeFunnel}
            recommendationIds={selectableRecommendationIds}
            selectedRecommendationCount={selectedRecommendationCount}
            selectedRecommendationIdSet={selectedRecommendationIdSet}
            summary={summary}
            onApplyCalibration={() => {
              void handleApplyCalibration();
            }}
            onClearRecommendations={() => {
              setSelectedRecommendationIds([]);
            }}
            onSelectAllRecommendations={() => {
              setSelectedRecommendationIds(selectableRecommendationIds);
            }}
            onToggleRecommendation={toggleRecommendationSelection}
          />
          <WatchTargetsPanel watchTargets={watchTargets} />
          <BaselinesPanel baselines={baselines} />
        </section>

        <OpportunityDetailSheet
          feedbackByOpportunity={feedbackByOpportunity}
          feedbackPendingId={feedbackPendingId}
          isOpen={Boolean(sheetOpportunity)}
          onClose={() => {
            setPurchaseOutcomeOpportunityId(null);
            setSheetOpportunity(null);
          }}
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
          purchaseOutcomeOpportunityId={purchaseOutcomeOpportunityId}
          opportunity={sheetOpportunity}
          baselineEvidence={sheetOpportunity ? baselineEvidenceFor(sheetOpportunity, baselineEvidenceByKey) : null}
        />
      </main>
    </AppFrame>
  );
}

function MarketSidebar(props: {
  baselinesCount: number;
  categoryCode: string | null | undefined;
  opportunityCount: number | null | undefined;
  watchTargetCount: number;
}) {
  return (
    <aside className="buy-desk-sidebar" aria-label="品类导航">
      <nav className="desk-sidebar-tree" aria-label="SKU 指纹树">
        <div className="desk-tree-row is-root">APPLE</div>
        <div className="desk-tree-row is-level-1">MacBook Pro 14</div>
        <div className="desk-tree-row is-level-2">M3 Max</div>
        <button className={props.categoryCode === 'apple_computer' ? 'desk-tree-row is-level-3 is-active' : 'desk-tree-row is-level-3 is-active'} type="button">
          16C/40G 64G/1T 深空黑
        </button>
        <button className="desk-tree-row is-level-3" type="button">
          16C/40G 32G/512G
        </button>
        <div className="desk-tree-row is-level-2">M3 Pro</div>
        <div className="desk-tree-row is-level-1">Mac Studio</div>
        <div className="desk-tree-row is-level-1">关注基线</div>
        <div className="desk-tree-row is-level-1">数据报告</div>
      </nav>
      <div className="desk-sidebar-metrics">
        <span>opp {formatNumber(props.opportunityCount)}</span>
        <span>base {formatNumber(props.baselinesCount)}</span>
        <span>watch {formatNumber(props.watchTargetCount)}</span>
      </div>
    </aside>
  );
}

function MetricTape(props: {
  outcomeFunnel?: BuyWorkbench['outcomeFunnel'];
  summary?: BuyWorkbench['summary'];
}) {
  return (
    <section className="metric-tape" aria-label="机会工作区摘要">
      <div>
        <span>机会</span>
        <strong data-number>{formatNumber(props.summary?.opportunityCount)}</strong>
      </div>
      <div>
        <span>基线</span>
        <strong data-number>{formatNumber(props.summary?.baselineCount)}</strong>
      </div>
      <div>
        <span>反馈</span>
        <strong data-number>{formatNumber(props.summary?.feedbackCount)}</strong>
      </div>
      <div>
        <span>命中率</span>
        <strong data-number>{formatPercent((props.summary?.alertHitRate ?? 0) * 100, 1)}</strong>
      </div>
      <div>
        <span>结果证据</span>
        <strong data-number>{formatNumber(props.outcomeFunnel?.purchasedOpportunityCount)}</strong>
        <small>打开 {formatNumber(props.outcomeFunnel?.openedOpportunityCount)} · 联系 {formatNumber(props.outcomeFunnel?.contactedOpportunityCount)} · ROI 证据 {formatNumber(props.outcomeFunnel?.roiEvidenceCount)}</small>
      </div>
    </section>
  );
}

function DailyOpportunityPack(props: {
  baselineEvidenceByKey: Map<string, BaselineEvidence>;
  feedbackByOpportunity: Record<string, FeedbackState>;
  feedbackPendingId: string | null;
  pack: DailyOpportunityPackModel;
  purchaseOutcomeOpportunityId: string | null;
  relativeClockTick: number;
  onFeedback: (opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) => void;
  onListingOpen: (opportunity: BuyOpportunity) => void;
  onOpenOpportunity: (opportunity: BuyOpportunity) => void;
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
  const rows = useMemo<DeskTask[]>(
    () => tasks.map((task) => ({
      groupLabel: task.groupLabel,
      rank: task.rank,
      reason: task.reason,
      recommendedAction: task.recommendedAction,
      slaLabel: task.slaLabel,
      opportunity: task.opportunity,
      valueSignals: task.valueSignals,
      riskFlags: task.riskFlags,
    })),
    [tasks],
  );
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string | null>(null);
  const activeSelectedOpportunityId = rows.some((row) => row.opportunity.id === selectedOpportunityId)
    ? selectedOpportunityId
    : (rows[0]?.opportunity.id ?? null);
  const selectedIndex = Math.max(0, rows.findIndex((row) => row.opportunity.id === activeSelectedOpportunityId));
  const selectedRow = rows[selectedIndex] ?? rows[0] ?? null;

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (!rows.length || !selectedRow || isTextEditingTarget(event.target)) {
        return;
      }

      if (event.key === 'j' || event.key === 'J') {
        event.preventDefault();
        const nextRow = rows[(selectedIndex + 1) % rows.length];
        setSelectedOpportunityId(nextRow?.opportunity.id ?? null);
        return;
      }

      if (event.key === 'k' || event.key === 'K') {
        event.preventDefault();
        const previousRow = rows[(selectedIndex - 1 + rows.length) % rows.length];
        setSelectedOpportunityId(previousRow?.opportunity.id ?? null);
        return;
      }

      if (event.key === 'Enter') {
        event.preventDefault();
        props.onOpenOpportunity(selectedRow.opportunity);
        return;
      }

      if (event.key === 'a' || event.key === 'A') {
        event.preventDefault();
        props.onFeedback(selectedRow.opportunity, 'contacted');
        return;
      }

      if (event.key === 'd' || event.key === 'D') {
        event.preventDefault();
        props.onFeedback(selectedRow.opportunity, 'not_worth_it');
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [props, rows, selectedIndex, selectedRow]);

  return (
    <section className="desk-section buy-daily-panel">
      <div className="desk-section-header">
        <div>
          <p className="eyebrow">Daily Opportunity Pack</p>
          <h2>今日机会任务包</h2>
          <p className="panel-subtitle">{summary.northStar ?? '把 OPEN 机会消化成反馈、联系、成交和 ROI 证据'}。</p>
        </div>
        <div className="desk-header-meta">
          <strong data-number>{formatNumber(summary.packOpportunityCount)} 条入队</strong>
          <small>OPEN backlog {formatNumber(summary.openBacklogCount)} · 未入队 {formatNumber(summary.ungroupedOpenCount)}</small>
        </div>
      </div>

      {rows.length ? (
        <OpportunityRows
          feedbackByOpportunity={props.feedbackByOpportunity}
          feedbackPendingId={props.feedbackPendingId}
          baselineEvidenceByKey={props.baselineEvidenceByKey}
          purchaseOutcomeOpportunityId={props.purchaseOutcomeOpportunityId}
          relativeClockTick={props.relativeClockTick}
          rows={rows}
          selectedOpportunityId={activeSelectedOpportunityId}
          onFeedback={props.onFeedback}
          onListingOpen={props.onListingOpen}
          onOpenOpportunity={props.onOpenOpportunity}
          onPurchaseCancel={props.onPurchaseCancel}
          onPurchaseIntent={props.onPurchaseIntent}
          onPurchasedOutcome={props.onPurchasedOutcome}
          onSelect={setSelectedOpportunityId}
        />
      ) : (
        <div className="buy-empty-state">
          当前没有可入队 OPEN 机会。先处理已有反馈，或按需刷新 baseline / opportunity。
        </div>
      )}

      {pack.marketIntel.length ? (
        <div className="desk-intel-strip">
          <strong>今日议价锚点</strong>
          {pack.marketIntel.slice(0, 4).map((entry) => (
            <span key={entry.baselineKey ?? `${entry.fairPrice}:${entry.buyCeiling}`}>
              {entry.baselineKey ?? 'baseline'} · fair {formatCurrency(entry.fairPrice)} · buy {formatCurrency(entry.buyCeiling)} · n={formatNumber(entry.sampleSize)}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function OpportunityPool(props: {
  baselineEvidenceByKey: Map<string, BaselineEvidence>;
  feedbackByOpportunity: Record<string, FeedbackState>;
  feedbackPendingId: string | null;
  opportunities: BuyOpportunity[];
  purchaseOutcomeOpportunityId: string | null;
  relativeClockTick: number;
  onFeedback: (opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) => void;
  onListingOpen: (opportunity: BuyOpportunity) => void;
  onOpenOpportunity: (opportunity: BuyOpportunity) => void;
  onPurchaseCancel: () => void;
  onPurchaseIntent: (opportunity: BuyOpportunity) => void;
  onPurchasedOutcome: (
    opportunity: BuyOpportunity,
    outcome: Pick<BuyFeedbackRequest, 'purchasePrice' | 'expectedResalePrice' | 'feedbackNote'>,
  ) => Promise<void>;
}) {
  const rows = useMemo<DeskTask[]>(
    () => props.opportunities.map((opportunity, index) => ({
      groupLabel: opportunity.status,
      rank: index + 1,
      reason: opportunity.explanation?.readinessSummary,
      slaLabel: formatRelative(opportunity.lastDetectedAt),
      opportunity,
      valueSignals: [
        `机会 ${formatNumber(opportunity.opportunityScore)}`,
        `风险 ${formatNumber(opportunity.riskScore)}`,
      ],
      riskFlags: opportunity.explanation?.missingRequiredFields?.map((field) => `缺 ${field}`) ?? [],
    })),
    [props.opportunities],
  );
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string | null>(rows[0]?.opportunity.id ?? null);

  return (
    <section className="desk-section">
      <div className="desk-section-header">
        <div>
          <p className="eyebrow">Opportunity Pool</p>
          <h2>机会池</h2>
          <p className="panel-subtitle">全量候选使用同一行式读法，避免卡片稀释价格信息。</p>
        </div>
        <div className="desk-header-meta">
          <strong data-number>{formatNumber(rows.length)} 条候选</strong>
        </div>
      </div>

      {rows.length ? (
        <OpportunityRows
          feedbackByOpportunity={props.feedbackByOpportunity}
          feedbackPendingId={props.feedbackPendingId}
          baselineEvidenceByKey={props.baselineEvidenceByKey}
          purchaseOutcomeOpportunityId={props.purchaseOutcomeOpportunityId}
          relativeClockTick={props.relativeClockTick}
          rows={rows}
          selectedOpportunityId={selectedOpportunityId}
          onFeedback={props.onFeedback}
          onListingOpen={props.onListingOpen}
          onOpenOpportunity={props.onOpenOpportunity}
          onPurchaseCancel={props.onPurchaseCancel}
          onPurchaseIntent={props.onPurchaseIntent}
          onPurchasedOutcome={props.onPurchasedOutcome}
          onSelect={setSelectedOpportunityId}
        />
      ) : (
        <div className="buy-empty-state">
          暂无机会。先运行 `build-buy-baselines` 和 `refresh-buy-opportunities`。
        </div>
      )}
    </section>
  );
}

function OpportunityRows(props: {
  baselineEvidenceByKey: Map<string, BaselineEvidence>;
  feedbackByOpportunity: Record<string, FeedbackState>;
  feedbackPendingId: string | null;
  purchaseOutcomeOpportunityId: string | null;
  relativeClockTick: number;
  rows: DeskTask[];
  selectedOpportunityId: string | null;
  onFeedback: (opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) => void;
  onListingOpen: (opportunity: BuyOpportunity) => void;
  onOpenOpportunity: (opportunity: BuyOpportunity) => void;
  onPurchaseCancel: () => void;
  onPurchaseIntent: (opportunity: BuyOpportunity) => void;
  onPurchasedOutcome: (
    opportunity: BuyOpportunity,
    outcome: Pick<BuyFeedbackRequest, 'purchasePrice' | 'expectedResalePrice' | 'feedbackNote'>,
  ) => Promise<void>;
  onSelect: (opportunityId: string) => void;
}) {
  return (
    <div className="desk-table" aria-label="机会列表">
      <div className="desk-table-head" aria-hidden="true">
        <span>#rank</span>
        <span>SKU+signal</span>
        <span>PRICE</span>
        <span>DELTA vs P50</span>
        <span>GAUGE</span>
        <span>SCORE</span>
        <span>LISTED</span>
        <span>ACTIONS</span>
      </div>
      {props.rows.map((row) => (
        <OpportunityRow
          feedbackByOpportunity={props.feedbackByOpportunity}
          feedbackPendingId={props.feedbackPendingId}
          baselineEvidence={baselineEvidenceFor(row.opportunity, props.baselineEvidenceByKey)}
          isSelected={props.selectedOpportunityId === row.opportunity.id}
          key={`${row.groupLabel ?? 'pool'}:${row.opportunity.id}`}
          purchaseOutcomeOpportunityId={props.purchaseOutcomeOpportunityId}
          relativeClockTick={props.relativeClockTick}
          row={row}
          onFeedback={props.onFeedback}
          onListingOpen={props.onListingOpen}
          onOpenOpportunity={props.onOpenOpportunity}
          onPurchaseCancel={props.onPurchaseCancel}
          onPurchaseIntent={props.onPurchaseIntent}
          onPurchasedOutcome={props.onPurchasedOutcome}
          onSelect={props.onSelect}
        />
      ))}
    </div>
  );
}

function InlinePriceGauge(props: {
  baselineEvidence: BaselineEvidence | null;
  opportunity: BuyOpportunity;
}) {
  const { opportunity, baselineEvidence } = props;
  const p15 = p15Price(opportunity, baselineEvidence);
  const p35 = p35Price(opportunity, baselineEvidence);
  const p50 = p50Price(opportunity, baselineEvidence);
  const current = numeric(opportunity.currentPrice) ?? p35 ?? p15 ?? p50 ?? 0;
  const values = [p15, p35, p50, current].filter((value): value is number => value !== null);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const position = (value: number | null) => {
    if (value === null) {
      return 50;
    }
    return Math.max(0, Math.min(100, ((value - min) / range) * 100));
  };
  const style = {
    '--gauge-current': `${position(current)}%`,
    '--gauge-p15': `${position(p15)}%`,
    '--gauge-p35': `${position(p35)}%`,
    '--gauge-p50': `${position(p50)}%`,
  } as CSSProperties;

  return (
    <div
      aria-label={`P15 ${formatYuan(p15)} P35 ${formatYuan(p35)} P50 ${formatYuan(p50)}`}
      className="desk-price-gauge"
      style={style}
    >
      <span className="desk-gauge-track" aria-hidden="true" />
      <span className="desk-gauge-tick is-p15" aria-hidden="true" />
      <span className="desk-gauge-tick is-p35" aria-hidden="true" />
      <span className="desk-gauge-tick is-p50" aria-hidden="true" />
      <span className={current <= (p35 ?? current) ? 'desk-gauge-dot is-buy' : 'desk-gauge-dot'} aria-hidden="true" />
      <span className="desk-gauge-label is-p15">P15</span>
      <span className="desk-gauge-label is-p35">P35</span>
      <span className="desk-gauge-label is-p50">P50</span>
    </div>
  );
}

function OpportunityRow(props: {
  baselineEvidence: BaselineEvidence | null;
  feedbackByOpportunity: Record<string, FeedbackState>;
  feedbackPendingId: string | null;
  isSelected: boolean;
  purchaseOutcomeOpportunityId: string | null;
  relativeClockTick: number;
  row: DeskTask;
  onFeedback: (opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) => void;
  onListingOpen: (opportunity: BuyOpportunity) => void;
  onOpenOpportunity: (opportunity: BuyOpportunity) => void;
  onPurchaseCancel: () => void;
  onPurchaseIntent: (opportunity: BuyOpportunity) => void;
  onPurchasedOutcome: (
    opportunity: BuyOpportunity,
    outcome: Pick<BuyFeedbackRequest, 'purchasePrice' | 'expectedResalePrice' | 'feedbackNote'>,
  ) => Promise<void>;
  onSelect: (opportunityId: string) => void;
}) {
  const opportunity = props.row.opportunity;
  const feedbackState = props.feedbackByOpportunity[opportunity.id];
  const isPending = props.feedbackPendingId === opportunity.id;
  const discount = discountVsFair(opportunity);
  const title = opportunityTitle(opportunity);
  const sellerScore = numeric(opportunity.specConfidence);
  const sellerLabel = sellerScore === null
    ? '卖家 --'
    : `卖家 ${sellerScore <= 1 ? sellerScore.toFixed(2) : (sellerScore / 100).toFixed(2)}`;
  const signalLine = [
    sellerLabel,
    props.row.valueSignals?.[0] ?? opportunity.explanation?.readinessSummary ?? '95%new',
    baselineSampleLabel(opportunity, props.baselineEvidence),
    sampleStateLabel(opportunity),
    feedbackTag(opportunity),
  ].filter((value): value is string => Boolean(value)).join(' · ');
  const metadataPills = [schemaTag(opportunity), fingerprintTag(opportunity)].filter((value): value is string => Boolean(value));
  const rowClassName = [
    'desk-opportunity-row',
    props.isSelected ? 'is-selected' : '',
    discount !== null && discount <= 0 ? 'is-discount' : 'is-premium',
  ].filter(Boolean).join(' ');

  void props.relativeClockTick;

  return (
    <article
      className={rowClassName}
      tabIndex={0}
      onClick={() => {
        props.onSelect(opportunity.id);
        props.onOpenOpportunity(opportunity);
      }}
      onFocus={() => {
        props.onSelect(opportunity.id);
      }}
      onMouseEnter={() => {
        props.onSelect(opportunity.id);
      }}
    >
      <div className="desk-row-rank" data-number>
        #{formatNumber(props.row.rank)}
      </div>

      <div className="desk-row-main">
        <div className="desk-row-title-line">
          <h3 title={title}>{title}</h3>
          {metadataPills.map((pill) => (
            <span className="soft-pill" key={pill}>
              <code>{pill}</code>
            </span>
          ))}
        </div>
        <p className="desk-row-note" title={signalLine}>{signalLine}</p>
      </div>

      <div className="desk-row-price" data-number data-price-tip={priceTip(opportunity)}>
        <strong>{formatYuan(opportunity.currentPrice)}</strong>
      </div>

      <div className="desk-row-delta">
        <strong>{formatDiscount(opportunity)}</strong>
      </div>

      <div className="desk-row-baseline">
        <InlinePriceGauge baselineEvidence={props.baselineEvidence} opportunity={opportunity} />
      </div>

      <div className="desk-row-score" data-number>
        <span className="desk-score-badge is-score">{formatNumber(opportunity.opportunityScore)}</span>
        <span className="desk-score-badge is-risk">{formatNumber(opportunity.riskScore)}</span>
      </div>

      <div className="desk-row-listed" data-number>
        {formatCompactRelative(opportunity.lastDetectedAt)}
      </div>

      <div className="desk-row-actions" aria-label="机会动作">
        <button
          aria-label="Watch opportunity"
          className="desk-action-icon"
          disabled={isPending}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            props.onFeedback(opportunity, 'contacted');
          }}
        >
          <Heart size={16} aria-hidden="true" />
        </button>
        <button
          aria-label="Skip opportunity"
          className="desk-action-icon"
          disabled={isPending}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            props.onFeedback(opportunity, 'not_worth_it');
          }}
        >
          <X size={16} aria-hidden="true" />
        </button>
        <button
          aria-label="Mark bought"
          className="desk-action-icon"
          disabled={isPending}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            props.onPurchaseIntent(opportunity);
          }}
        >
          <Check size={16} aria-hidden="true" />
        </button>
        {opportunity.listingUrl ? (
          <a
            aria-label="Open listing"
            className="desk-action-icon"
            href={opportunity.listingUrl}
            rel="noreferrer"
            target="_blank"
            onClick={(event) => {
              event.stopPropagation();
              props.onListingOpen(opportunity);
            }}
          >
            <ExternalLink size={16} aria-hidden="true" />
          </a>
        ) : null}
      </div>

      {feedbackState?.message ? (
        <p className={`buy-feedback-result ${feedbackState.kind === 'error' ? 'is-error' : feedbackState.kind === 'success' ? 'is-success' : ''}`}>
          {feedbackState.message}
        </p>
      ) : null}

      {props.purchaseOutcomeOpportunityId === opportunity.id ? (
        <div className="desk-row-form" onClick={(event) => event.stopPropagation()}>
          <PurchaseOutcomeForm
            buyCeiling={opportunity.buyCeiling}
            currentPrice={opportunity.currentPrice}
            fairPrice={opportunity.fairPrice}
            isPending={isPending}
            onCancel={props.onPurchaseCancel}
            onSubmit={(outcome) => props.onPurchasedOutcome(opportunity, outcome)}
          />
        </div>
      ) : null}
    </article>
  );
}

function OpportunityDetailSheet(props: {
  baselineEvidence: BaselineEvidence | null;
  feedbackByOpportunity: Record<string, FeedbackState>;
  feedbackPendingId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onFeedback: (opportunity: BuyOpportunity, feedbackLabel: BuyFeedbackRequest['feedbackLabel']) => void;
  onListingOpen: (opportunity: BuyOpportunity) => void;
  onPurchaseCancel: () => void;
  onPurchaseIntent: (opportunity: BuyOpportunity) => void;
  onPurchasedOutcome: (
    opportunity: BuyOpportunity,
    outcome: Pick<BuyFeedbackRequest, 'purchasePrice' | 'expectedResalePrice' | 'feedbackNote'>,
  ) => Promise<void>;
  opportunity: BuyOpportunity | null;
  purchaseOutcomeOpportunityId: string | null;
}) {
  if (!props.isOpen || !props.opportunity) {
    return null;
  }

  const opportunity = props.opportunity;
  const title = opportunityTitle(opportunity);
  const feedbackState = props.feedbackByOpportunity[opportunity.id];
  const isPending = props.feedbackPendingId === opportunity.id;
  const discount = discountVsFair(opportunity);
  const p15 = p15Price(opportunity, props.baselineEvidence);
  const p35 = p35Price(opportunity, props.baselineEvidence);
  const p50 = p50Price(opportunity, props.baselineEvidence);
  const confidence = numeric(props.baselineEvidence?.confidence) ?? numeric(opportunity.specConfidence);
  const sampleSize = numeric(props.baselineEvidence?.sampleSize);
  const sampleLabel = sampleSize === null ? 'n=--' : `n=${formatNumber(sampleSize)}`;
  const confidenceLabel = confidence === null
    ? 'confidence --'
    : `confidence ${confidence <= 1 ? confidence.toFixed(2) : (confidence / 100).toFixed(2)}`;
  const detailMetaLine = [schemaTag(opportunity), fingerprintTag(opportunity)].filter((value): value is string => Boolean(value)).join(' · ') || 'Opportunity evidence';
  const evidenceChips = [
    sampleStateLabel(opportunity),
    feedbackTag(opportunity),
    ...((opportunity.sampleSnapshot?.missingRequiredAttrs ?? []).map((fieldName) => `缺 ${fieldName}`)),
  ].filter((value): value is string => Boolean(value));

  return (
    <Sheet open={props.isOpen} onOpenChange={(open) => {
      if (!open) {
        props.onClose();
      }
    }}>
      <SheetContent side="right" className="buy-detail-sheet">
        <SheetHeader className="detail-sheet-header">
          <SheetDescription className="detail-breadcrumb">{detailMetaLine}</SheetDescription>
          <SheetTitle className="detail-title" title={title}>{title}</SheetTitle>
        </SheetHeader>

        <section className="detail-price-block">
          <strong data-number>{formatYuan(opportunity.currentPrice)}</strong>
          <span className={discount !== null && discount <= 0 ? 'detail-status-line is-success' : 'detail-status-line is-danger'}>
            {formatDiscount(opportunity)} below P50 · score <b>{formatNumber(opportunity.opportunityScore)}</b> · risk <b>{formatNumber(opportunity.riskScore)}</b>
          </span>
        </section>

        <section className="detail-trend-block">
          <h3>90-day trend</h3>
          <svg className="detail-trend-chart" role="img" aria-label="90 day price trend with P15 P35 P50 reference lines" viewBox="0 0 420 148">
            <line className="detail-trend-reference" x1="38" x2="408" y1="44" y2="44" />
            <line className="detail-trend-reference" x1="38" x2="408" y1="76" y2="76" />
            <line className="detail-trend-reference" x1="38" x2="408" y1="108" y2="108" />
            <text x="0" y="49">P50</text>
            <text x="0" y="81">P35</text>
            <text x="0" y="113">P15</text>
            <polyline className="detail-trend-line" points="42,28 78,34 116,46 154,48 192,58 230,62 268,70 306,78 344,84 404,98" />
            <circle cx="58" cy="40" r="3" />
            <circle cx="92" cy="64" r="3" />
            <circle cx="146" cy="56" r="3" />
            <circle cx="206" cy="42" r="3" />
            <circle cx="246" cy="70" r="3" />
            <circle cx="286" cy="62" r="3" />
            <circle cx="330" cy="92" r="3" />
            <circle cx="384" cy="114" r="3" />
          </svg>
          <p>P50 trend -2.3%/week</p>
        </section>

        <section className="detail-condition-block">
          <h3>Evidence</h3>
          <div className="detail-chip-row">
            {evidenceChips.length ? evidenceChips.map((chip) => (
              <span key={chip}>{chip}</span>
            )) : <span>等待更多结构化证据</span>}
          </div>
        </section>

        <section className="detail-baseline-block">
          <h3>Baseline · Tier {opportunityTier(opportunity)} · {sampleLabel}{schemaTag(opportunity) ? ` · ${schemaTag(opportunity)}` : ''}</h3>
          <div className="detail-baseline-grid">
            <div>
              <span>P15</span>
              <strong data-number>{formatYuan(p15)}</strong>
            </div>
            <div>
              <span>P35</span>
              <strong data-number>{formatYuan(p35)}</strong>
            </div>
            <div>
              <span>P50</span>
              <strong data-number>{formatYuan(p50)}</strong>
            </div>
          </div>
          <p>MAD ±¥680 · {confidenceLabel}{fingerprintTag(opportunity) ? ` · ${fingerprintTag(opportunity)}` : ''}</p>
        </section>

        <section className="detail-actions-block">
          <h3>Actions</h3>
          <div className="detail-action-row">
          {opportunity.listingUrl ? (
            <a
              className="is-primary"
              href={opportunity.listingUrl}
              rel="noreferrer"
              target="_blank"
              onClick={() => {
                props.onListingOpen(opportunity);
              }}
            >
              Open on Goofish
              <ArrowUpRight size={13} aria-hidden="true" />
            </a>
          ) : null}
          <button
            className="is-secondary"
            disabled={isPending}
            type="button"
            onClick={() => {
              props.onFeedback(opportunity, 'contacted');
            }}
          >
            Watch
          </button>
          <button
            className="is-secondary"
            disabled={isPending}
            type="button"
            onClick={() => {
              props.onFeedback(opportunity, 'not_worth_it');
            }}
          >
            Skip
          </button>
          <button
            className="is-secondary"
            disabled={isPending}
            type="button"
            onClick={() => {
              props.onPurchaseIntent(opportunity);
            }}
          >
            Mark bought
          </button>
          </div>
        </section>

        {feedbackState?.message ? (
          <p className={`buy-feedback-result ${feedbackState.kind === 'error' ? 'is-error' : feedbackState.kind === 'success' ? 'is-success' : ''}`}>
            {feedbackState.message}
          </p>
        ) : null}

        {props.purchaseOutcomeOpportunityId === opportunity.id ? (
          <PurchaseOutcomeForm
            buyCeiling={opportunity.buyCeiling}
            currentPrice={opportunity.currentPrice}
            fairPrice={opportunity.fairPrice}
            isPending={isPending}
            onCancel={props.onPurchaseCancel}
            onSubmit={(outcome) => props.onPurchasedOutcome(opportunity, outcome)}
          />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function DataValueCockpit(props: { dataValue: BuyDataValueReport }) {
  const { dataValue } = props;
  const summary = dataValue.summary;
  const diagnosis = dataValue.diagnosis;
  const primaryCategories = dataValue.categoryBreakdown.slice(0, 6);

  return (
    <section className="desk-section buy-value-panel">
      <div className="desk-section-header">
        <div>
          <p className="eyebrow">Data Value</p>
          <h2>数据资产利用率</h2>
        </div>
        <div className="desk-header-meta">
          <strong data-number>{formatNumber(summary.dataValueScore)} / 100</strong>
          <small>{diagnosis.statusLabel ?? '待诊断'}</small>
        </div>
      </div>
      <p className="desk-diagnosis"><strong>{diagnosis.summary}</strong><span>{diagnosis.nextBestAction}</span></p>
      <div className="desk-mini-grid">
        <div><span>有效商品</span><strong data-number>{formatNumber(summary.itemCount)}</strong></div>
        <div><span>结构化</span><strong data-number>{formatPercent((summary.specCoverageRate ?? 0) * 100, 1)}</strong></div>
        <div><span>OPEN</span><strong data-number>{formatNumber(summary.openOpportunityCount)}</strong></div>
        <div><span>ROI</span><strong data-number>{formatNumber(summary.roiEvidenceCount)}</strong></div>
      </div>
      <div className="desk-dense-table">
        {primaryCategories.map((category) => (
          <div className="desk-dense-row" key={category.categoryCode}>
            <span>{category.categoryCode}</span>
            <span>{formatNumber(category.itemCount)} 商品</span>
            <span>{formatNumber(category.openOpportunityCount)} OPEN</span>
            <span>{formatPercent((category.feedbackCoverageRate ?? 0) * 100, 1)} 反馈</span>
            <span>{formatNumber(category.utilizationScore)} 分</span>
          </div>
        ))}
      </div>
      {dataValue.recommendations.slice(0, 4).map((recommendation) => (
        <p className="desk-recommendation" key={`${recommendation.priority}:${recommendation.title}`}>
          <strong>{recommendation.priority ?? 'P?'} · {recommendation.title}</strong>
          <span>{recommendation.reason}</span>
          <span>{recommendation.action}</span>
        </p>
      ))}
    </section>
  );
}

function CalibrationPanel(props: {
  calibration?: BuyWorkbench['feedbackCalibration'];
  calibrationPending: boolean;
  calibrationRecommendations: Array<{
    id?: string | null;
    title: string;
    summary: string;
    recommendedAction: string;
  }>;
  calibrationState: FeedbackState;
  effectiveCalibrationConfig?: NonNullable<BuyWorkbench['feedbackCalibration']>['effectiveCalibrationConfig'];
  feedback?: BuyWorkbench['feedbackQuality'];
  lastAppliedRecommendationCount: number;
  outcomeFunnel?: BuyWorkbench['outcomeFunnel'];
  recommendationIds: string[];
  selectedRecommendationCount: number;
  selectedRecommendationIdSet: Set<string>;
  summary?: BuyWorkbench['summary'];
  onApplyCalibration: () => void;
  onClearRecommendations: () => void;
  onSelectAllRecommendations: () => void;
  onToggleRecommendation: (recommendationId: string) => void;
}) {
  const guidanceThresholds = props.effectiveCalibrationConfig?.pricingThresholds?.guidanceReady;
  const referenceThresholds = props.effectiveCalibrationConfig?.pricingThresholds?.referenceOnly;
  const scoringConfig = props.effectiveCalibrationConfig?.opportunityScoring;

  return (
    <section className="desk-section">
      <div className="desk-section-header">
        <div>
          <p className="eyebrow">Calibration</p>
          <h2>反馈校准</h2>
        </div>
        <div className="desk-header-meta">
          <strong data-number>{formatNumber(props.summary?.calibrationRecommendationCount)}</strong>
          <small>建议</small>
        </div>
      </div>

      <div className="desk-mini-grid">
        <div>
          <span>采纳/拒绝</span>
          <strong data-number>{formatNumber(props.summary?.acceptCount)} / {formatNumber(props.summary?.rejectCount)}</strong>
        </div>
        <div>
          <span>反馈覆盖</span>
          <strong data-number>{formatPercent((((props.feedback?.feedbackCount ?? 0) / Math.max(props.feedback?.opportunityCount ?? 1, 1)) * 100), 1)}</strong>
        </div>
        <div>
          <span>提醒→打开</span>
          <strong data-number>{formatPercent((props.outcomeFunnel?.alertToOpenRate ?? 0) * 100, 1)}</strong>
        </div>
        <div>
          <span>打开→联系</span>
          <strong data-number>{formatPercent((props.outcomeFunnel?.openToContactRate ?? 0) * 100, 1)}</strong>
        </div>
      </div>
      <p className="panel-subtitle">
        提醒→打开 {formatPercent((props.outcomeFunnel?.alertToOpenRate ?? 0) * 100, 1)} · 打开→联系 {formatPercent((props.outcomeFunnel?.openToContactRate ?? 0) * 100, 1)}
      </p>

      {props.effectiveCalibrationConfig ? (
        <div className="desk-dense-table">
          <div className="desk-dense-row">
            <span>guidance</span>
            <span>卖家样本 {formatNumber(guidanceThresholds?.seller_sample_count)}</span>
            <span>exact {formatPercent((guidanceThresholds?.exact_spec_ratio ?? 0) * 100, 1)}</span>
            <span>fresh {formatNumber(guidanceThresholds?.freshness_days)}d</span>
          </div>
          <div className="desk-dense-row">
            <span>reference</span>
            <span>卖家样本 {formatNumber(referenceThresholds?.seller_sample_count)}</span>
            <span>exact {formatPercent((referenceThresholds?.exact_spec_ratio ?? 0) * 100, 1)}</span>
            <span>fresh {formatNumber(referenceThresholds?.freshness_days)}d</span>
          </div>
          <div className="desk-dense-row">
            <span>scoring</span>
            <span>buy ceiling 收紧 {formatDecimal(scoringConfig?.buyCeilingTightenPct, 1)}% · risk penalty {formatDecimal(scoringConfig?.riskPenaltyWeight, 2)}</span>
            <span>discount {formatDecimal(scoringConfig?.discountRateWeight, 2)}</span>
            <span>conf {formatDecimal(scoringConfig?.confidenceWeight, 2)}</span>
          </div>
          <div className="desk-dense-row">
            <span>last</span>
            <span>{props.effectiveCalibrationConfig.lastAppliedAt ? `${formatRelative(props.effectiveCalibrationConfig.lastAppliedAt)} · ${props.effectiveCalibrationConfig.lastAppliedBy ?? 'system'}` : '尚未自动应用过校准'}</span>
            <span>window {formatNumber(props.effectiveCalibrationConfig.lastCalibrationWindowDays ?? props.calibration?.windowDays ?? 30)}d</span>
            <span>最近落地 {formatNumber(props.lastAppliedRecommendationCount)} 条建议</span>
          </div>
        </div>
      ) : null}

      <div className="desk-action-row">
        <button
          disabled={props.calibrationPending || !props.selectedRecommendationCount}
          type="button"
          onClick={props.onApplyCalibration}
        >
          {props.calibrationPending ? '应用中...' : '应用所选校准'}
        </button>
        <button
          disabled={props.calibrationPending || props.selectedRecommendationCount === props.recommendationIds.length}
          type="button"
          onClick={props.onSelectAllRecommendations}
        >
          全选
        </button>
        <button
          disabled={props.calibrationPending || props.selectedRecommendationCount === 0}
          type="button"
          onClick={props.onClearRecommendations}
        >
          清空
        </button>
      </div>

      {props.calibrationRecommendations.length ? (
        <p className="panel-subtitle">
          自动可执行 {formatNumber(props.recommendationIds.length)} 条 · 已选择 {formatNumber(props.selectedRecommendationCount)} / {formatNumber(props.recommendationIds.length)} 条可应用建议
        </p>
      ) : <p className="panel-subtitle">当前窗口暂无明确校准动作，继续积累反馈样本。</p>}

      {props.calibrationRecommendations.slice(0, 6).map((recommendation) => {
        const recommendationId = recommendation.id ?? null;
        const isSelected = recommendationId ? props.selectedRecommendationIdSet.has(recommendationId) : false;
        return (
          <label
            className={`desk-recommendation is-checkable ${isSelected ? 'is-selected' : ''}`}
            key={`${recommendation.id ?? recommendation.title}:${recommendation.recommendedAction}`}
          >
            <input
              aria-label={`选择建议 ${recommendation.title}`}
              checked={isSelected}
              disabled={!recommendationId}
              type="checkbox"
              onChange={() => {
                if (recommendationId) {
                  props.onToggleRecommendation(recommendationId);
                }
              }}
            />
            <strong>{recommendation.title}</strong>
            <span>{recommendation.summary}</span>
            <span>{recommendation.recommendedAction}</span>
          </label>
        );
      })}

      {props.calibrationState.message ? (
        <p className={`buy-feedback-result ${props.calibrationState.kind === 'error' ? 'is-error' : props.calibrationState.kind === 'success' ? 'is-success' : ''}`}>
          {props.calibrationState.message}
        </p>
      ) : null}
    </section>
  );
}

function WatchTargetsPanel(props: { watchTargets: NonNullable<BuyWorkbench['watchTargets']> }) {
  return (
    <section className="desk-section">
      <div className="desk-section-header">
        <div>
          <p className="eyebrow">Watch</p>
          <h2>监控目标</h2>
        </div>
        <div className="desk-header-meta">
          <strong data-number>{formatNumber(props.watchTargets.length)}</strong>
        </div>
      </div>
      <div className="desk-dense-table">
        {props.watchTargets.length ? props.watchTargets.map((target) => (
          <div className="desk-dense-row" key={target.id}>
            <span>{target.targetName}</span>
            <span>{target.profileKey ?? '-'}</span>
            <span>{target.status ?? '-'}</span>
            <span>cooldown {formatNumber(target.notifyCooldownMinutes)}m</span>
          </div>
        )) : <p className="panel-subtitle">暂无监控目标。刷新机会池时会自动创建默认目标。</p>}
      </div>
    </section>
  );
}

function BaselinesPanel(props: { baselines: NonNullable<BuyWorkbench['baselines']> }) {
  return (
    <section className="desk-section">
      <div className="desk-section-header">
        <div>
          <p className="eyebrow">Price Baselines</p>
          <h2>最新价格基线</h2>
        </div>
        <div className="desk-header-meta">
          <strong data-number>{formatNumber(props.baselines.length)}</strong>
        </div>
      </div>
      <div className="desk-dense-table">
        {props.baselines.length ? props.baselines.slice(0, 12).map((baseline) => (
          <div className="desk-dense-row" key={baseline.id}>
            <span>{baseline.baselineKey}</span>
            <span>fair {formatCurrency(baseline.fairPrice)}</span>
            <span>buy {formatCurrency(baseline.buyCeiling)}</span>
            <span>n={formatNumber(baseline.sampleSize)}</span>
          </div>
        )) : <p className="panel-subtitle">暂无 baseline。先运行 `build-buy-baselines --view all`。</p>}
      </div>
    </section>
  );
}
