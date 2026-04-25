import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from 'react';

import '../styles/error-boundary.css';

export type AppErrorBoundaryFallbackProps = {
  error: Error;
  reset: () => void;
};

export type AppErrorBoundaryProps = PropsWithChildren<{
  fallback?: (props: AppErrorBoundaryFallbackProps) => ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  resetKeys?: readonly unknown[];
}>;

type AppErrorBoundaryState = {
  error: Error | null;
};

export function AppErrorBoundary(props: AppErrorBoundaryProps) {
  return <AppErrorBoundaryImpl {...props} />;
}

class AppErrorBoundaryImpl extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.props.onError?.(error, errorInfo);
  }

  componentDidUpdate(previousProps: AppErrorBoundaryProps) {
    if (!this.state.error) {
      return;
    }

    if (!hasResetKeysChanged(previousProps.resetKeys, this.props.resetKeys)) {
      return;
    }

    this.setState({ error: null });
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { children, fallback } = this.props;

    if (!this.state.error) {
      return children;
    }

    const error = this.state.error;

    if (fallback) {
      return fallback({
        error,
        reset: this.reset,
      });
    }

    return (
      <DefaultAppErrorState
        error={error}
        onGoHome={() => {
          window.location.assign('/');
        }}
        onReload={() => {
          window.location.reload();
        }}
        onViewRuntime={() => {
          window.location.assign('/runtime');
        }}
        onRetry={this.reset}
      />
    );
  }
}

function hasResetKeysChanged(previousResetKeys?: readonly unknown[], nextResetKeys?: readonly unknown[]) {
  if (previousResetKeys === nextResetKeys) {
    return false;
  }

  if (!previousResetKeys || !nextResetKeys) {
    return previousResetKeys !== nextResetKeys;
  }

  if (previousResetKeys.length !== nextResetKeys.length) {
    return true;
  }

  return nextResetKeys.some((value, index) => !Object.is(previousResetKeys[index], value));
}

type DefaultAppErrorStateProps = {
  error: Error;
  onGoHome: () => void;
  onReload: () => void;
  onRetry: () => void;
  onViewRuntime: () => void;
};

function DefaultAppErrorState(props: DefaultAppErrorStateProps) {
  return (
    <div className="error-shell" role="alert">
      <section className="error-card">
        <div className="error-copy">
          <p className="error-kicker">应用级异常</p>
          <h1 className="error-title">Goofish Insight 前端壳层出现错误</h1>
          <p className="error-description">
            这通常是一次未捕获的渲染异常。可以先刷新页面，或者直接跳到首页和运行状态继续排查。
          </p>
        </div>

        <div className="error-summary">
          <strong>{props.error.name || 'Error'}</strong>
          <span>{props.error.message || '未提供错误详情'}</span>
        </div>

        <div className="error-actions">
          <button className="error-button is-primary" type="button" onClick={props.onReload}>
            刷新页面
          </button>
          <button className="error-button is-secondary" type="button" onClick={props.onRetry}>
            重试
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
