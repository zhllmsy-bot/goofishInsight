import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { AppFrame } from '../../../shared/components/AppFrame';
import { PageHero } from '../../../shared/components/PageHero';
import { formatCurrency, formatNumber, formatRelative } from '../../dashboard/lib/formatters';
import { buildWorkspaceLocation, readInitialQuery } from '../../dashboard/lib/urlState';
import { useItemDetail } from '../hooks/useItemDetail';

import '../../dashboard/styles/dashboard.css';
import '../../progress/styles/progress.css';
import '../styles/item-detail.css';

export function ItemDetailPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const itemId = params.itemId ?? '';
  const workspaceQuery = readInitialQuery(location.search);
  const { detail, isLoading, error } = useItemDetail(itemId);
  const dashboardTarget = buildWorkspaceLocation('/', workspaceQuery);
  const runtimeTarget = buildWorkspaceLocation('/ops/runtime', workspaceQuery);

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack progress-page">
            <PageHero
              eyebrow={`${detail?.item.domain_label ?? '-'} · ${detail?.item.task_display_name ?? '-'}`}
              title={detail?.item.title ?? '商品详情'}
              description="详情页已经并回 React 主壳层，查看 listing、快照和原始响应时不再跳回旧模板页。"
              meta={
                <>
                  <span className="soft-pill is-accent">{formatCurrency(detail?.item.price)}</span>
                  <span className="soft-pill">{detail?.item.region ?? '-'}</span>
                  <span className="soft-pill">{formatRelative(detail?.item.last_seen_at ?? null)}</span>
                </>
              }
            >
              <Link className="nav-pill" to={dashboardTarget}>
                返回看板
              </Link>
              <button
                className="nav-pill"
                type="button"
                onClick={() => {
                  void navigate(runtimeTarget);
                }}
              >
                打开运行控制
              </button>
              {detail?.item.listing_url ? (
                <a className="nav-pill" href={detail.item.listing_url} rel="noreferrer" target="_blank">
                  打开闲鱼原页
                </a>
              ) : null}
            </PageHero>

            {error ? <div className="error-banner">{error}</div> : null}

            {isLoading && !detail ? (
              <section className="panel">
                <p className="eyebrow">Item Detail</p>
                <h2>正在汇总商品详情、快照和原始响应...</h2>
                <p className="panel-subtitle">这页会把当前商品的规格抽取、卖家信息和最近抓取快照一次性拉齐。</p>
              </section>
            ) : null}

            {detail ? (
              <>
                <section className="progress-two-column">
                  <article className="panel">
                    <div className="panel-header">
                      <div>
                        <p className="eyebrow">Listing Facts</p>
                        <h2>商品信息</h2>
                      </div>
                    </div>
                    {(detail.item.image_urls ?? []).length ? (
                      <div className="item-detail-image-grid">
                        {(detail.item.image_urls ?? []).map((imageUrl) => (
                          <img alt={detail.item.title} className="item-detail-image" key={imageUrl} src={imageUrl} />
                        ))}
                      </div>
                    ) : null}
                    <div className="item-detail-fact-grid">
                      <ItemDetailFact label="商品 ID" value={detail.item.item_id} />
                      <ItemDetailFact label="品牌" value={detail.item.normalized_brand} />
                      <ItemDetailFact label="型号家族" value={detail.item.normalized_model_family} />
                      <ItemDetailFact label="型号" value={detail.item.normalized_model} />
                      <ItemDetailFact label="芯片" value={detail.item.normalized_chip} />
                      <ItemDetailFact label="内存" value={formatStorage(detail.item.normalized_memory_gb, 'GB')} />
                      <ItemDetailFact label="硬盘" value={formatStorage(detail.item.normalized_storage_gb, 'GB')} />
                      <ItemDetailFact label="发布时间" value={detail.item.publish_time ?? '-'} />
                      <ItemDetailFact label="首次入库" value={detail.item.first_seen_at ?? '-'} />
                      <ItemDetailFact label="最近看到" value={detail.item.last_seen_at ?? '-'} />
                      <ItemDetailFact label="来源关键词" value={detail.item.source_keyword} />
                    </div>
                    {detail.spec ? (
                      <div className="item-detail-fact-grid">
                        <ItemDetailFact label="Spec 状态" value={detail.spec.status} />
                        <ItemDetailFact label="Spec 置信度" value={formatMaybeNumber(detail.spec.confidence)} />
                        <ItemDetailFact label="抽取方式" value={detail.spec.extractor_type} />
                        <ItemDetailFact label="产品线" value={detail.spec.product_line} />
                        <ItemDetailFact label="标准型号" value={detail.spec.model_name} />
                        <ItemDetailFact label="代际" value={detail.spec.generation} />
                        <ItemDetailFact label="表盘尺寸" value={formatStorage(detail.spec.case_size_mm, 'mm')} />
                        <ItemDetailFact label="太阳能" value={detail.spec.is_solar === true ? '是' : detail.spec.is_solar === false ? '否' : '-'} />
                        <ItemDetailFact label="显示类型" value={detail.spec.display_type} />
                        <ItemDetailFact label="屏幕尺寸" value={formatStorage(detail.spec.screen_size_in, '寸')} />
                        <ItemDetailFact label="芯片" value={detail.spec.chip_family} />
                        <ItemDetailFact label="CPU 核心" value={formatMaybeNumber(detail.spec.cpu_cores)} />
                        <ItemDetailFact label="GPU 核心" value={formatMaybeNumber(detail.spec.gpu_cores)} />
                        <ItemDetailFact label="内存" value={formatStorage(detail.spec.memory_gb, 'GB')} />
                        <ItemDetailFact label="硬盘" value={formatStorage(detail.spec.storage_gb, 'GB')} />
                        <ItemDetailFact label="需复核" value={detail.spec.needs_review ? '是' : '否'} />
                      </div>
                    ) : null}
                    <div className="pill-row">
                      {(detail.item.condition_tags ?? []).map((tag) => (
                        <span className="soft-pill" key={`condition:${tag}`}>{tag}</span>
                      ))}
                      {(detail.spec?.edition_tags ?? []).map((tag) => (
                        <span className="soft-pill" key={`edition:${tag}`}>{tag}</span>
                      ))}
                      {detail.item.has_video ? <span className="soft-pill">Video</span> : null}
                      {detail.item.is_ad ? <span className="soft-pill is-warning">Ad</span> : null}
                    </div>
                  </article>

                  <article className="panel">
                    <div className="panel-header">
                      <div>
                        <p className="eyebrow">Seller Context</p>
                        <h2>卖家与快照</h2>
                      </div>
                    </div>
                    <div className="item-detail-fact-grid compact">
                      <ItemDetailFact label="卖家" value={detail.seller?.seller_name} />
                      <ItemDetailFact label="卖家 ID" value={detail.seller?.seller_id} />
                      <ItemDetailFact label="地区" value={detail.seller?.region} />
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
                          {(detail.snapshots ?? []).length ? (
                            (detail.snapshots ?? []).map((snapshot, index) => (
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
                  </article>
                </section>

                <section className="panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Evidence Chain</p>
                      <h2>原始响应</h2>
                    </div>
                    {detail.item.raw_response_id ? (
                      <a
                        className="nav-pill"
                        href={`/api/raw-responses/${detail.item.raw_response_id}`}
                        rel="noreferrer"
                        target="_blank"
                      >
                        JSON
                      </a>
                    ) : null}
                  </div>
                  <pre className="item-detail-raw-block">{detail.raw_response_body || 'No raw response available.'}</pre>
                </section>
              </>
            ) : null}
          </div>
        </div>
      </main>
    </AppFrame>
  );
}

function ItemDetailFact(props: { label: string; value: string | null | undefined }) {
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
