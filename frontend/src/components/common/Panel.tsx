import type { HTMLAttributes, ReactNode } from "react";

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  eyebrow?: string;
  title?: string;
  action?: ReactNode;
}

export default function Panel({ children, eyebrow, title, action, className = "", ...props }: PanelProps) {
  return (
    <section className={`panel ${className}`} {...props}>
      {(eyebrow || title || action) && <div className="panel-header">
        <div>{eyebrow && <div className="panel-eyebrow">{eyebrow}</div>}{title && <h2 className="panel-title">{title}</h2>}</div>
        {action}
      </div>}
      {children}
    </section>
  );
}