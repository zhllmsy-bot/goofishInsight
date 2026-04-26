import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { AppFrame } from '../../../shared/components/AppFrame';
import { PageHero } from '../../../shared/components/PageHero';
import { formatCurrency, formatNumber, formatPercent, formatRelative } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation, readInitialQuery } from '../../dashboard/lib/urlState';
import { postBuyFeedback } from '../api/buyApi';
import { useBuyOpportunityDetail } from '../hooks/useBuyOpportunityDetail';
import type { BuyFeedbackRequest } from '../types/buy';
import { PurchaseOutcomeForm } from './PurchaseOutcomeForm';

import '../../dashboard/styles/dashboard.css';
import '../../item-detail/styles/item-detail.css';
import '../../progress/styles/progress.css';
import '../styles/buy-workbench.css';

type FeedbackState = {
  kind: 'idle' | 'success' | 'error';
  message: string;
};

function formatSchemaTag(value: number | null | undefined): string | null {
  return typeof value === 'number' ? `schema ${formatNumber(value)}` : null;
}

function formatFingerprintTag(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  return normalized ? `fp ${normalized.slice(0, 8)}` : null;
}

function formatSampleStateLabel(value: string | null | undefined): string | null {
  switch (value) {
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

function formatSampleQualityLabel(value: number | null | undefined): string | null {
  if (typeof value !== 'number') {
    return null;
  }
  const normalized = value <= 1 ? value : value / 100;
  return `Q ${normalized.toFixed(2)}`;
}

export function BuyOpportunityDetailPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const opportunityId = params.opportunityId ?? '';
  const workspaceQuery = readInitialQuery(location.search);
  const categoryCode = workspaceQuery.categoryCode;
  const queryClient = useQueryClient();
  const { detail, isLoading, isRefreshing, error } = useBuyOpportunityDetail(opportunityId, categoryCode);
  const recordedDetailOpenRef = useRef<string | null>(null);
  const [feedbackState, setFeedbackState] = useState<FeedbackState>({
    kind: 'idle',
    message: '在这里直接记录 contacted / purchased / not worth it，结果会回写机会池和提醒命中统计。',
  });
  const [showPurchaseOutcomeForm, setShowPurchaseOutcomeForm] = useState(false);

  const opportunity = detail?.opportunity ?? null;
  const itemDetail = detail?.itemDetail ?? null;
  const outcomeProof = detail?.outcomeProof ?? null;
  const itemId = opportunity?.itemId ?? itemDetail?.item.item_id ?? null;
  const queueTarget = buildWorkspaceLocation('/', workspaceQuery);
  const marketTarget = buildWorkspaceLocation('/market', workspaceQuery);
  const runtimeTarget = buildWorkspaceLocation('/ops/runtime', workspaceQuery);
  const itemTarget = itemId ? buildWorkspaceLocation(`/items/${itemId}`, workspaceQuery) : null;
  const matchedFields = Object.entries(opportunity?.matchedFieldValues ?? {});
  const schemaTag = formatSchemaTag(opportunity?.schemaId);
  const fingerprintTag = formatFingerprintTag(opportunity?.sampleSnapshot?.fingerprintHash);
  const sampleStateLabel = formatSampleStateLabel(opportunity?.sampleSnapshot?.sampleState);
  const sampleQualityLabel = formatSampleQualityLabel(opportunity?.sampleSnapshot?.sampleQualityScore);
  const missingSampleAttrs = opportunity?.sampleSnapshot?.missingRequiredAttrs ?? [];

  const feedbackMutation = useMutation({
    mutationFn: async (payload: BuyFeedbackRequest) => postBuyFeedback(payload),
    onSuccess: async (result, payload) => {
      const stateLabel = [result.status, result.decision].filter(Boolean).join(' · ') || payload.feedbackLabel;
      if (payload.feedbackLabel === 'purchased') {
        setShowPurchaseOutcomeForm(false);
      }
      setFeedbackState({
        kind: 'success',
        message: payload.feedbackLabel === 'purchased' ? `已回写成交：${stateLabel}，ROI 证据已进入结果漏斗。` : `已回写：${stateLabel}`,
      });
      await queryClient.invalidateQueries({ queryKey: ['buy'] });
    },
    onError: (mutationError) => {
      const message = mutationError instanceof Error ? mutationError.message : '提交失败';
      setFeedbackState({
        kind: 'error',
        message,
      });
    },
  });

  useEffect(() => {
    if (!opportunity?.id || recordedDetailOpenRef.current === opportunity.id) {
      return;
    }
    recordedDetailOpenRef.current = opportunity.id;
    void postBuyFeedback({
      opportunityId: opportunity.id,
      feedbackType: 'engagement',
      feedbackLabel: 'detail_opened',
    }).catch(() => undefined);
  }, [opportunity?.id]);

  function recordListingOpen() {
    if (!opportunity?.id) {
      return;
    }
    void postBuyFeedback({
      opportunityId: opportunity.id,
      feedbackType: 'engagement',
      feedbackLabel: 'listing_opened',
    }).catch(() => undefined);
  }

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack buy-workbench-page">
            <PageHero
              eyebrow={`${(detail?.categoryCode ?? categoryCode) || '-'} · Opportunity Detail`}
              title={opportunity?.title ?? opportunity?.itemId ?? opportunity?.itemIdRef ?? '机会详情'}
              description="把机会判断、价格基线、风险解释、提醒历史和商品证据收在同一页，先做买方决策，再决定是否继续深挖原始 listing。"
              meta={
                <>
                  <span className="soft-pill is-accent">{formatCurrency(opportunity?.currentPrice)}</span>
                  <span className="soft-pill">买入线 {formatCurrency(opportunity?.buyCeiling)}</span>
                  <span className="soft-pill">机会 {formatNumber(opportunity?.opportunityScore)}</span>
                  <span className="soft-pill">风险 {formatNumber(opportunity?.riskScore)}</span>
                </>
              }
            >
              <Link className="nav-pill" to={queueTarget}>
                返回机会队列
              </Link>
              <Link className="nav-pill" to={marketTarget}>
                返回看板
              </Link>
              <button
                className="nav-pill"
                type="button"
                onClick={() => {
                  void navigate(runtimeTarget);
                }}
              >
                打开运行后台
              </button>
              {itemTarget ? (
                <Link className="nav-pill" to={itemTarget}>
                  查看完整商品证据
                </Link>
              ) : null}
              {opportunity?.listingUrl ? (
                <a
                  className="nav-pill"
                  href={opportunity.listingUrl}
                  rel="noreferrer"
                  target="_blank"
                  onClick={recordListingOpen}
                >
                  打开原始商品
                </a>
              ) : null}
              {isRefreshing ? <span className="soft-pill">正在刷新</span> : null}
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !detail ? (
              <section className="panel">
                <p className="eyebrow">Opportunity Detail</p>
                <h2>正在汇总机会、提醒和商品证据...</h2>
                <p className="panel-subtitle">这页会一次性拉齐机会评分、风险原因、反馈历史和商品快照，避免在多个页面之间来回切。</p>
              </section>
            ) : null}

            {detail && opportunity ? (
              <section className="buy-layout">
                <div className="buy-main">
                  <article className="panel buy-detail-panel">
                    <div className="panel-header buy-panel-header">
                      <div>
                        <p className="eyebrow">Decision Summary</p>
                        <h2>买入摘要</h2>
                        <p className="panel-subtitle">先判断为什么命中、价格线是否可信、现在该采取什么动作。</p>
                      </div>
                      <span className="soft-pill">{[opportunity.status, opportunity.decision].filter(Boolean).join(' · ') || '待处理'}</span>
                    </div>

                    <div className="item-detail-fact-grid">
                      <DetailFact label="当前价" value={formatCurrency(opportunity.currentPrice)} />
                      <DetailFact label="合理价" value={formatCurrency(opportunity.fairPrice)} />
                      <DetailFact label="买入线" value={formatCurrency(opportunity.buyCeiling)} />
                      <DetailFact label="折扣" value={formatPercent((opportunity.discountRate ?? 0) * 100, 1)} />
                      <DetailFact label="机会分" value={formatNumber(opportunity.opportunityScore)} />
                      <DetailFact label="风险分" value={formatNumber(opportunity.riskScore)} />
                      <DetailFact label="首次识别" value={opportunity.firstDetectedAt ?? '-'} />
                      <DetailFact label="最近识别" value={opportunity.lastDetectedAt ?? '-'} />
                      <DetailFact label="Schema" value={schemaTag} />
                      <DetailFact label="指纹" value={fingerprintTag} />
                      <DetailFact label="基线匹配" value={opportunity.baselineMatchLevel ?? '-'} />
                      <DetailFact label="模板可用性" value={opportunity.templateAvailabilityTier ?? '-'} />
                      <DetailFact label="监控目标" value={detail.watchTarget?.targetName ?? '-'} />
                      <DetailFact label="预算上限" value={formatCurrency(detail.watchTarget?.budgetCeiling)} />
                    </div>

                    <div className="buy-detail-note-list">
                      <p>命中原因：{opportunity.explanation?.readinessSummary ?? '等待更多证据。'}</p>
                      <p>review gate：{opportunity.explanation?.reviewGateSummary ?? '-'} · spec gate：{opportunity.explanation?.specGateSummary ?? '-'}</p>
                      <p>合理价证据：{detail.baseline?.explanation?.readinessSummary ?? '当前没有额外基线解释。'}</p>
                      {schemaTag || fingerprintTag ? <p>SKU 指纹：{[schemaTag, fingerprintTag].filter(Boolean).join(' · ')}</p> : null}
                      {sampleStateLabel || sampleQualityLabel ? <p>样本状态：{[sampleStateLabel, sampleQualityLabel].filter(Boolean).join(' · ')}</p> : null}
                      {opportunity.decisionNote ? <p>最近备注：{opportunity.decisionNote}</p> : null}
                      {opportunity.feedbackSummary?.recordedAt ? (
                        <p>最近反馈：{opportunity.feedbackSummary.feedbackLabel ?? '-'} · {formatRelative(opportunity.feedbackSummary.recordedAt)}</p>
                      ) : null}
                    </div>

                    {opportunity.explanation?.missingRequiredFields?.length ? (
                      <div className="pill-row">
                        {opportunity.explanation.missingRequiredFields.map((fieldName) => (
                          <span className="soft-pill is-warning" key={fieldName}>
                            缺字段 {fieldName}
                          </span>
                        ))}
                      </div>
                    ) : null}

                    {schemaTag || fingerprintTag || sampleStateLabel || missingSampleAttrs.length ? (
                      <div className="pill-row">
                        {schemaTag ? <span className="soft-pill"><code>{schemaTag}</code></span> : null}
                        {fingerprintTag ? <span className="soft-pill"><code>{fingerprintTag}</code></span> : null}
                        {sampleStateLabel ? <span className="soft-pill">{sampleStateLabel}</span> : null}
                        {missingSampleAttrs.map((fieldName) => (
                          <span className="soft-pill is-warning" key={`sample-missing:${fieldName}`}>
                            指纹缺 {fieldName}
                          </span>
                        ))}
                      </div>
                    ) : null}

                    {matchedFields.length ? (
                      <div className="pill-row">
                        {matchedFields.map(([fieldName, value]) => (
                          <span className="soft-pill" key={fieldName}>
                            {fieldName}: {formatMaybeValue(value)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </article>

                  <article className="panel buy-detail-panel">
                    <div className="panel-header buy-panel-header">
                      <div>
                        <p className="eyebrow">Manual Feedback</p>
                        <h2>人工反馈入口</h2>
                        <p className="panel-subtitle">反馈会直接回写 opportunity 状态，并联动提醒命中统计和后续校准任务。</p>
                      </div>
                      {opportunity.feedbackSummary?.feedbackAction ? (
                        <span className="soft-pill is-accent">最近动作 {opportunity.feedbackSummary.feedbackAction}</span>
                      ) : null}
                    </div>

                    <div className="buy-feedback-actions">
                      <button
                        className="quick-pill"
                        disabled={feedbackMutation.isPending}
                        type="button"
                        onClick={() => {
                          setShowPurchaseOutcomeForm(true);
                        }}
                      >
                        已成交
                      </button>
                      <button
                        className="quick-pill is-active"
                        disabled={feedbackMutation.isPending}
                        type="button"
                        onClick={() => {
                          setFeedbackState({ kind: 'idle', message: '提交中...' });
                          feedbackMutation.mutate({
                            opportunityId,
                            feedbackLabel: 'contacted',
                            linkToAlertCandidate: true,
                          });
                        }}
                      >
                        感兴趣
                      </button>
                      <button
                        className="quick-pill"
                        disabled={feedbackMutation.isPending}
                        type="button"
                        onClick={() => {
                          setFeedbackState({ kind: 'idle', message: '提交中...' });
                          feedbackMutation.mutate({
                            opportunityId,
                            feedbackLabel: 'not_worth_it',
                          });
                        }}
                      >
                        不感兴趣
                      </button>
                    </div>

                    <p className={`buy-feedback-result ${feedbackState.kind === 'error' ? 'is-error' : feedbackState.kind === 'success' ? 'is-success' : ''}`}>
                      {feedbackState.message}
                    </p>
                    {showPurchaseOutcomeForm ? (
                      <PurchaseOutcomeForm
                        buyCeiling={opportunity.buyCeiling}
                        currentPrice={opportunity.currentPrice}
                        fairPrice={opportunity.fairPrice}
                        isPending={feedbackMutation.isPending}
                        onCancel={() => {
                          setShowPurchaseOutcomeForm(false);
                        }}
                        onSubmit={(outcome) => {
                          setFeedbackState({ kind: 'idle', message: '正在记录成交和 ROI 证据...' });
                          feedbackMutation.mutate({
                            opportunityId,
                            feedbackLabel: 'purchased',
                            purchasePrice: outcome.purchasePrice,
                            expectedResalePrice: outcome.expectedResalePrice,
                            feedbackNote: outcome.feedbackNote,
                          });
                        }}
                      />
                    ) : null}
                  </article>

                  <article className="panel buy-detail-panel">
                    <div className="panel-header buy-panel-header">
                      <div>
                        <p className="eyebrow">Listing Evidence</p>
                        <h2>当前商品与历史快照</h2>
                        <p className="panel-subtitle">这里保留买方判断需要的核心证据；更细的原始响应可以继续跳到完整商品页。</p>
                      </div>
                    </div>

                    {itemDetail ? (
                      <>
                        {(itemDetail.item.image_urls ?? []).length ? (
                          <div className="item-detail-image-grid">
                            {(itemDetail.item.image_urls ?? []).map((imageUrl) => (
                              <img alt={itemDetail.item.title} className="item-detail-image" key={imageUrl} src={imageUrl} />
                            ))}
                          </div>
                        ) : null}

                        <div className="item-detail-fact-grid">
                          <DetailFact label="商品 ID" value={itemDetail.item.item_id} />
                          <DetailFact label="标题" value={itemDetail.item.title} />
                          <DetailFact label="地区" value={itemDetail.item.region} />
                          <DetailFact label="发布时间" value={itemDetail.item.publish_time ?? '-'} />
                          <DetailFact label="首次入库" value={itemDetail.item.first_seen_at ?? '-'} />
                          <DetailFact label="最近看到" value={itemDetail.item.last_seen_at ?? '-'} />
                          <DetailFact label="品牌" value={itemDetail.item.normalized_brand} />
                          <DetailFact label="型号" value={itemDetail.item.normalized_model} />
                          <DetailFact label="芯片" value={itemDetail.item.normalized_chip} />
                          <DetailFact label="内存" value={formatStorage(itemDetail.item.normalized_memory_gb, 'GB')} />
                          <DetailFact label="硬盘" value={formatStorage(itemDetail.item.normalized_storage_gb, 'GB')} />
                          <DetailFact label="来源关键词" value={itemDetail.item.source_keyword} />
                        </div>

                        {itemDetail.spec ? (
                          <div className="item-detail-fact-grid compact">
                            <DetailFact label="Spec 状态" value={itemDetail.spec.status} />
                            <DetailFact label="Spec 置信度" value={formatMaybeNumber(itemDetail.spec.confidence)} />
                            <DetailFact label="抽取方式" value={itemDetail.spec.extractor_type} />
                            <DetailFact label="产品线" value={itemDetail.spec.product_line} />
                            <DetailFact label="标准型号" value={itemDetail.spec.model_name} />
                            <DetailFact label="代际" value={itemDetail.spec.generation} />
                          </div>
                        ) : null}

                        <div className="pill-row">
                          {(itemDetail.item.condition_tags ?? []).map((tag) => (
                            <span className="soft-pill" key={`condition:${tag}`}>{tag}</span>
                          ))}
                          {(itemDetail.spec?.edition_tags ?? []).map((tag) => (
                            <span className="soft-pill" key={`edition:${tag}`}>{tag}</span>
                          ))}
                        </div>

                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>抓取时间</th>
                                <th>价格</th>
                                <th>地区</th>
                                <th>页码</th>
                                <th>关键词</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(itemDetail.snapshots ?? []).length ? (
                                (itemDetail.snapshots ?? []).map((snapshot, index) => (
                                  <tr key={`${snapshot.snapshot_at ?? '-'}:${index}`}>
                                    <td>{snapshot.snapshot_at ?? '-'}</td>
                                    <td>{formatCurrency(snapshot.price)}</td>
                                    <td>{snapshot.region ?? '-'}</td>
                                    <td>{formatMaybeValue(snapshot.extra_json?.page_number)}</td>
                                    <td>{formatMaybeValue(snapshot.extra_json?.source_keyword)}</td>
                                  </tr>
                                ))
                              ) : (
                                <tr>
                                  <td className="empty-cell" colSpan={5}>
                                    还没有抓取快照。
                                  </td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </>
                    ) : (
                      <p className="panel-subtitle">当前没有更多商品详情，说明机会已经存在，但 listing 证据还没同步完整。</p>
                    )}
                  </article>
                </div>

                <aside className="buy-side">
                  <article className="panel buy-side-panel">
                    <p className="eyebrow">Outcome Proof</p>
                    <h3>结果证据</h3>
                    <div className="mini-card">
                      <strong>
                        提醒 {formatNumber(outcomeProof?.alertEventCount)} · 打开 {formatNumber(outcomeProof?.openFeedbackCount)} · 联系 {formatNumber(outcomeProof?.contactFeedbackCount)} · 成交 {formatNumber(outcomeProof?.purchaseFeedbackCount)}
                      </strong>
                      <small>{outcomeProof?.hasPurchaseEvidence ? '已出现成交反馈证据。' : '还没有成交反馈证据。'}</small>
                      {outcomeProof?.hasRoiEvidence ? (
                        <>
                          <small>
                            买入价 {formatCurrency(outcomeProof.purchasePrice)} · 预估转售价 {formatCurrency(outcomeProof.expectedResalePrice)}
                          </small>
                          <small>
                            预估利润 {formatCurrency(outcomeProof.estimatedProfit)} · ROI {formatPercent((outcomeProof.estimatedRoiRate ?? 0) * 100, 1)}
                          </small>
                        </>
                      ) : (
                        <small>尚未填写 purchasePrice / expectedResalePrice，暂时无法估算 ROI。</small>
                      )}
                    </div>
                  </article>

                  <article className="panel buy-side-panel">
                    <p className="eyebrow">Baseline Evidence</p>
                    <h3>合理价证据</h3>
                    {detail.baseline ? (
                      <>
                        <div className="mini-card">
                          <strong>{detail.baseline.baselineKey}</strong>
                          <small>样本 {formatNumber(detail.baseline.sampleSize)} · 置信度 {formatPercent((detail.baseline.confidence ?? 0) * 100, 1)}{detail.baseline.schemaId ? ` · schema ${formatNumber(detail.baseline.schemaId)}` : ''}</small>
                          <small>合理价 {formatCurrency(detail.baseline.fairPrice)} · 买入线 {formatCurrency(detail.baseline.buyCeiling)}</small>
                        </div>
                        <p className="panel-subtitle">{detail.baseline.explanation?.readinessSummary ?? '当前没有更多基线解释。'}</p>
                      </>
                    ) : (
                      <p className="panel-subtitle">当前机会还没有可展示的价格基线。</p>
                    )}
                  </article>

                  <article className="panel buy-side-panel">
                    <p className="eyebrow">Risk Review</p>
                    <h3>风险解释</h3>
                    {detail.risks?.length ? detail.risks.map((risk) => (
                      <div className="mini-card" key={risk.id}>
                        <strong>{risk.riskCode}</strong>
                        <small>{risk.riskLevel ?? '-'}</small>
                        <small>{risk.detail ?? '暂无额外说明。'}</small>
                      </div>
                    )) : <p className="panel-subtitle">当前没有额外风险命中，仍建议结合卖家成色和地区自行复核。</p>}
                  </article>

                  <article className="panel buy-side-panel">
                    <p className="eyebrow">Alert History</p>
                    <h3>提醒与命中原因</h3>
                    {detail.alertEvents?.length ? detail.alertEvents.map((alert) => (
                      <div className="mini-card" key={alert.id}>
                        <strong>{alert.status ?? '-'}</strong>
                        <small>{alert.alertChannel ?? '-'} · {formatRelative(alert.sentAt)}</small>
                        <small>{alert.alertReason ?? '暂无提醒原因。'}</small>
                      </div>
                    )) : <p className="panel-subtitle">这条机会还没有生成提醒事件。</p>}
                  </article>

                  <article className="panel buy-side-panel">
                    <p className="eyebrow">Feedback History</p>
                    <h3>反馈历史</h3>
                    {detail.feedbackEntries?.length ? detail.feedbackEntries.map((entry) => (
                      <div className="mini-card" key={entry.id}>
                        <strong>{entry.feedbackLabel ?? '-'}</strong>
                        <small>{entry.feedbackType ?? '-'} · 操作者 {entry.operatorId ?? '-'}</small>
                        <small>{entry.feedbackNote ?? '暂无备注。'}</small>
                      </div>
                    )) : <p className="panel-subtitle">还没有写入人工反馈。</p>}
                  </article>
                </aside>
              </section>
            ) : null}
          </div>
        </div>
      </main>
    </AppFrame>
  );
}

function DetailFact(props: { label: string; value: string | null | undefined }) {
  return (
    <div className="item-detail-fact">
      <dt>{props.label}</dt>
      <dd>{props.value || '-'}</dd>
    </div>
  );
}

function formatStorage(value: number | null | undefined, unit: string) {
  return typeof value === 'number' ? `${formatNumber(value)} ${unit}` : '-';
}

function formatMaybeNumber(value: number | null | undefined) {
  return typeof value === 'number' ? String(value) : '-';
}

function formatMaybeValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  return '-';
}
