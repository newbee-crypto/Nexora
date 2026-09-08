import React from "react";
import {
  CheckCircle2,
  Send,
  MailOpen,
  MousePointerClick,
  ShoppingBag,
} from "lucide-react";

interface FunnelStats {
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  purchased: number;
  failed: number;
}

interface FunnelChartProps {
  stats: FunnelStats;
}

export default function FunnelChart({ stats }: FunnelChartProps) {
  const sent = stats.sent || 0;
  const delivered = stats.delivered || 0;
  const opened = stats.opened || 0;
  const clicked = stats.clicked || 0;
  const purchased = stats.purchased || 0;
  const failed = stats.failed || 0;

  // Percentages relative to Sent (or 100% baseline)
  const getPct = (value: number, total: number) => {
    if (total === 0) return 0;
    return Math.round((value / total) * 100);
  };

  const deliveredPctOfSent = getPct(delivered, sent);
  const openedPctOfDelivered = getPct(opened, delivered);
  const clickedPctOfOpened = getPct(clicked, opened);
  const purchasedPctOfClicked = getPct(purchased, clicked);

  const openedPctOfSent = getPct(opened, sent);
  const clickedPctOfSent = getPct(clicked, sent);
  const purchasedPctOfSent = getPct(purchased, sent);

  const steps = [
    {
      id: "sent",
      label: "Sent",
      count: sent,
      pctLabel: "Baseline",
      pctValue: 100,
      color: "bg-zinc-900",
      icon: <Send className="h-4 w-4 text-zinc-500" />,
      subtext: `${sent} communications dispatched`,
    },
    {
      id: "delivered",
      label: "Delivered",
      count: delivered,
      pctLabel: "Delivery Rate",
      pctValue: deliveredPctOfSent,
      color: "bg-indigo-600",
      icon: <CheckCircle2 className="h-4 w-4 text-indigo-500" />,
      subtext: `${deliveredPctOfSent}% of sent. Failed: ${failed}`,
    },
    {
      id: "opened",
      label: "Opened",
      count: opened,
      pctLabel: "Open Rate",
      pctValue: openedPctOfSent,
      color: "bg-amber-500",
      icon: <MailOpen className="h-4 w-4 text-amber-500" />,
      subtext:
        opened > 0
          ? `${openedPctOfDelivered}% of delivered`
          : "0% of delivered",
    },
    {
      id: "clicked",
      label: "Clicked",
      count: clicked,
      pctLabel: "Click Rate",
      pctValue: clickedPctOfSent,
      color: "bg-blue-600",
      icon: <MousePointerClick className="h-4 w-4 text-blue-500" />,
      subtext:
        clicked > 0 ? `${clickedPctOfOpened}% of opened` : "0% of opened",
    },
    {
      id: "purchased",
      label: "Purchased",
      count: purchased,
      pctLabel: "Purchase Rate",
      pctValue: purchasedPctOfSent,
      color: "bg-emerald-600",
      icon: <ShoppingBag className="h-4 w-4 text-emerald-500" />,
      subtext:
        purchased > 0
          ? `${purchasedPctOfClicked}% of clicked`
          : "0% of clicked",
    },
  ];

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-6">
      <div className="flex items-center justify-between border-b border-zinc-100 pb-4">
        <div>
          <h2 className="text-sm font-semibold text-zinc-900">
            Campaign Delivery & Nexoran Funnel
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Real-time status updates from receipt webhooks
          </p>
        </div>
        <div className="flex items-center gap-1.5 rounded-full bg-zinc-50 border border-zinc-200 px-2.5 py-0.5 text-2xs font-medium text-zinc-600">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          Live updates polling
        </div>
      </div>

      <div className="mt-6 space-y-5">
        {steps.map((step) => {
          // Prevent tiny percentage widths from showing weirdly, but 0 is 0
          const barWidth = step.count === 0 ? "0%" : `${step.pctValue}%`;

          return (
            <div key={step.id} className="group">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <div className="flex items-center gap-2 font-medium text-zinc-900">
                  {step.icon}
                  <span>{step.label}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-zinc-900">
                    {step.count.toLocaleString()}
                  </span>
                  <span className="text-zinc-400">|</span>
                  <span className="text-zinc-500 font-medium text-2xs">
                    {step.pctLabel}: {step.pctValue}%
                  </span>
                </div>
              </div>

              {/* Funnel Bar container */}
              <div className="h-5 w-full rounded bg-zinc-100/70 border border-zinc-200/40 relative overflow-hidden">
                <div
                  className={`h-full rounded-r transition-all duration-500 ease-out ${step.color}`}
                  style={{ width: barWidth }}
                />
              </div>

              <div className="flex items-center justify-between mt-1 text-2xs text-zinc-400">
                <span>{step.subtext}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 grid grid-cols-4 gap-4 border-t border-zinc-100 pt-5 text-center">
        <div>
          <span className="text-2xs text-zinc-400 font-medium block">
            Delivery Success
          </span>
          <span className="text-lg font-semibold text-zinc-950 mt-0.5">
            {sent > 0 ? getPct(delivered, sent) : 0}%
          </span>
        </div>
        <div>
          <span className="text-2xs text-zinc-400 font-medium block">
            Open Rate
          </span>
          <span className="text-lg font-semibold text-zinc-950 mt-0.5">
            {delivered > 0 ? getPct(opened, delivered) : 0}%
          </span>
        </div>
        <div>
          <span className="text-2xs text-zinc-400 font-medium block">
            Click Rate
          </span>
          <span className="text-lg font-semibold text-zinc-950 mt-0.5">
            {opened > 0 ? getPct(clicked, opened) : 0}%
          </span>
        </div>
        <div>
          <span className="text-2xs text-zinc-400 font-medium block">
            Nexoran (ROI)
          </span>
          <span className="text-lg font-semibold text-emerald-600 mt-0.5">
            {clicked > 0 ? getPct(purchased, clicked) : 0}%
          </span>
        </div>
      </div>
    </div>
  );
}
