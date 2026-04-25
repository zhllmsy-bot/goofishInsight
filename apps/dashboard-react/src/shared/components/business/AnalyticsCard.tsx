import type { ReactNode } from 'react';

import { cn } from '../../lib/utils';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../ui/card';

type AnalyticsCardProps = {
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  description?: ReactNode;
  eyebrow?: ReactNode;
  title: ReactNode;
};

export function AnalyticsCard(props: AnalyticsCardProps) {
  return (
    <Card className={cn('analytics-card', props.className)}>
      <CardHeader className="panel-header">
        <div>
          {props.eyebrow ? <p className="eyebrow">{props.eyebrow}</p> : null}
          <CardTitle>
            <h2 className="panel-title">{props.title}</h2>
          </CardTitle>
          {props.description ? (
            <CardDescription className="panel-subtitle">
              {props.description}
            </CardDescription>
          ) : null}
        </div>
        {props.actions ? <div className="panel-actions">{props.actions}</div> : null}
      </CardHeader>
      {props.children ? <CardContent>{props.children}</CardContent> : null}
    </Card>
  );
}
