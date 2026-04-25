import type { ReactNode } from 'react';

import { cn } from '../../lib/utils';
import { Badge } from '../ui/badge';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '../ui/card';

export type DecisionBucket = 'buy' | 'watch' | 'market' | 'high' | 'neutral';

const DECISION_SHAPE: Record<DecisionBucket, string> = {
  buy: '●',
  watch: '◆',
  market: '─',
  high: '▲',
  neutral: '○',
};

type OpportunityCardVariant = 'hero' | 'row' | 'compact';

type OpportunityCardProps = {
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  decision?: DecisionBucket;
  decisionLabel?: ReactNode;
  eyebrow?: ReactNode;
  price?: ReactNode;
  score?: ReactNode;
  subtitle?: ReactNode;
  title: ReactNode;
  variant?: OpportunityCardVariant;
};

export function OpportunityCard(props: OpportunityCardProps) {
  const decision = props.decision ?? 'neutral';

  return (
    <Card
      className={cn('opportunity-card', `is-${props.variant ?? 'row'}`, props.className)}
      data-decision={decision}
    >
      <CardHeader className="opportunity-card-header">
        <div>
          {props.eyebrow ? <p className="eyebrow">{props.eyebrow}</p> : null}
          <CardTitle>
            <h3 className="opportunity-title">{props.title}</h3>
          </CardTitle>
          {props.subtitle ? <p className="panel-subtitle">{props.subtitle}</p> : null}
        </div>
        <div className="opportunity-card-meta">
          <Badge className={`decision-${decision}`} data-decision={decision}>
            <span aria-hidden="true" className="decision-marker">
              {DECISION_SHAPE[decision]}
            </span>
            {props.decisionLabel ?? decision}
          </Badge>
          {props.score ? <span className="soft-pill">机会 {props.score}</span> : null}
          {props.price ? <span className="soft-pill" data-number>{props.price}</span> : null}
        </div>
      </CardHeader>
      {props.children ? <CardContent>{props.children}</CardContent> : null}
      {props.actions ? <CardFooter className="opportunity-card-actions">{props.actions}</CardFooter> : null}
    </Card>
  );
}
