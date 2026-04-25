import type { PropsWithChildren } from 'react';

import { DashboardHeader } from '../../features/dashboard/components/DashboardHeader';

type TerminalScreenProps = PropsWithChildren<{
  className?: string;
}>;

export function TerminalScreen(props: TerminalScreenProps) {
  return (
    <div className={props.className ? `terminal-app ${props.className}` : 'terminal-app'}>
      <DashboardHeader />
      {props.children}
    </div>
  );
}
