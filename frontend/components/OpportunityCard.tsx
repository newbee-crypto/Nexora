import React from "react";
import { Clock, Star, AlertTriangle, UserPlus, ArrowRight, TrendingUp } from "lucide-react";

export interface Opportunity {
  id: string;
  title: string;
  description: string;
  audience_count: number;
  avg_spend: number;
  estimated_recovery: number;
  suggested_goal: string;
  urgency: "high" | "medium" | "low";
  channel_hint: string;
  icon: string;
}

interface OpportunityCardProps {
  opportunity: Opportunity;
  onSelect: (goal: string) => void;
}

export default function OpportunityCard({ opportunity, onSelect }: OpportunityCardProps) {
  const getIcon = (iconName: string) => {
    switch (iconName) {
      case "clock":
        return <Clock className="h-4 w-4 text-amber-600" />;
      case "star":
        return <Star className="h-4 w-4 text-yellow-600" />;
      case "alert":
        return <AlertTriangle className="h-4 w-4 text-red-600" />;
      case "user-plus":
        return <UserPlus className="h-4 w-4 text-blue-600" />;
      default:
        return <TrendingUp className="h-4 w-4 text-zinc-600" />;
    }
  };

  const getUrgencyClass = (urgency: string) => {
    switch (urgency) {
      case "high":
        return "bg-red-50 text-red-700 border-red-200/50";
      case "medium":
        return "bg-amber-50 text-amber-700 border-amber-200/50";
      default:
        return "bg-zinc-50 text-zinc-700 border-zinc-200/50";
    }
  };

  return (
    <div className="flex flex-col justify-between rounded-lg border border-zinc-200 bg-white p-5 transition-colors hover:border-zinc-300">
      <div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="rounded-md border border-zinc-200/60 p-1 bg-zinc-50">
              {getIcon(opportunity.icon)}
            </div>
            <span className={`rounded-full border px-2 py-0.5 text-2xs font-medium uppercase tracking-wider ${getUrgencyClass(opportunity.urgency)}`}>
              {opportunity.urgency} priority
            </span>
          </div>
          <div className="text-right">
            <span className="text-xs text-zinc-500 font-medium block">Est. Revenue</span>
            <span className="text-sm font-semibold text-zinc-900">₹{opportunity.estimated_recovery.toLocaleString()}</span>
          </div>
        </div>

        <h3 className="mt-4 text-sm font-semibold text-zinc-900 tracking-tight leading-snug">
          {opportunity.title}
        </h3>
        <p className="mt-2 text-xs text-zinc-500 leading-relaxed">
          {opportunity.description}
        </p>

        <div className="mt-4 flex items-center justify-between rounded-md bg-zinc-50/50 border border-zinc-100 px-3 py-2 text-2xs">
          <div className="flex flex-col">
            <span className="text-zinc-400 font-medium">Audience Size</span>
            <span className="font-semibold text-zinc-700 mt-0.5">{opportunity.audience_count} customers</span>
          </div>
          <div className="flex flex-col text-right">
            <span className="text-zinc-400 font-medium">Channel Hint</span>
            <span className="font-semibold text-zinc-700 capitalize mt-0.5">{opportunity.channel_hint}</span>
          </div>
        </div>
      </div>

      <button
        onClick={() => onSelect(opportunity.suggested_goal)}
        className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-zinc-900 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-zinc-800 focus:outline-none focus:ring-1 focus:ring-zinc-950"
      >
        Create Campaign
        <ArrowRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
