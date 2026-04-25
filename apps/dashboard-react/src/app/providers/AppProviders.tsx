import { QueryClientProvider, QueryErrorResetBoundary } from '@tanstack/react-query';
import { useState } from 'react';

import type { PropsWithChildren } from 'react';

import { createAppQueryClient } from '../../shared/lib/queryClient';

export function AppProviders(props: PropsWithChildren) {
  const [queryClient] = useState(createAppQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <QueryErrorResetBoundary>{props.children}</QueryErrorResetBoundary>
    </QueryClientProvider>
  );
}
