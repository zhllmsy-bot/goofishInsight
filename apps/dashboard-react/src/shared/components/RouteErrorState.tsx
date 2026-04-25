import '../styles/error-boundary.css';

type RouteErrorStateProps = {
  error: Error;
  onGoHome: () => void;
  onReload: () => void;
  onRetry: () => void;
  onViewRuntime: () => void;
  routeLabel: string;
};

export function RouteErrorState(props: RouteErrorStateProps) {
  return (
    <div className="error-shell" role="alert">
      <section className="error-card">
        <div className="error-copy">
          <p className="error-kicker">路由级恢复</p>
          <h1 className="error-title">{props.routeLabel} 渲染失败</h1>
          <p className="error-description">
            当前页面在渲染时抛出了异常。你可以先重试当前路由，或者直接回到首页、查看运行状态继续排查。
          </p>
        </div>

        <div className="error-summary">
          <strong>{props.error.name || 'Error'}</strong>
          <span>{props.error.message || '未提供错误详情'}</span>
        </div>

        <div className="error-actions">
          <button className="error-button is-primary" type="button" onClick={props.onRetry}>
            重试当前路由
          </button>
          <button className="error-button is-secondary" type="button" onClick={props.onReload}>
            刷新页面
          </button>
          <button className="error-button" type="button" onClick={props.onGoHome}>
            返回首页
          </button>
          <button className="error-button" type="button" onClick={props.onViewRuntime}>
            查看运行状态
          </button>
        </div>

        {props.error.stack ? (
          <details className="error-details">
            <summary>查看错误详情</summary>
            <pre>{props.error.stack}</pre>
          </details>
        ) : null}
      </section>
    </div>
  );
}
