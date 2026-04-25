import type { PropsWithChildren, ReactNode } from 'react';

import '../styles/page-shell.css';

type PageHeroProps = PropsWithChildren<{
  eyebrow: string;
  title: string;
  description: string;
  meta?: ReactNode;
}>;

export function PageHero(props: PageHeroProps) {
  return (
    <section className="panel page-hero">
      <div className="page-hero-copy">
        <p className="eyebrow">{props.eyebrow}</p>
        <h2>{props.title}</h2>
        <p className="page-hero-description">{props.description}</p>
        {props.children ? <div className="page-hero-foot">{props.children}</div> : null}
      </div>
      {props.meta ? <div className="page-hero-meta">{props.meta}</div> : null}
    </section>
  );
}
