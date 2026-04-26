import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderDashboardApp } from '../../../test/renderApp';
import { requestBodyText, requestUrl } from '../../../test/fetchMock';

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('BuyWorkbenchPage', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('keeps workspace filters, writes feedback, and provides dashboard return path', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/buy/opportunities') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          summary: {
            opportunityCount: 1,
            baselineCount: 0,
            watchTargetCount: 0,
            feedbackCount: 0,
            calibrationRecommendationCount: 0,
          },
          outcomeFunnel: {
            alertedOpportunityCount: 1,
            openedOpportunityCount: 0,
            contactedOpportunityCount: 0,
            purchasedOpportunityCount: 0,
            roiEvidenceCount: 0,
            alertToOpenRate: 0,
            alertToContactRate: 0,
            openToContactRate: 0,
            contactToPurchaseRate: 0,
          },
          dataValue: {
            categoryCode: 'apple_computer',
            generatedAt: '2026-04-24T15:30:00+00:00',
            summary: {
              itemCount: 46081,
              activeItemCount: 37516,
              pricedItemCount: 46081,
              snapshotCount: 74572,
              specItemCount: 4085,
              completeSpecItemCount: 51,
              baselineCount: 2241,
              latestBaselineCount: 650,
              latestBaselineDate: '2026-04-24',
              opportunityCount: 4938,
              openOpportunityCount: 941,
              guidanceReadyOpportunityCount: 943,
              referenceLimitedOpportunityCount: 3992,
              alertEventCount: 50,
              alertedOpportunityCount: 50,
              feedbackCount: 0,
              openedOpportunityCount: 0,
              contactedOpportunityCount: 0,
              purchasedOpportunityCount: 0,
              roiEvidenceCount: 0,
              specCoverageRate: 0.0887,
              completeSpecCoverageRate: 0.0011,
              opportunityYieldRate: 0.1072,
              openOpportunityRate: 0.1906,
              guidanceReadyRate: 0.1909,
              alertCoverageRate: 0.0531,
              feedbackCoverageRate: 0,
              purchaseProofRate: 0,
              roiProofRate: 0,
              dataValueScore: 17.8,
            },
            diagnosis: {
              stage: 'value_unproven',
              severity: 'critical',
              statusLabel: '资源消耗态',
              summary: '数据已经能生成价格资产和机会资产，但没有任何人工反馈、成交或 ROI 证据。',
              nextBestAction: '暂停扩品类采集，把 OPEN 机会转成人工判断、联系、成交与 ROI 证据。',
            },
            stages: [
              { key: 'inventory', label: '有效商品库存', count: 46081, denominator: 46081, conversionRate: 1, leakageCount: 0 },
              { key: 'feedback', label: '人工反馈', count: 0, denominator: 4938, conversionRate: 0, leakageCount: 4938 },
              { key: 'roi', label: 'ROI 证据', count: 0, denominator: 0, conversionRate: 0, leakageCount: 0 },
            ],
            categoryBreakdown: [
              {
                categoryCode: 'apple_computer',
                itemCount: 46081,
                openOpportunityCount: 941,
                feedbackCoverageRate: 0,
                utilizationScore: 17.8,
              },
            ],
            recommendations: [
              {
                priority: 'P0',
                title: '从采集优先切换到机会消化优先',
                reason: '当前 OPEN 机会有 941 条，但反馈数是 0。',
                action: '每天先处理 TOP 20 OPEN 机会，并把打开、联系、不值得、已成交全部回写。',
              },
            ],
          },
          dailyOpportunityPack: {
            generatedAt: '2026-04-24T15:30:00+00:00',
            summary: {
              targetProcessingCount: 20,
              packOpportunityCount: 1,
              openBacklogCount: 941,
              ungroupedOpenCount: 940,
              feedbackCount: 0,
              contactedOpportunityCount: 0,
              purchasedOpportunityCount: 0,
              roiEvidenceCount: 0,
              feedbackCoverageRate: 0,
              operatingMode: 'opportunity_digest_first',
              northStar: '把 OPEN 机会消化成反馈、联系、成交和 ROI 证据',
            },
            groups: [
              {
                key: 'act_now',
                label: '立即看',
                recommendedAction: '今天先打开原始商品，确认实物、卖家和可交易性，再标记已联系或不值得。',
                count: 1,
                tasks: [
                  {
                    rank: 1,
                    groupKey: 'act_now',
                    groupLabel: '立即看',
                    recommendedAction: '今天先打开原始商品，确认实物、卖家和可交易性，再标记已联系或不值得。',
                    reason: '机会分 68.0 · 低于公平价 ¥601',
                    slaLabel: '今日必须给出联系/跳过判断',
                    riskFlags: [],
                    valueSignals: ['机会分 68.0', '低于公平价 ¥601'],
                    opportunity: {
                      id: 'opp-1',
                      itemIdRef: 'item-1',
                      title: 'MacBook Pro M5 Pro 16G 512G',
                      status: 'OPEN',
                      decision: null,
                      currentPrice: 6999,
                      fairPrice: 7600,
                      buyCeiling: 7200,
                      opportunityScore: 68,
                      riskScore: 12,
                      explanation: {
                        readinessSummary: '可行动',
                        reviewGateSummary: '通过',
                        specGateSummary: '通过',
                      },
                      schemaId: 42,
                      sampleSnapshot: {
                        schemaId: 42,
                        sampleState: 'eligible',
                        fingerprintHash: '1234abcdeffedcba',
                      },
                      feedbackSummary: {
                        feedbackLabel: 'contacted',
                        recordedAt: '2026-04-24T15:00:00+00:00',
                      },
                      specContract: { status: 'complete' },
                    },
                  },
                ],
              },
              {
                key: 'negotiate',
                label: '可砍价',
                recommendedAction: '用公平价和买入线上限做议价锚点。',
                count: 0,
                tasks: [],
              },
            ],
            marketIntel: [
              {
                baselineKey: 'template:apple',
                sampleSize: 42,
                fairPrice: 7600,
                buyCeiling: 7200,
                confidence: 0.9,
                reason: '可作为今日联系和议价的价格锚点。',
              },
            ],
          },
          opportunities: [
            {
              id: 'opp-1',
              itemIdRef: 'item-1',
              title: 'MacBook Pro M5 Pro 16G 512G',
              status: 'OPEN',
              decision: null,
              currentPrice: 6999,
              fairPrice: 7600,
              buyCeiling: 7200,
              opportunityScore: 68,
              riskScore: 12,
              explanation: {
                readinessSummary: '可行动',
                reviewGateSummary: '通过',
                specGateSummary: '通过',
              },
              schemaId: 42,
              sampleSnapshot: {
                schemaId: 42,
                sampleState: 'eligible',
                fingerprintHash: '1234abcdeffedcba',
              },
              feedbackSummary: {
                feedbackLabel: 'contacted',
                recordedAt: '2026-04-24T15:00:00+00:00',
              },
              specContract: { status: 'complete' },
            },
          ],
          baselines: [],
          watchTargets: [],
        });
      }

      if (url.pathname === '/api/buy/feedback' && init?.method === 'POST') {
        return jsonResponse({
          opportunityId: 'opp-1',
          feedbackLabel: 'contacted',
          feedbackType: 'decision',
          status: 'CONTACTED',
          decision: 'contacted',
          linkedAlertCandidate: true,
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp(
      '/?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '今日机会' })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '打开全局搜索' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '数据资产利用率' })).toBeInTheDocument();
    });
    expect(screen.getByText('资源消耗态')).toBeInTheDocument();
    expect(screen.getByText(/从采集优先切换到机会消化优先/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '今日机会任务包' })).toBeInTheDocument();
    expect(screen.getByText(/把 OPEN 机会消化成反馈、联系、成交和 ROI 证据/)).toBeInTheDocument();
    expect(screen.getByText(/OPEN backlog 941 · 未入队 940/)).toBeInTheDocument();
    expect(screen.getByText('schema 42')).toBeInTheDocument();
    expect(screen.getByText('fp 1234abcd')).toBeInTheDocument();
    expect(screen.getByText(/反馈 contacted/)).toBeInTheDocument();

    expect(screen.getByRole('link', { name: '前往市场大盘' })).toHaveAttribute(
      'href',
      '/market?category_code=apple_computer&product_label=MacBook+Pro+%2F+M5&spec_label=16G+%2F+512G&pricing_scope=all&pricing_freshness_days=30',
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Watch opportunity' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Watch opportunity' }));

    await waitFor(() => {
      expect(screen.getAllByText(/已回写：CONTACTED · contacted/).length).toBeGreaterThan(0);
    });

    const postCall = fetchMock.mock.calls.find(([, callInit]) => callInit?.method === 'POST');
    expect(postCall).toBeDefined();
    const payload = JSON.parse(requestBodyText(postCall?.[1]?.body)) as Record<string, unknown>;
    expect(payload.opportunityId).toBe('opp-1');
    expect(payload.feedbackLabel).toBe('contacted');
    expect(payload.linkToAlertCandidate).toBe(true);
  });

  it('records purchase outcome evidence from the workbench', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/buy/opportunities') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          summary: {
            opportunityCount: 1,
            baselineCount: 1,
            watchTargetCount: 1,
            feedbackCount: 0,
            calibrationRecommendationCount: 0,
          },
          outcomeFunnel: {
            alertedOpportunityCount: 1,
            openedOpportunityCount: 0,
            contactedOpportunityCount: 0,
            purchasedOpportunityCount: 0,
            roiEvidenceCount: 0,
            alertToOpenRate: 0,
            alertToContactRate: 0,
            openToContactRate: 0,
            contactToPurchaseRate: 0,
          },
          opportunities: [
            {
              id: 'opp-1',
              itemIdRef: 'item-1',
              title: 'MacBook Pro M5 Pro 16G 512G',
              status: 'OPEN',
              decision: null,
              currentPrice: 6999,
              fairPrice: 7600,
              buyCeiling: 7200,
              opportunityScore: 88,
              riskScore: 8,
              explanation: {
                readinessSummary: '可行动',
                reviewGateSummary: '通过',
                specGateSummary: '通过',
              },
              specContract: { status: 'complete' },
            },
          ],
          baselines: [],
          watchTargets: [],
        });
      }

      if (url.pathname === '/api/buy/feedback' && init?.method === 'POST') {
        const payload = JSON.parse(requestBodyText(init.body)) as Record<string, unknown>;
        expect(payload).toMatchObject({
          opportunityId: 'opp-1',
          feedbackLabel: 'purchased',
          purchasePrice: '6800',
          expectedResalePrice: '7800',
          feedbackNote: '线下验机通过',
        });
        return jsonResponse({
          opportunityId: 'opp-1',
          feedbackLabel: 'purchased',
          feedbackType: 'decision',
          status: 'PURCHASED',
          decision: 'purchased',
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Mark bought' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mark bought' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: '实际买入价' }), {
      target: { value: '6800' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: '预估转售价' }), {
      target: { value: '7800' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: '成交备注' }), {
      target: { value: '线下验机通过' },
    });

    expect(screen.getByText(/预估利润 ¥1,000 · ROI 14.7%/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认成交并记录 ROI' }));

    await waitFor(() => {
      expect(screen.getByText(/已回写成交：PURCHASED · purchased，ROI 证据已进入结果漏斗。/)).toBeInTheDocument();
    });
  });

  it('shows auto calibration controls in the workbench panel', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.pathname === '/api/buy/opportunities') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          summary: {
            opportunityCount: 1,
            baselineCount: 1,
            watchTargetCount: 0,
            feedbackCount: 3,
            calibrationRecommendationCount: 2,
          },
          outcomeFunnel: {
            alertedOpportunityCount: 4,
            openedOpportunityCount: 3,
            contactedOpportunityCount: 2,
            purchasedOpportunityCount: 1,
            roiEvidenceCount: 1,
            alertToOpenRate: 0.75,
            alertToContactRate: 0.5,
            openToContactRate: 0.6667,
            contactToPurchaseRate: 0.5,
          },
          feedbackQuality: {
            feedbackCount: 3,
            opportunityCount: 5,
          },
          feedbackCalibration: {
            windowDays: 30,
            effectiveCalibrationConfig: {
              pricingThresholds: {
                referenceOnly: {
                  seller_sample_count: 3,
                  unique_seller_count: 2,
                  exact_spec_ratio: 0.65,
                  reliability_score: 60,
                  freshness_days: 14,
                },
                guidanceReady: {
                  seller_sample_count: 6,
                  unique_seller_count: 3,
                  exact_spec_ratio: 0.75,
                  reliability_score: 75,
                  freshness_days: 14,
                },
              },
              opportunityScoring: {
                buyCeilingTightenPct: 4,
                discountRateWeight: 0.52,
                ceilingGapWeight: 0.34,
                confidenceWeight: 0.14,
                riskPenaltyWeight: 0.25,
                defaultConfidence: 0.45,
              },
              lastAppliedAt: '2026-04-24T01:00:00+00:00',
              lastAppliedBy: 'ops-bot',
              lastApplySource: 'buy_feedback_calibration_apply',
              lastCalibrationWindowDays: 30,
              lastAppliedRecommendationIds: [
                'threshold_guidance_sample_count',
                'ranking_risk_penalty_weight',
              ],
            },
            recommendations: {
              totalRecommendationCount: 2,
              autoApplicableRecommendationCount: 2,
              thresholdRecommendations: [
                {
                  id: 'threshold_guidance_sample_count',
                  title: '提高 guidance 样本门槛',
                  summary: '样本不稳偏多',
                  recommendedAction: '提高 seller sample count',
                },
              ],
              rankingRecommendations: [
                {
                  id: 'ranking_risk_penalty_weight',
                  title: '提高风险惩罚权重',
                  summary: '风险 gap 明显',
                  recommendedAction: '提高 risk penalty',
                },
              ],
            },
          },
          opportunities: [],
          baselines: [],
          watchTargets: [],
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '应用所选校准' })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('提高 guidance 样本门槛')).toBeInTheDocument();
    });
    expect(screen.getByText(/自动可执行 2 条/)).toBeInTheDocument();
    expect(screen.getByText(/已选择 2 \/ 2 条可应用建议/)).toBeInTheDocument();
    expect(screen.getByText('提高 guidance 样本门槛')).toBeInTheDocument();
    expect(screen.getByText(/buy ceiling 收紧 4.0% · risk penalty 0.25/)).toBeInTheDocument();
    expect(screen.getByText(/最近落地 2 条建议/)).toBeInTheDocument();
    expect(screen.getByText(/打开 3 · 联系 2 · ROI 证据 1/)).toBeInTheDocument();
    expect(screen.getByText(/提醒→打开 75.0% · 打开→联系 66.7%/)).toBeInTheDocument();
  });

  it('applies only the selected calibration recommendations', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.pathname === '/api/buy/opportunities') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          summary: {
            opportunityCount: 0,
            baselineCount: 0,
            watchTargetCount: 0,
            feedbackCount: 2,
            calibrationRecommendationCount: 2,
          },
          outcomeFunnel: {
            alertedOpportunityCount: 2,
            openedOpportunityCount: 1,
            contactedOpportunityCount: 1,
            purchasedOpportunityCount: 0,
            roiEvidenceCount: 0,
            alertToOpenRate: 0.5,
            alertToContactRate: 0.5,
            openToContactRate: 1,
            contactToPurchaseRate: 0,
          },
          feedbackCalibration: {
            windowDays: 30,
            recommendations: {
              totalRecommendationCount: 2,
              autoApplicableRecommendationCount: 2,
              thresholdRecommendations: [
                {
                  id: 'threshold_guidance_sample_count',
                  title: '提高 guidance 样本门槛',
                  summary: '样本不稳偏多',
                  recommendedAction: '提高 seller sample count',
                },
              ],
              rankingRecommendations: [
                {
                  id: 'ranking_risk_penalty_weight',
                  title: '提高风险惩罚权重',
                  summary: '风险 gap 明显',
                  recommendedAction: '提高 risk penalty',
                },
              ],
            },
          },
          opportunities: [],
          baselines: [],
          watchTargets: [],
        });
      }

      if (url.pathname === '/api/buy/feedback-calibration/apply' && init?.method === 'POST') {
        const payload = JSON.parse(requestBodyText(init.body)) as Record<string, unknown>;
        expect(payload.categoryCode).toBe('apple_computer');
        expect(payload.recommendationIds).toEqual(['threshold_guidance_sample_count']);
        return jsonResponse({
          categoryCode: 'apple_computer',
          windowDays: 30,
          appliedRecommendationCount: 1,
          skippedRecommendationCount: 0,
          baselineRebuild: { baselineCount: 12 },
          opportunityRefresh: { opportunityCount: 8 },
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByLabelText('选择建议 提高 guidance 样本门槛')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('选择建议 提高风险惩罚权重'));
    await waitFor(() => {
      expect(screen.getByText(/已选择 1 \/ 2 条可应用建议/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '应用所选校准' }));

    await waitFor(() => {
      expect(screen.getByText(/已应用 1 条建议，重建 12 条基线，刷新 8 条机会。/)).toBeInTheDocument();
    });
  });

  it('supports keyboard shortcuts for daily opportunity pack actions', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/buy/opportunities') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          summary: {
            opportunityCount: 2,
            baselineCount: 0,
            watchTargetCount: 0,
            feedbackCount: 0,
            calibrationRecommendationCount: 0,
          },
          outcomeFunnel: {
            alertedOpportunityCount: 2,
            openedOpportunityCount: 0,
            contactedOpportunityCount: 0,
            purchasedOpportunityCount: 0,
            roiEvidenceCount: 0,
            alertToOpenRate: 0,
            alertToContactRate: 0,
            openToContactRate: 0,
            contactToPurchaseRate: 0,
          },
          opportunities: [],
          baselines: [],
          watchTargets: [],
          dailyOpportunityPack: {
            generatedAt: '2026-04-24T15:30:00+00:00',
            summary: {
              targetProcessingCount: 2,
              packOpportunityCount: 2,
              openBacklogCount: 2,
              ungroupedOpenCount: 0,
              feedbackCount: 0,
              contactedOpportunityCount: 0,
              purchasedOpportunityCount: 0,
              roiEvidenceCount: 0,
              feedbackCoverageRate: 0,
              operatingMode: 'opportunity_digest_first',
              northStar: '按键操作验证',
            },
            groups: [
              {
                key: 'act_now',
                label: '立即看',
                recommendedAction: '先处理',
                count: 1,
                tasks: [
                  {
                    rank: 1,
                    groupKey: 'act_now',
                    groupLabel: '立即看',
                    recommendedAction: '先处理',
                    reason: '对比机会分',
                    slaLabel: '快动作',
                    riskFlags: [],
                    valueSignals: [],
                    opportunity: {
                      id: 'opp-1',
                      title: 'MacBook M1',
                      status: 'OPEN',
                      decision: null,
                      currentPrice: 6800,
                      fairPrice: 7400,
                      buyCeiling: 7100,
                      opportunityScore: 80,
                      riskScore: 5,
                      explanation: {
                        readinessSummary: '可行动',
                        reviewGateSummary: '通过',
                        specGateSummary: '通过',
                      },
                      specContract: { status: 'complete' },
                    },
                  },
                ],
              },
              {
                key: 'negotiate',
                label: '可砍价',
                recommendedAction: '再确认',
                count: 1,
                tasks: [
                  {
                    rank: 2,
                    groupKey: 'negotiate',
                    groupLabel: '可砍价',
                    recommendedAction: '再确认',
                    reason: '有议价空间',
                    slaLabel: '下一步',
                    riskFlags: [],
                    valueSignals: [],
                    opportunity: {
                      id: 'opp-2',
                      title: 'MacBook M2',
                      status: 'OPEN',
                      decision: null,
                      currentPrice: 6500,
                      fairPrice: 7200,
                      buyCeiling: 7000,
                      opportunityScore: 77,
                      riskScore: 10,
                      explanation: {
                        readinessSummary: '可行动',
                        reviewGateSummary: '通过',
                        specGateSummary: '通过',
                      },
                      specContract: { status: 'complete' },
                    },
                  },
                ],
              },
            ],
            marketIntel: [],
          },
        });
      }

      if (url.pathname === '/api/buy/feedback' && init?.method === 'POST') {
        const payload = JSON.parse(requestBodyText(init.body)) as Record<string, unknown>;
        return jsonResponse({
          ...payload,
          feedbackType: 'decision',
          status: payload.feedbackLabel === 'contacted' ? 'CONTACTED' : 'REJECTED',
          decision: payload.feedbackLabel,
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '今日机会任务包' })).toBeInTheDocument();
    });

    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'a' });

    await waitFor(() => {
      const posted = fetchMock.mock.calls.find(([, callInit]) => callInit?.method === 'POST');
      const payload = JSON.parse(requestBodyText(posted?.[1]?.body)) as Record<string, unknown>;
      expect(payload.opportunityId).toBe('opp-2');
      expect(payload.feedbackLabel).toBe('contacted');
    });

    fireEvent.keyDown(window, { key: 'd' });
    await waitFor(() => {
      const postedCalls = fetchMock.mock.calls.filter(([, callInit]) => callInit?.method === 'POST');
      expect(postedCalls).toHaveLength(2);
      const secondPayload = JSON.parse(requestBodyText(postedCalls[1]?.[1]?.body)) as Record<string, unknown>;
      expect(secondPayload.opportunityId).toBe('opp-2');
      expect(secondPayload.feedbackLabel).toBe('not_worth_it');
    });
  });

  it('supports Enter key to open selected opportunity detail sheet', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/buy/opportunities') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          summary: {
            opportunityCount: 1,
            baselineCount: 0,
            watchTargetCount: 0,
            feedbackCount: 0,
            calibrationRecommendationCount: 0,
          },
          outcomeFunnel: {
            alertedOpportunityCount: 1,
            openedOpportunityCount: 0,
            contactedOpportunityCount: 0,
            purchasedOpportunityCount: 0,
            roiEvidenceCount: 0,
            alertToOpenRate: 0,
            alertToContactRate: 0,
            openToContactRate: 0,
            contactToPurchaseRate: 0,
          },
          opportunities: [],
          baselines: [],
          watchTargets: [],
          dailyOpportunityPack: {
            generatedAt: '2026-04-24T15:30:00+00:00',
            summary: {
              targetProcessingCount: 1,
              packOpportunityCount: 1,
              openBacklogCount: 1,
              ungroupedOpenCount: 0,
              feedbackCount: 0,
              contactedOpportunityCount: 0,
              purchasedOpportunityCount: 0,
              roiEvidenceCount: 0,
              feedbackCoverageRate: 0,
              operatingMode: 'opportunity_digest_first',
              northStar: '按回车打开详情',
            },
            groups: [
              {
                key: 'act_now',
                label: '立即看',
                recommendedAction: '先处理',
                count: 1,
                tasks: [
                  {
                    rank: 1,
                    groupKey: 'act_now',
                    groupLabel: '立即看',
                    recommendedAction: '先处理',
                    reason: '对比机会分',
                    slaLabel: '快动作',
                    riskFlags: [],
                    valueSignals: [],
                    opportunity: {
                      id: 'opp-enter',
                      itemIdRef: 'item-enter',
                      title: 'MacBook M1',
                      status: 'OPEN',
                      decision: null,
                      currentPrice: 6800,
                      fairPrice: 7400,
                      buyCeiling: 7100,
                      opportunityScore: 80,
                      riskScore: 5,
                      explanation: {
                        readinessSummary: '可行动',
                        reviewGateSummary: '通过',
                        specGateSummary: '通过',
                      },
                      specContract: { status: 'complete' },
                    },
                  },
                ],
              },
            ],
            marketIntel: [],
          },
        });
      }

      if (url.pathname === '/api/buy/opportunities/opp-enter') {
        return jsonResponse({
          categoryCode: 'apple_computer',
          opportunity: {
            id: 'opp-enter',
            itemIdRef: 'item-enter',
            title: 'MacBook M1',
            status: 'OPEN',
            decision: null,
            currentPrice: 6800,
            fairPrice: 7400,
            buyCeiling: 7100,
            opportunityScore: 80,
            riskScore: 5,
            explanation: {
              readinessSummary: '可行动',
              reviewGateSummary: '通过',
              specGateSummary: '通过',
            },
            specContract: { status: 'complete' },
          },
        });
      }

      if (url.pathname === '/api/buy/feedback' && init?.method === 'POST') {
        const payload = JSON.parse(requestBodyText(init.body)) as Record<string, unknown>;
        return jsonResponse({
          ...payload,
          feedbackType: 'decision',
          status: payload.feedbackLabel === 'contacted' ? 'CONTACTED' : 'REJECTED',
          decision: payload.feedbackLabel,
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp('/?category_code=apple_computer');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '今日机会任务包' })).toBeInTheDocument();
    });

    fireEvent.keyDown(window, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'MacBook M1' })).toBeInTheDocument();
    });
    expect(window.location.pathname).toBe('/');
  });
});
