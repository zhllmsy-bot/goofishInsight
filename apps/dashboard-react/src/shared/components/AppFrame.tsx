import type { PropsWithChildren } from 'react';

import { DashboardHeader } from '../../features/dashboard/components/DashboardHeader';

type AppFrameProps = PropsWithChildren<{
  className?: string;
}>;

export function AppFrame(props: AppFrameProps) {
  return (
    <div className={props.className ? `app-frame ${props.className}` : 'app-frame'}>
      <DashboardHeader />
      {props.children}
    </div>
  );
}
