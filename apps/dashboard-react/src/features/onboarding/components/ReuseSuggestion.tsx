import type { OnboardingReuseSuggestion, OnboardingAnalysis } from '../api/onboardingSchemas';
import { formatPercent } from '../../dashboard/lib/formatters';

type ReuseSuggestionProps = {
  reuseSuggestion: OnboardingReuseSuggestion | null | undefined;
  analysis: OnboardingAnalysis | null | undefined;
  reuseEnabled: boolean;
  onReuseToggle: (enabled: boolean) => void;
};

export function ReuseSuggestion({ reuseSuggestion, analysis, reuseEnabled, onReuseToggle }: ReuseSuggestionProps) {
  if (!reuseSuggestion) {
    return null;
  }

  const coverage = reuseSuggestion.coverage;
  const coveredCodes = coverage?.coveredSuggestedAttributeCodes ?? [];
  const missingCodes = coverage?.missingSuggestedAttributeCodes ?? [];
  const extraCodes = coverage?.extraTemplateAttributeCodes ?? [];
  const categoryCode = String((reuseSuggestion.category as Record<string, unknown>)?.code ?? '');
  const categoryName = String((reuseSuggestion.category as Record<string, unknown>)?.name ?? '');
  const templateVersion = String((reuseSuggestion.template as Record<string, unknown>)?.version ?? '');
  const templateStatus = String((reuseSuggestion.template as Record<string, unknown>)?.status ?? '');

  const observations = analysis?.attributeObservations ?? [];
  const resolveLabel = (code: string) => {
    const obs = observations.find((o) => o.attributeCode === code);
    return obs?.attributeName || code;
  };

  return (
    <div className="onboarding-reuse-block">
      <div className="onboarding-reuse-head">
        <div>
          <p className="eyebrow">Canonical Reuse</p>
          <p className="onboarding-reuse-description">
            建议直接复用现有大类模板
            <strong>{categoryName || categoryCode}</strong>，
            这次落库只补 raw cate 到模板的映射，不重复创建 category/template。
          </p>
        </div>
        <label className="onboarding-toggle">
          <input
            type="checkbox"
            checked={reuseEnabled}
            onChange={(event) => {
              onReuseToggle(event.target.checked);
            }}
          />
          <span>复用现有模板</span>
        </label>
      </div>
      <div className="pill-row">
        <span className="soft-pill is-accent">{categoryCode || '-'}</span>
        <span className="soft-pill">Template v{templateVersion || '-'}</span>
        <span className="soft-pill">{templateStatus || '-'}</span>
        <span className="soft-pill">覆盖 {formatPercent(Number(coverage?.coverageRatio ?? 0))}</span>
      </div>
      <div className="pill-row">
        {coveredCodes.length ? (
          coveredCodes.map((code) => (
            <span className="soft-pill" key={code}>{resolveLabel(code)}</span>
          ))
        ) : (
          <span className="soft-pill">暂无已覆盖属性</span>
        )}
      </div>
      {missingCodes.length ? (
        <div className="onboarding-reuse-missing">
          <p className="onboarding-reuse-description">
            这些候选属性当前模板还没覆盖。保持"复用现有模板"时，它们不会被自动写进已有模板，后续如有需要再做模板升级。
          </p>
          <div className="pill-row">
            {missingCodes.map((code) => (
              <span className="soft-pill" key={code}>{resolveLabel(code)}</span>
            ))}
          </div>
        </div>
      ) : null}
      {extraCodes.length ? (
        <div className="onboarding-reuse-extra">
          <p className="onboarding-reuse-description">现有模板里还有这些额外属性，会继续沿用：</p>
          <div className="pill-row">
            {extraCodes.map((code) => (
              <span className="soft-pill" key={code}>{resolveLabel(code)}</span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
