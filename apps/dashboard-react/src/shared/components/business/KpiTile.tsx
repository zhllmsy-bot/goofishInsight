import type { ReactNode } from 'react';

import { cn } from '../../lib/utils';
import { Card, CardContent } from '../ui/card';

type KpiTone = 'default' | 'success' | 'warning' | 'danger' | 'info';

type KpiTileProps = {
  className?: string;
  label: ReactNode;
  subtitle?: ReactNode;
  tone?: KpiTone;
  value: ReactNode;
};

export function KpiTile(props: KpiTileProps) {
  return (
    <Card className={cn('kpi-tile', props.tone ? `is-${props.tone}` : null, props.className)}>
      <CardContent>
        <span className="metric-label">{props.label}</span>
        <strong className="kpi-value" data-number>
          {props.value}
        </strong>
        {props.subtitle ? <small className="panel-subtitle">{props.subtitle}</small> : null}
      </CardContent>
    </Card>
  );
}
