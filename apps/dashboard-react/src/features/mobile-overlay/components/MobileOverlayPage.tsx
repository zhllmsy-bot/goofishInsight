import { useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { TerminalScreen } from '../../../shared/components/TerminalScreen';
import { PageHero } from '../../../shared/components/PageHero';
import { formatCurrency, formatNumber, formatPercent } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation, readInitialQuery } from '../../dashboard/lib/urlState';
import { useOverlayHealthz, useOverlayAnalysis } from '../hooks/useMobileOverlay';
import type { OverlayAnalyzeRequest, OverlayDomainAnalysis, OverlayOcrLine } from '../types/mobileOverlay';

import '../../dashboard/styles/dashboard.css';
import '../styles/mobile-overlay.css';

const DECISION_STATUS_LABELS: Record<string, string> = {
  strong_yes: '强烈推荐',
  yes: '可以收货',
  watch: '继续观察',
  no: '不建议',
  needs_review: '需要人工判断',
};

function decisionTone(status: string): string {
  if (status === 'strong_yes') return 'strong_yes';
  if (status === 'yes') return 'yes';
  if (status === 'watch') return 'watch';
  if (status === 'no') return 'no';
  return 'needs_review';
}

export function MobileOverlayPage() {
  const location = useLocation();
  const workspaceQuery = useMemo(() => readInitialQuery(location.search), [location.search]);
  const { healthz, isLoading: healthzLoading } = useOverlayHealthz();
  const { analysis, isAnalyzing, error: analysisError, submitAnalysis } = useOverlayAnalysis();

  const [ocrText, setOcrText] = useState('');
  const [sourcePackage, setSourcePackage] = useState('');
  const [screenWidth, setScreenWidth] = useState('');
  const [screenHeight, setScreenHeight] = useState('');

  const vlm = healthz?.vlm;
  const vlmEnabled = vlm?.enabled ?? false;
  const vlmWorkerAlive = vlm?.queue?.worker_alive ?? false;

  const dashboardTarget = useMemo(
    () => buildWorkspaceLocation('/', workspaceQuery),
    [workspaceQuery],
  );
  const runtimeTarget = useMemo(
    () => buildWorkspaceLocation('/runtime', workspaceQuery),
    [workspaceQuery],
  );

  async function handleAnalyze() {
    const lines: OverlayOcrLine[] = ocrText
      .split('\n')
      .filter((line) => line.trim().length > 0)
      .map((text) => ({
        text: text.trim(),
        left: null,
        top: null,
        right: null,
        bottom: null,
      }));

    const request: OverlayAnalyzeRequest = {
      source_package: sourcePackage || null,
      screen_width: screenWidth ? Number(screenWidth) : null,
      screen_height: screenHeight ? Number(screenHeight) : null,
      captured_at: null,
      screenshot_base64: null,
      ocr_lines: lines,
    };

    await submitAnalysis(request);
  }

  const ocrSummary = analysis?.ocr_summary;
  const decision = analysis?.decision;
  const match = analysis?.match;
  const alternatives = analysis?.alternatives ?? [];

  return (
    <TerminalScreen>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack">
            <PageHero
              eyebrow="Mobile Overlay"
              title="移动端辅助分析"
              description="把手机截图 OCR 文本送进后端分析管线，实时匹配品类、价格带和买入决策。这个页面是辅助面，不挤占主 dashboard。"
              meta={
                <>
                  <span className="soft-pill">{vlmEnabled ? 'VLM 已启用' : 'VLM 未启用'}</span>
                  {vlmEnabled ? (
                    <span className={`soft-pill ${vlmWorkerAlive ? 'is-accent' : 'is-warn'}`}>
                      {vlmWorkerAlive ? 'Worker 在线' : 'Worker 离线'}
                    </span>
                  ) : null}
                  {vlm?.queue ? (
                    <span className="soft-pill">
                      队列 {formatNumber(vlm.queue.pending_jobs)} · 完成 {formatNumber(vlm.queue.completed_jobs)}
                    </span>
                  ) : null}
                </>
              }
            >
              <Link className="nav-pill" to={dashboardTarget}>
                回到看板首页
              </Link>
              <Link className="nav-pill" to={runtimeTarget}>
                打开运行控制
              </Link>
            </PageHero>

            {healthzLoading && !healthz ? (
              <section className="panel">
                <p className="eyebrow">Healthz</p>
                <h2>正在检查 Overlay 服务状态...</h2>
                <p className="panel-subtitle">首轮会拉取 VLM 运行状态和队列信息。</p>
              </section>
            ) : null}

            <section className="panel overlay-status-panel">
              <div className="overlay-status-grid">
                <article className="overlay-status-card">
                  <p className="eyebrow">VLM 状态</p>
                  <strong>{vlmEnabled ? '已启用' : '未启用'}</strong>
                  <p className="panel-subtitle">模型 {vlm?.model ?? '-'}</p>
                </article>
                <article className="overlay-status-card">
                  <p className="eyebrow">Worker</p>
                  <strong>{vlmWorkerAlive ? '在线' : '离线'}</strong>
                  <p className="panel-subtitle">
                    待处理 {formatNumber(vlm?.queue?.pending_jobs)} · 失败 {formatNumber(vlm?.queue?.failed_jobs)}
                  </p>
                </article>
                <article className="overlay-status-card">
                  <p className="eyebrow">已完成</p>
                  <strong>{formatNumber(vlm?.queue?.completed_jobs)}</strong>
                  <p className="panel-subtitle">累计分析任务</p>
                </article>
              </div>
            </section>

            <section className="overlay-layout">
              <div className="overlay-main">
                <article className="panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">OCR Input</p>
                      <h2>OCR 文本输入</h2>
                      <p className="panel-subtitle">
                        把手机截图 OCR 识别出的文字按行粘贴，每行一条。后端会自动提取标题候选、价格和品类匹配。
                      </p>
                    </div>
                  </div>

                  <div className="overlay-form-field">
                    <label>OCR 行文本（每行一条）</label>
                    <textarea
                      aria-label="OCR 行文本"
                      placeholder={"佳明 fenix 7X Pro Solar\n¥3,299\nGarmin 佳明 fenix7X 太阳能\n到手价3299元"}
                      value={ocrText}
                      onChange={(event) => {
                        setOcrText(event.target.value);
                      }}
                    />
                  </div>

                  <div className="overlay-metrics-row" style={{ marginTop: 12 }}>
                    <div className="overlay-form-field">
                      <label>来源包名</label>
                      <input
                        aria-label="来源包名"
                        placeholder="com.xianyu.mobile"
                        value={sourcePackage}
                        onChange={(event) => {
                          setSourcePackage(event.target.value);
                        }}
                      />
                    </div>
                    <div className="overlay-form-field">
                      <label>屏幕宽度</label>
                      <input
                        aria-label="屏幕宽度"
                        placeholder="1080"
                        type="number"
                        value={screenWidth}
                        onChange={(event) => {
                          setScreenWidth(event.target.value);
                        }}
                      />
                    </div>
                    <div className="overlay-form-field">
                      <label>屏幕高度</label>
                      <input
                        aria-label="屏幕高度"
                        placeholder="2400"
                        type="number"
                        value={screenHeight}
                        onChange={(event) => {
                          setScreenHeight(event.target.value);
                        }}
                      />
                    </div>
                  </div>

                  <div className="overlay-submit-row" style={{ marginTop: 16 }}>
                    <button
                      className="overlay-submit-button"
                      disabled={isAnalyzing || !ocrText.trim()}
                      type="button"
                      onClick={() => {
                        void handleAnalyze();
                      }}
                    >
                      {isAnalyzing ? '分析中...' : '提交分析'}
                    </button>
                    {isAnalyzing ? <span className="soft-pill">正在匹配品类与价格带</span> : null}
                  </div>
                </article>

                {analysisError ? <div className="error-banner">{analysisError}</div> : null}

                {ocrSummary ? (
                  <article className="overlay-result-card">
                    <div className="overlay-result-header">
                      <div>
                        <p className="eyebrow">OCR Summary</p>
                        <h3>OCR 识别结果</h3>
                      </div>
                      <span className="soft-pill">{formatNumber(ocrSummary.line_count)} 行</span>
                    </div>

                    <div className="overlay-metrics-row">
                      <div className="overlay-metric">
                        <small>标题候选</small>
                        <strong>{ocrSummary.title_candidate ?? '-'}</strong>
                      </div>
                      <div className="overlay-metric">
                        <small>来源</small>
                        <strong>{ocrSummary.title_candidate_source}</strong>
                      </div>
                      <div className="overlay-metric">
                        <small>识别价格</small>
                        <strong>{ocrSummary.listing_price != null ? formatCurrency(ocrSummary.listing_price) : '-'}</strong>
                      </div>
                      <div className="overlay-metric">
                        <small>价格原文</small>
                        <strong>{ocrSummary.price_source_text ?? '-'}</strong>
                      </div>
                    </div>

                    {ocrSummary.text_excerpt ? (
                      <div>
                        <p className="eyebrow">文本摘要</p>
                        <p style={{ fontSize: 13, color: '#334155', lineHeight: 1.7, margin: 0 }}>
                          {ocrSummary.text_excerpt}
                        </p>
                      </div>
                    ) : null}
                  </article>
                ) : null}

                {decision ? (
                  <div className={`overlay-decision-banner ${decisionTone(decision.status)}`}>
                    <h3>{DECISION_STATUS_LABELS[decision.status] ?? decision.status}</h3>
                    <p>{decision.summary}</p>
                    {decision.risk_flags.length ? (
                      <div className="overlay-risk-flags">
                        {decision.risk_flags.map((flag) => (
                          <span className="overlay-risk-flag" key={flag}>{flag}</span>
                        ))}
                      </div>
                    ) : null}
                    <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                      <span className="soft-pill">
                        快速收货 {decision.quick_flip_ok ? '可行' : '不可行'}
                      </span>
                    </div>
                  </div>
                ) : null}

                {match ? (
                  <OverlayDomainMatchCard analysis={match} />
                ) : null}

                {alternatives.length > 0 && match ? (
                  <article className="panel">
                    <div className="panel-header">
                      <div>
                        <p className="eyebrow">Alternatives</p>
                        <h2>其他匹配候选</h2>
                      </div>
                      <span className="soft-pill">{alternatives.length} 个</span>
                    </div>
                    <div className="overlay-alt-list">
                      {alternatives
                        .filter((alt) => match && alt.business_domain !== match.business_domain)
                        .map((alt) => (
                          <OverlayAltCard key={alt.business_domain} analysis={alt} />
                        ))}
                    </div>
                  </article>
                ) : null}
              </div>

              <aside className="overlay-side">
                <article className="overlay-side-panel">
                  <p className="eyebrow">VLM Runtime</p>
                  <h3>VLM 运行状态</h3>
                  {vlm ? (
                    <div className="overlay-vlm-detail">
                      <div><span>启用</span> <strong>{vlm.enabled ? '是' : '否'}</strong></div>
                      <div><span>模型</span> <strong>{vlm.model ?? '-'}</strong></div>
                      <div><span>Base URL</span> <strong>{vlm.base_url ?? '-'}</strong></div>
                      <div><span>Thinking</span> <strong>{vlm.thinking_enabled ? '已开启' : '未开启'}</strong></div>
                      <div><span>Worker</span> <strong>{vlm.queue.worker_alive ? '在线' : '离线'}</strong></div>
                      <div><span>待处理</span> <strong>{formatNumber(vlm.queue.pending_jobs)}</strong></div>
                      <div><span>已完成</span> <strong>{formatNumber(vlm.queue.completed_jobs)}</strong></div>
                      <div><span>失败</span> <strong>{formatNumber(vlm.queue.failed_jobs)}</strong></div>
                      {vlm.queue.active_job_id ? (
                        <div><span>当前任务</span> <strong>{vlm.queue.active_job_id.slice(0, 8)}</strong></div>
                      ) : null}
                      {vlm.queue.active_seconds != null ? (
                        <div><span>执行时间</span> <strong>{vlm.queue.active_seconds.toFixed(1)}s</strong></div>
                      ) : null}
                    </div>
                  ) : (
                    <p className="panel-subtitle">VLM 状态不可用，请检查后端服务是否启动。</p>
                  )}
                </article>

                {analysis?.vlm_summary && !analysis.vlm_summary.error ? (
                  <article className="overlay-side-panel">
                    <p className="eyebrow">VLM Analysis</p>
                    <h3>VLM 分析结果</h3>
                    <div className="overlay-vlm-detail">
                      <div><span>标题候选</span> <strong>{analysis.vlm_summary.title_candidate ?? '-'}</strong></div>
                      <div><span>品牌</span> <strong>{analysis.vlm_summary.brand_hint ?? '-'}</strong></div>
                      <div><span>品类</span> <strong>{analysis.vlm_summary.business_domain_hint ?? '-'}</strong></div>
                      <div><span>型号</span> <strong>{analysis.vlm_summary.model_hint ?? '-'}</strong></div>
                      <div><span>规格</span> <strong>{analysis.vlm_summary.spec_hint ?? '-'}</strong></div>
                      <div><span>价格</span> <strong>{analysis.vlm_summary.price_hint ?? '-'}</strong></div>
                      <div><span>置信度</span> <strong>{analysis.vlm_summary.confidence != null ? formatPercent(analysis.vlm_summary.confidence * 100, 1) : '-'}</strong></div>
                      <div><span>理由</span> <strong>{analysis.vlm_summary.reason ?? '-'}</strong></div>
                    </div>
                  </article>
                ) : null}

                {analysis?.vlm_summary?.error ? (
                  <article className="overlay-side-panel" style={{ borderColor: '#fecaca', background: '#fef2f2' }}>
                    <p className="eyebrow">VLM Error</p>
                    <h3>VLM 分析失败</h3>
                    <p style={{ fontSize: 12, color: '#b91c1c', margin: 0 }}>{analysis.vlm_summary.error}</p>
                  </article>
                ) : null}
              </aside>
            </section>
          </div>
        </div>
      </main>
    </TerminalScreen>
  );
}

function OverlayDomainMatchCard({ analysis }: { analysis: OverlayDomainAnalysis }) {
  const pricing = analysis.pricing;
  const trend = analysis.trend;

  return (
    <article className="overlay-result-card">
      <div className="overlay-result-header">
        <div>
          <p className="eyebrow">Best Match</p>
          <h3>{analysis.domain_label}</h3>
          <p className="panel-subtitle">
            {analysis.task_display_name} · 匹配视图 {analysis.matched_view} · 分数 {formatNumber(analysis.score)}
          </p>
        </div>
        <span className={`soft-pill ${pricing.price_position === 'safe' ? 'is-accent' : pricing.price_position === 'target' ? 'is-accent' : pricing.price_position === 'watch' ? 'is-warn' : ''}`}>
          {pricing.price_position ?? '-'}
        </span>
      </div>

      <div className="overlay-metrics-row">
        <div className="overlay-metric">
          <small>当前价</small>
          <strong>{formatCurrency(pricing.listing_price)}</strong>
        </div>
        <div className="overlay-metric">
          <small>合理价</small>
          <strong>{formatCurrency(pricing.fair_price)}</strong>
        </div>
        <div className="overlay-metric">
          <small>安全收货价</small>
          <strong>{formatCurrency(pricing.safe_buy_price)}</strong>
        </div>
        <div className="overlay-metric">
          <small>目标上限</small>
          <strong>{formatCurrency(pricing.target_buy_ceiling)}</strong>
        </div>
      </div>

      <div className="overlay-metrics-row">
        <div className="overlay-metric">
          <small>预期利润率</small>
          <strong>{pricing.expected_profit_margin_pct != null ? formatPercent(pricing.expected_profit_margin_pct, 1) : '-'}</strong>
        </div>
        <div className="overlay-metric">
          <small>可靠性</small>
          <strong>{pricing.reliability_tier ?? '-'}</strong>
        </div>
        <div className="overlay-metric">
          <small>样本量</small>
          <strong>{formatNumber(pricing.seller_sample_count)}</strong>
        </div>
        <div className="overlay-metric">
          <small>可操作</small>
          <strong>{pricing.is_actionable ? '是' : '否'}</strong>
        </div>
      </div>

      {trend ? (
        <div className="overlay-metrics-row">
          <div className="overlay-metric">
            <small>最新收盘</small>
            <strong>{formatCurrency(trend.latest_close)}</strong>
          </div>
          <div className="overlay-metric">
            <small>涨跌</small>
            <strong>{trend.change_label ?? '-'}</strong>
          </div>
          <div className="overlay-metric">
            <small>波动</small>
            <strong>{trend.volatility_label ?? '-'}</strong>
          </div>
          <div className="overlay-metric">
            <small>趋势质量</small>
            <strong>{trend.trend_quality_ok ? 'OK' : '一般'}</strong>
          </div>
        </div>
      ) : null}

      {pricing.label ? (
        <p className="panel-subtitle">
          匹配 {pricing.label} · {pricing.spec_label ?? '-'} · 上架 {formatNumber(pricing.listing_count)} 条
        </p>
      ) : null}
    </article>
  );
}

function OverlayAltCard({ analysis }: { analysis: OverlayDomainAnalysis }) {
  const pricing = analysis.pricing;

  return (
    <div className="overlay-alt-card">
      <h4>{analysis.domain_label}</h4>
      <div className="overlay-alt-metrics">
        <span className="soft-pill">分数 {formatNumber(analysis.score)}</span>
        <span className="soft-pill">当前 {formatCurrency(pricing.listing_price)}</span>
        <span className="soft-pill">合理 {formatCurrency(pricing.fair_price)}</span>
        <span className={`soft-pill ${pricing.price_position === 'safe' ? 'is-accent' : ''}`}>
          {pricing.price_position ?? '-'}
        </span>
      </div>
    </div>
  );
}