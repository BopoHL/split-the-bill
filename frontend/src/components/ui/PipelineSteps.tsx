'use client';

import type { ReactNode } from 'react';
import { Check } from 'lucide-react';

export interface PipelineStep {
  key: string;
  label: string;
  /** Shown under the step once it is done — what it came up with. */
  detail?: ReactNode;
}

/** The steps of something the server works through, the ones behind ticked
 *  and the one under way spinning — a scan, a bill said out loud. */
export default function PipelineSteps({ steps, current }: { steps: readonly PipelineStep[]; current: number }) {
  return (
    <div className="flex flex-col gap-5 rounded-lg border-[1.5px] border-outline bg-surface px-[22px] py-7">
      {steps.map((step, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={step.key} className="flex items-start gap-[13px]">
            <span
              className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] ${
                done ? 'border-success bg-success text-success-fg' : 'border-outline'
              }`}
            >
              {done ? (
                <Check className="h-[15px] w-[15px]" strokeWidth={2.5} />
              ) : active ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              ) : (
                <span className="h-2 w-2 rounded-full bg-border" />
              )}
            </span>
            <span className="min-w-0 pt-1">
              <span className={`block text-sm font-semibold ${active || done ? 'text-foreground' : 'text-muted-2'}`}>
                {step.label}
              </span>
              {done && step.detail && (
                <span className="mt-1 block text-[12px] leading-snug text-muted [overflow-wrap:anywhere]">{step.detail}</span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
