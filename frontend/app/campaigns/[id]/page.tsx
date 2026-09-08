"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Sparkles,
  RefreshCw,
  Layers,
  Calendar,
  ChevronLeft,
  ChevronRight,
  FileText,
  CheckCircle2,
} from "lucide-react";
import Link from "next/link";
import FunnelChart from "../../../components/FunnelChart";

interface CampaignDetail {
  id: string;
  name: string;
  goal: string;
  segment_filters: any;
  segment_size: number;
  message_template: string;
  channel: string;
  status: string;
  created_at: string;
  launched_at: string | null;
}

interface CampaignStats {
  campaign_id: string;
  campaign_name: string;
  total: number;
  queued: number;
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  purchased: number;
  failed: number;
  open_rate: number;
  click_rate: number;
  conversion_rate: number;
  estimated_cost: number;
  estimated_revenue: number;
  roi_percentage: number;
}

interface RecipientLog {
  id: string;
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  channel: string;
  message: string;
  status: string;
  sent_at: string | null;
  delivered_at: string | null;
  opened_at: string | null;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const RECIPIENT_LIMIT = 10;

// Custom SVG-based line chart to show live event metrics over time
const TimelineChart = ({
  data,
}: {
  data: { minute: number; sent: number; delivered: number; opened: number }[];
}) => {
  const hasEvents = data.some(
    (d) => d.sent > 0 || d.delivered > 0 || d.opened > 0,
  );
  if (!hasEvents) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-5 h-[245px] flex flex-col items-center justify-center text-center">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
          Event Timeline
        </span>
        <p className="text-2xs text-zinc-400 max-w-[220px] leading-relaxed">
          Waiting for webhook delivery receipts to assemble the event
          timeline...
        </p>
      </div>
    );
  }

  // Find max value for scaling Y axis
  const maxVal = Math.max(
    ...data.map((d) => Math.max(d.sent, d.delivered, d.opened)),
    1,
  );
  const height = 150;
  const width = 450;
  const padding = 20;
  const chartHeight = height - padding * 2;
  const chartWidth = width - padding * 2;

  // Helper to generate SVG points
  const getPointsPath = (key: "sent" | "delivered" | "opened") => {
    return data
      .map((d, index) => {
        const x = padding + (index / (data.length - 1)) * chartWidth;
        const y = padding + chartHeight - (d[key] / maxVal) * chartHeight;
        return `${x},${y}`;
      })
      .join(" ");
  };

  const sentPath = getPointsPath("sent");
  const deliveredPath = getPointsPath("delivered");
  const openedPath = getPointsPath("opened");

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-3xs">
      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-4">
        Event Timeline (Events per minute)
      </h3>
      <div
        className="relative w-full overflow-hidden"
        style={{ aspectRatio: "450/150" }}
      >
        <svg viewBox="0 0 450 150" className="w-full h-full">
          {/* Grid Lines */}
          <line
            x1={padding}
            y1={padding}
            x2={width - padding}
            y2={padding}
            stroke="#f4f4f5"
            strokeWidth={1}
          />
          <line
            x1={padding}
            y1={padding + chartHeight / 2}
            x2={width - padding}
            y2={padding + chartHeight / 2}
            stroke="#f4f4f5"
            strokeWidth={1}
          />
          <line
            x1={padding}
            y1={height - padding}
            x2={width - padding}
            y2={height - padding}
            stroke="#e4e4e7"
            strokeWidth={1.5}
          />

          {/* Paths */}
          <polyline
            fill="none"
            stroke="#6366f1"
            strokeWidth={2.5}
            points={sentPath}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-all duration-300"
          />
          <polyline
            fill="none"
            stroke="#3b82f6"
            strokeWidth={2.5}
            points={deliveredPath}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-all duration-300"
          />
          <polyline
            fill="none"
            stroke="#10b981"
            strokeWidth={2.5}
            points={openedPath}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-all duration-300"
          />

          {/* Data Dots */}
          {data.map((d, idx) => {
            const x = padding + (idx / (data.length - 1)) * chartWidth;
            const sentY =
              padding + chartHeight - (d.sent / maxVal) * chartHeight;
            const delY =
              padding + chartHeight - (d.delivered / maxVal) * chartHeight;
            const openY =
              padding + chartHeight - (d.opened / maxVal) * chartHeight;
            return (
              <g key={idx}>
                {d.sent > 0 && (
                  <circle
                    cx={x}
                    cy={sentY}
                    r={3.5}
                    fill="#6366f1"
                    stroke="#fff"
                    strokeWidth={1}
                  />
                )}
                {d.delivered > 0 && (
                  <circle
                    cx={x}
                    cy={delY}
                    r={3.5}
                    fill="#3b82f6"
                    stroke="#fff"
                    strokeWidth={1}
                  />
                )}
                {d.opened > 0 && (
                  <circle
                    cx={x}
                    cy={openY}
                    r={3.5}
                    fill="#10b981"
                    stroke="#fff"
                    strokeWidth={1}
                  />
                )}
              </g>
            );
          })}
        </svg>
      </div>
      {/* Legend */}
      <div className="mt-3 flex gap-4 text-3xs font-semibold justify-center">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-pulse" />{" "}
          Sent
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />{" "}
          Delivered
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />{" "}
          Opened
        </span>
      </div>
    </div>
  );
};

const formatSegmentFilters = (filters: any) => {
  if (!filters || Object.keys(filters).length === 0) return "All Customers";
  const parts = [];
  if (filters.inactive_days)
    parts.push(`Inactive: ${filters.inactive_days}+ days`);
  if (filters.active_days)
    parts.push(`Active: last ${filters.active_days} days`);
  if (filters.min_orders) parts.push(`Orders: ${filters.min_orders}+`);
  if (filters.min_spent)
    parts.push(`Spend: ₹${filters.min_spent.toLocaleString()}+`);
  if (filters.tags && filters.tags.length > 0)
    parts.push(`Tags: ${filters.tags.join(", ")}`);
  if (filters.budget_limit)
    parts.push(`Budget: ₹${filters.budget_limit.toLocaleString()}`);
  if (filters.customer_ids && filters.customer_ids.length > 0)
    parts.push(`Target Group: ${filters.customer_ids.length} customers`);
  return parts.join(" | ");
};

export default function CampaignDetailPage() {
  const params = useParams();
  const router = useRouter();
  const campaignId = params.id as string;

  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [stats, setStats] = useState<CampaignStats | null>(null);
  const [recipients, setRecipients] = useState<RecipientLog[]>([]);
  const [timelineRecipients, setTimelineRecipients] = useState<RecipientLog[]>(
    [],
  );
  const [recipientPage, setRecipientPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // AI Performance Insight state
  const [aiInsight, setAiInsight] = useState<string | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [insightForCompleted, setInsightForCompleted] = useState(false);
  const [insightVersion, setInsightVersion] = useState(0);

  // Selected recipient for personalized message preview popup modal
  const [selectedRecipient, setSelectedRecipient] =
    useState<RecipientLog | null>(null);
  const [simulatingId, setSimulatingId] = useState<string | null>(null);

  const getCustomerJourney = (customerName: string): RecipientLog[] => {
    if (!timelineRecipients) return [];
    return timelineRecipients
      .filter((r) => r.customer_name === customerName)
      .sort(
        (a, b) =>
          new Date(a.sent_at || 0).getTime() -
          new Date(b.sent_at || 0).getTime(),
      );
  };

  const renderMessageTemplates = () => {
    let parsedTemplates: Record<string, string> | null = null;
    try {
      if (
        campaign?.message_template &&
        (campaign.message_template.trim().startsWith("{") ||
          campaign.message_template.trim().startsWith("["))
      ) {
        parsedTemplates = JSON.parse(campaign.message_template);
      }
    } catch (e) {
      // Not a JSON template
    }

    if (parsedTemplates) {
      return (
        <div className="mt-4 space-y-4">
          {parsedTemplates.whatsapp && (
            <div className="rounded border border-emerald-150 bg-emerald-50/20 p-3.5">
              <span className="inline-flex items-center rounded bg-emerald-100 px-1.5 py-0.5 text-3xs font-semibold text-emerald-800 uppercase tracking-wider mb-2">
                WhatsApp Template
              </span>
              <p className="text-2xs text-zinc-650 leading-relaxed whitespace-pre-wrap font-sans">
                {parsedTemplates.whatsapp}
              </p>
            </div>
          )}
          {parsedTemplates.sms && (
            <div className="rounded border border-indigo-150 bg-indigo-50/20 p-3.5">
              <span className="inline-flex items-center rounded bg-indigo-100 px-1.5 py-0.5 text-3xs font-semibold text-indigo-800 uppercase tracking-wider mb-2">
                SMS Template
              </span>
              <p className="text-2xs text-zinc-650 leading-relaxed whitespace-pre-wrap font-sans">
                {parsedTemplates.sms}
              </p>
            </div>
          )}
          {parsedTemplates.email && (
            <div className="rounded border border-zinc-200 bg-zinc-50/30 p-3.5 text-2xs">
              <span className="inline-flex items-center rounded bg-zinc-100 px-1.5 py-0.5 text-3xs font-semibold text-zinc-750 uppercase tracking-wider mb-2">
                Email Template
              </span>
              <div className="border border-zinc-100 rounded bg-white shadow-3xs overflow-hidden mt-1.5">
                <div className="bg-zinc-50/50 border-b border-zinc-100 p-2.5 space-y-0.5 text-zinc-500 font-medium">
                  <div className="text-zinc-750">
                    <span className="text-zinc-400 mr-1 font-medium">
                      Subject:
                    </span>
                    {parsedTemplates.email.startsWith("SUBJECT:")
                      ? parsedTemplates.email
                          .split("|")[0]
                          .replace("SUBJECT:", "")
                          .trim()
                      : "Campaign Offer"}
                  </div>
                </div>
                <div className="p-3 text-zinc-650 leading-relaxed whitespace-pre-wrap font-sans">
                  {parsedTemplates.email.includes("BODY:")
                    ? parsedTemplates.email.split("BODY:")[1].trim()
                    : parsedTemplates.email}
                </div>
              </div>
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="mt-4 rounded border border-zinc-150 bg-zinc-50/50 p-4">
        <p className="text-2xs text-zinc-600 leading-relaxed whitespace-pre-wrap">
          {campaign?.message_template}
        </p>
      </div>
    );
  };

  // Group recipient communications by minute offset from launch time
  const getTimelineData = () => {
    if (
      !timelineRecipients ||
      timelineRecipients.length === 0 ||
      !campaign?.launched_at
    )
      return [];

    const launchTime = new Date(campaign.launched_at).getTime();
    const minutesMap: {
      [minute: number]: { sent: number; delivered: number; opened: number };
    } = {};

    timelineRecipients.forEach((rec) => {
      if (rec.sent_at) {
        const diffMin = Math.max(
          0,
          Math.floor((new Date(rec.sent_at).getTime() - launchTime) / 60000),
        );
        if (!minutesMap[diffMin])
          minutesMap[diffMin] = { sent: 0, delivered: 0, opened: 0 };
        minutesMap[diffMin].sent++;
      }
      if (rec.delivered_at) {
        const diffMin = Math.max(
          0,
          Math.floor(
            (new Date(rec.delivered_at).getTime() - launchTime) / 60000,
          ),
        );
        if (!minutesMap[diffMin])
          minutesMap[diffMin] = { sent: 0, delivered: 0, opened: 0 };
        minutesMap[diffMin].delivered++;
      }
      if (rec.opened_at) {
        const diffMin = Math.max(
          0,
          Math.floor((new Date(rec.opened_at).getTime() - launchTime) / 60000),
        );
        if (!minutesMap[diffMin])
          minutesMap[diffMin] = { sent: 0, delivered: 0, opened: 0 };
        minutesMap[diffMin].opened++;
      }
    });

    const sortedMinutes = Object.keys(minutesMap)
      .map(Number)
      .sort((a, b) => a - b);
    if (sortedMinutes.length === 0) return [];

    // Create a continuous array of minutes from 0 to max(5, maxMinute)
    const maxMinute = Math.max(5, Math.max(...sortedMinutes));
    const data = [];
    for (let m = 0; m <= maxMinute; m++) {
      data.push({
        minute: m,
        sent: minutesMap[m]?.sent || 0,
        delivered: minutesMap[m]?.delivered || 0,
        opened: minutesMap[m]?.opened || 0,
      });
    }
    return data;
  };

  // Reusable API Fetchers
  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/campaigns/${campaignId}/stats`);
      if (res.ok) {
        const json = await res.json();
        setStats(json);
      }
    } catch (err) {
      console.error("Failed to poll campaign stats:", err);
    }
  };

  const fetchRecipients = async () => {
    try {
      const skip = recipientPage * RECIPIENT_LIMIT;
      const res = await fetch(
        `${API_BASE}/campaigns/${campaignId}/communications?skip=${skip}&limit=${RECIPIENT_LIMIT}`,
      );
      if (res.ok) {
        const json = await res.json();
        setRecipients(json);
      }
    } catch (err) {
      console.error("Failed to fetch recipients:", err);
    }
  };

  const fetchTimelineRecipients = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/campaigns/${campaignId}/communications?skip=0&limit=500`,
      );
      if (res.ok) {
        const json = await res.json();
        setTimelineRecipients(json);
      }
    } catch (err) {
      console.error("Failed to fetch timeline recipients:", err);
    }
  };

  // Manual webhook simulation trigger
  const triggerSimulation = async (
    communicationId: string,
    eventType: string,
  ) => {
    setSimulatingId(`${communicationId}-${eventType}`);
    try {
      const res = await fetch(`${API_BASE}/receipts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          communication_id: communicationId,
          event_type: eventType,
          event_time: new Date().toISOString(),
          event_metadata: { source: "manual_simulation_ui" },
        }),
      });
      if (res.ok) {
        // Refresh dashboard immediately
        await fetchStats();
        await fetchRecipients();
        await fetchTimelineRecipients();
      }
    } catch (err) {
      console.error("Failed to trigger simulation webhook:", err);
    } finally {
      setSimulatingId(null);
    }
  };

  // Fetch initial campaign details
  useEffect(() => {
    async function fetchCampaignDetails() {
      try {
        setLoading(true);
        const res = await fetch(`${API_BASE}/campaigns/${campaignId}`);
        if (!res.ok) {
          if (res.status === 404) throw new Error("Campaign not found");
          throw new Error("Failed to fetch campaign details");
        }
        const json = await res.json();
        setCampaign(json);
        setError(null);
      } catch (err: any) {
        console.error(err);
        setError(err.message || "An error occurred");
      } finally {
        setLoading(false);
      }
    }

    if (campaignId) {
      fetchCampaignDetails();
    }
  }, [campaignId]);

  // Live Stats Polling (every 3 seconds)
  useEffect(() => {
    if (campaignId && campaign?.status === "launched") {
      // Fetch immediately once
      fetchStats();
      fetchRecipients();
      fetchTimelineRecipients();

      // Poll every 3 seconds
      const interval = setInterval(() => {
        fetchStats();
        fetchRecipients();
        fetchTimelineRecipients();
      }, 3000);
      return () => clearInterval(interval);
    } else if (campaignId && campaign) {
      // Fetch once for completed or draft
      fetchStats();
      fetchRecipients();
      fetchTimelineRecipients();
    }
  }, [campaignId, campaign, recipientPage]);

  // Generate AI Performance Insight once stats are available
  useEffect(() => {
    async function generateInsight() {
      if (!campaign || !stats || insightLoading) return;

      try {
        setInsightLoading(true);
        // We use a specific session ID for insights to keep conversation history isolated
        const session = `insight-${campaignId}`;

        // Construct statistics prompt with full ROI and conversion stats
        const prompt = `Here are the performance stats for the campaign '${campaign.name}' (Channel: ${campaign.channel}, Goal: '${campaign.goal}').
Total Sent: ${stats.sent}
Delivered: ${stats.delivered}
Opened: ${stats.opened}
Clicked: ${stats.clicked}
Purchased: ${stats.purchased}
Failed: ${stats.failed}
Est. Cost: ₹${stats.estimated_cost}
Est. Revenue: ₹${stats.estimated_revenue}
ROI: ${stats.roi_percentage}%
Nexoran Rate: ${stats.conversion_rate}%

Write a short 2-3 line natural language performance analysis or campaign success verdict. If the campaign has achieved positive ROI, call out the success and highlight the key drivers (e.g. high open rate, conversion value). If there are no purchases yet, comment on engagement and delivery success. Do not suggest launching any campaigns. Be concise and professional.`;

        const res = await fetch(`${API_BASE}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: session,
            message: prompt,
          }),
        });

        if (res.ok) {
          const json = await res.json();
          setAiInsight(json.final_message);
        }
      } catch (err) {
        console.error("Failed to generate AI performance insight:", err);
      } finally {
        setInsightLoading(false);
      }
    }

    if (campaign && stats && stats.sent > 0) {
      const isCompleted = stats.queued === 0;
      if (isCompleted && insightForCompleted) return;
      if (!isCompleted && aiInsight && !insightForCompleted) return;

      generateInsight();
      if (isCompleted) {
        setInsightForCompleted(true);
      }
    }
  }, [campaign, stats?.sent, stats?.queued, campaignId, insightVersion]);

  const getStatusClass = (status: string) => {
    switch (status) {
      case "launched":
        return "bg-emerald-50 text-emerald-700 border-emerald-250/50";
      case "completed":
        return "bg-zinc-50 text-zinc-700 border-zinc-250/50";
      default:
        return "bg-amber-50 text-amber-700 border-amber-250/50";
    }
  };

  const getRecipientStatusBadge = (status: string) => {
    switch (status) {
      case "purchased":
        return (
          <span className="inline-flex items-center rounded bg-emerald-100 px-1.5 py-0.5 text-3xs font-semibold text-emerald-800 uppercase tracking-wider">
            Purchased
          </span>
        );
      case "clicked":
        return (
          <span className="inline-flex items-center rounded bg-blue-50 px-1.5 py-0.5 text-3xs font-semibold text-blue-700 uppercase tracking-wider">
            Clicked
          </span>
        );
      case "opened":
        return (
          <span className="inline-flex items-center rounded bg-emerald-50 px-1.5 py-0.5 text-3xs font-semibold text-emerald-700 uppercase tracking-wider">
            Opened
          </span>
        );
      case "delivered":
        return (
          <span className="inline-flex items-center rounded bg-indigo-50 px-1.5 py-0.5 text-3xs font-semibold text-indigo-700 uppercase tracking-wider">
            Delivered
          </span>
        );
      case "sent":
        return (
          <span className="inline-flex items-center rounded bg-zinc-50 px-1.5 py-0.5 text-3xs font-semibold text-zinc-650 uppercase tracking-wider">
            Sent
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center rounded bg-red-50 px-1.5 py-0.5 text-3xs font-semibold text-red-700 uppercase tracking-wider">
            Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded bg-amber-50 px-1.5 py-0.5 text-3xs font-semibold text-amber-700 uppercase tracking-wider">
            Queued
          </span>
        );
    }
  };

  const getChannelBadge = (channel: string) => {
    switch (channel?.toLowerCase()) {
      case "whatsapp":
        return (
          <span className="inline-flex items-center rounded bg-emerald-100 px-1.5 py-0.5 text-3xs font-semibold text-emerald-800 uppercase tracking-wider">
            WhatsApp
          </span>
        );
      case "sms":
        return (
          <span className="inline-flex items-center rounded bg-indigo-50 px-1.5 py-0.5 text-3xs font-semibold text-indigo-700 uppercase tracking-wider">
            SMS
          </span>
        );
      case "email":
        return (
          <span className="inline-flex items-center rounded bg-zinc-150 px-1.5 py-0.5 text-3xs font-semibold text-zinc-750 uppercase tracking-wider">
            Email
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded bg-zinc-50 px-1.5 py-0.5 text-3xs font-semibold text-zinc-600 uppercase tracking-wider">
            {channel || "Unknown"}
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col justify-center items-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900" />
        <span className="mt-4 text-xs font-medium text-zinc-500">
          Loading campaign details...
        </span>
      </div>
    );
  }

  if (error || !campaign) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50/50 p-6 text-center max-w-xl mx-auto my-10">
        <h3 className="text-sm font-semibold text-red-950">
          Error Loading Campaign
        </h3>
        <p className="mt-2 text-xs text-red-700 leading-relaxed">
          {error || "Campaign could not be found."}
        </p>
        <Link
          href="/dashboard"
          className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-white border border-zinc-200 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 transition-colors"
        >
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Campaign Detail Top Actions */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6 border-b border-zinc-200/80 pb-6">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="rounded-md border border-zinc-200 bg-white p-1.5 text-zinc-500 hover:text-zinc-950 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-900">
              {campaign.name}
            </h1>
            <p className="text-xs text-zinc-650 mt-1.5 font-medium">
              <span className="text-zinc-400 font-semibold uppercase tracking-wider text-4xs mr-1">
                Campaign Goal:
              </span>
              {campaign.goal}
            </p>
            <p className="text-xs text-zinc-650 mt-1 font-medium">
              <span className="text-zinc-400 font-semibold uppercase tracking-wider text-4xs mr-1">
                Target Segment:
              </span>
              {formatSegmentFilters(campaign.segment_filters)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {campaign.status === "launched" && stats && stats.sent > 0 && (
            <Link
              href={`/chat?goal=Retarget non-responders from campaign ${campaign.name} (ID: ${campaign.id})&retarget=true&campaign_id=${campaign.id}`}
              className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 transition-colors shadow-3xs"
            >
              <Sparkles className="h-3.5 w-3.5" />
              Retarget Non-Responders
            </Link>
          )}
          <span
            className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-semibold capitalize ${getStatusClass(campaign.status)}`}
          >
            {campaign.status}
          </span>
        </div>
      </div>

      {/* Campaign Completion / Outcome Summary Banner */}
      {stats && stats.total > 0 && (
        <div
          className={`rounded-lg border p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-3xs transition-all ${
            stats.queued > 0
              ? "border-amber-100 bg-amber-50/10 text-amber-900"
              : stats.roi_percentage > 0
                ? "border-emerald-100 bg-emerald-50/10 text-emerald-950"
                : "border-zinc-200 bg-zinc-50/40 text-zinc-800"
          }`}
        >
          <div className="flex items-center gap-3">
            <div
              className={`p-2 rounded-full ${
                stats.queued > 0
                  ? "bg-amber-100 text-amber-700"
                  : "bg-emerald-100 text-emerald-700"
              }`}
            >
              {stats.queued > 0 ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
            </div>
            <div>
              <h4 className="text-xs font-bold text-zinc-850">
                {stats.queued > 0
                  ? `Campaign dispatch in progress... (${stats.total - stats.queued} / ${stats.total} sent)`
                  : "Campaign Dispatch Completed!"}
              </h4>
              <p className="text-3xs text-zinc-500 mt-0.5">
                {stats.queued > 0
                  ? "Marketers can track live webhook delivery events as messages queue up in the background."
                  : stats.purchased > 0
                    ? `Recaptured ₹${stats.estimated_revenue.toLocaleString()} in revenue with a conversion rate of ${stats.conversion_rate}%.`
                    : "All messages successfully dispatched. Waiting for customers to convert."}
              </p>
            </div>
          </div>

          {stats.queued === 0 && (
            <div className="flex items-center gap-4 text-3xs border-t md:border-t-0 md:border-l border-zinc-200 pt-3 md:pt-0 md:pl-6">
              <div>
                <span className="text-zinc-400 block font-medium uppercase tracking-wider text-4xs">
                  Final Status
                </span>
                <span className="inline-flex items-center gap-1 mt-0.5 font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-150/50">
                  <span className="h-1 w-1 rounded-full bg-emerald-500 animate-pulse" />{" "}
                  Success
                </span>
              </div>
              <div>
                <span className="text-zinc-400 block font-medium uppercase tracking-wider text-4xs">
                  Delivered
                </span>
                <span className="font-bold text-zinc-800 block mt-0.5">
                  {stats.sent > 0
                    ? Math.round((stats.delivered / stats.sent) * 100)
                    : 0}
                  %
                </span>
              </div>
              <div>
                <span className="text-zinc-400 block font-medium uppercase tracking-wider text-4xs">
                  CTR
                </span>
                <span className="font-bold text-zinc-800 block mt-0.5">
                  {stats.click_rate}%
                </span>
              </div>
              <div>
                <span className="text-zinc-400 block font-medium uppercase tracking-wider text-4xs">
                  ROI
                </span>
                <span
                  className={`font-bold block mt-0.5 ${stats.roi_percentage >= 0 ? "text-emerald-650" : "text-red-500"}`}
                >
                  {stats.roi_percentage >= 0 ? "+" : ""}
                  {stats.roi_percentage}%
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* AI Campaign Performance Insight Section */}
      <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-3xs">
        <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
          <div className="flex items-center gap-2 text-zinc-950">
            <Sparkles className="h-4 w-4 text-indigo-600" />
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              AI Campaign Insight
            </h2>
          </div>
          {stats && stats.sent > 0 && (
            <button
              onClick={() => setInsightVersion((v) => v + 1)}
              disabled={insightLoading}
              className="inline-flex items-center gap-1 text-3xs font-semibold text-zinc-500 hover:text-zinc-950 hover:bg-zinc-50 border border-zinc-200 rounded px-2 py-0.5 transition-colors disabled:opacity-40 focus:outline-none"
            >
              <RefreshCw
                className={`h-2.5 w-2.5 ${insightLoading ? "animate-spin" : ""}`}
              />
              Refresh Insight
            </button>
          )}
        </div>
        <div className="mt-3">
          {insightLoading ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-3 w-3/4 bg-zinc-100 rounded" />
              <div className="h-3 w-1/2 bg-zinc-100 rounded" />
            </div>
          ) : stats && stats.sent === 0 ? (
            <p className="text-xs text-zinc-405 italic leading-relaxed">
              Campaign dispatch is still queuing up in the background.
              Performance insights will populate as delivery updates arrive.
            </p>
          ) : aiInsight ? (
            <p className="text-xs text-zinc-700 leading-relaxed font-medium">
              {aiInsight}
            </p>
          ) : (
            <p className="text-xs text-zinc-400 italic">
              No insight available. Polling stats to analyze outcomes...
            </p>
          )}
        </div>
      </div>

      {/* Main Stats Funnel Split Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
        {/* Left Funnel & Timeline (60%) */}
        <div className="lg:col-span-6 space-y-6">
          {stats ? (
            <FunnelChart stats={stats} />
          ) : (
            <div className="rounded-lg border border-zinc-200 bg-white p-6 h-60 flex items-center justify-center text-zinc-400 text-xs">
              No stats available
            </div>
          )}
          <TimelineChart data={getTimelineData()} />
        </div>

        {/* Right Metadata/Message Template (40%) */}
        <div className="lg:col-span-4 rounded-lg border border-zinc-200 bg-white p-6 space-y-6">
          {/* ROI & Business Impact Card */}
          {stats && (
            <div className="rounded-lg border border-emerald-100 bg-emerald-50/10 p-5 space-y-4 shadow-3xs">
              <h3 className="text-sm font-semibold text-emerald-900 flex items-center gap-1.5 border-b border-emerald-100/50 pb-2">
                <Sparkles className="h-4 w-4 text-emerald-600 animate-pulse" />
                ROI & Business Impact
              </h3>
              <div className="grid grid-cols-2 gap-4 text-2xs">
                <div>
                  <span className="text-zinc-400 block font-medium">
                    Est. Campaign Cost
                  </span>
                  <span className="text-xs font-bold text-zinc-700 mt-0.5 block">
                    ₹{(stats.estimated_cost || 0).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-400 block font-medium">
                    Est. Revenue Recaptured
                  </span>
                  <span className="text-xs font-bold text-zinc-900 mt-0.5 block">
                    ₹{(stats.estimated_revenue || 0).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-400 block font-medium">
                    Purchase Nexorans
                  </span>
                  <span className="text-xs font-bold text-zinc-800 mt-0.5 block">
                    {stats.purchased || 0} orders
                    <span className="text-3xs text-zinc-400 font-normal ml-1">
                      ({stats.conversion_rate || 0}%)
                    </span>
                  </span>
                </div>
                <div>
                  <span className="text-zinc-400 block font-medium">
                    ROI Factor
                  </span>
                  <span
                    className={`text-xs font-extrabold mt-0.5 block ${stats.roi_percentage >= 0 ? "text-emerald-650" : "text-red-500"}`}
                  >
                    {stats.roi_percentage >= 0 ? "+" : ""}
                    {(stats.roi_percentage || 0).toLocaleString()}%
                  </span>
                </div>
              </div>
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-1.5">
              <Layers className="h-4 w-4 text-zinc-400" />
              Campaign Configuration
            </h3>
            <div className="mt-4 space-y-3 text-2xs">
              <div className="flex justify-between border-b border-zinc-50 pb-2">
                <span className="text-zinc-400">Launch Date</span>
                <span className="font-semibold text-zinc-750">
                  {campaign.launched_at
                    ? new Date(campaign.launched_at).toLocaleString()
                    : "Not launched"}
                </span>
              </div>
              <div className="flex justify-between border-b border-zinc-50 pb-2">
                <span className="text-zinc-400">Target Segment</span>
                <span className="font-semibold text-zinc-750">
                  {campaign.segment_size} customers
                </span>
              </div>
              <div className="flex justify-between border-b border-zinc-50 pb-2">
                <span className="text-zinc-400">Cohort Filters</span>
                <span
                  className="font-semibold text-zinc-750 text-right font-mono text-3xs max-w-[200px] truncate"
                  title={formatSegmentFilters(campaign.segment_filters)}
                >
                  {formatSegmentFilters(campaign.segment_filters)}
                </span>
              </div>
              <div className="flex justify-between border-b border-zinc-50 pb-2">
                <span className="text-zinc-400">Delivery Channel</span>
                <span className="font-semibold text-zinc-750 capitalize">
                  {campaign.channel}
                </span>
              </div>
              <div className="flex justify-between border-b border-zinc-50 pb-2">
                <span className="text-zinc-400">Database ID</span>
                <span className="font-mono text-zinc-500 text-3xs">
                  {campaign.id}
                </span>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-1.5">
              <FileText className="h-4 w-4 text-zinc-400" />
              Message Template Copy
            </h3>
            {renderMessageTemplates()}
          </div>
        </div>
      </div>

      {/* Recipient Logs Communications Table */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-zinc-900">
            Campaign Dispatch Logs
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setRecipientPage((p) => Math.max(0, p - 1))}
              disabled={recipientPage === 0}
              className="rounded border border-zinc-200 bg-white p-1 text-zinc-500 hover:text-zinc-950 transition-colors disabled:opacity-40 focus:outline-none"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-2xs font-semibold text-zinc-700">
              Page {recipientPage + 1}
            </span>
            <button
              onClick={() => setRecipientPage((p) => p + 1)}
              disabled={recipients.length < RECIPIENT_LIMIT}
              className="rounded border border-zinc-200 bg-white p-1 text-zinc-500 hover:text-zinc-950 transition-colors disabled:opacity-40 focus:outline-none"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-left text-xs">
              <thead className="bg-zinc-50 text-zinc-500 font-medium uppercase tracking-wider text-3xs border-b border-zinc-200">
                <tr>
                  <th scope="col" className="px-6 py-3">
                    Customer Name
                  </th>
                  <th scope="col" className="px-6 py-3 hidden md:table-cell">
                    Contact
                  </th>
                  <th scope="col" className="px-6 py-3">
                    Channel
                  </th>
                  <th scope="col" className="px-6 py-3">
                    Status
                  </th>
                  <th scope="col" className="px-6 py-3 hidden sm:table-cell">
                    Delivered At
                  </th>
                  <th scope="col" className="px-6 py-3 hidden sm:table-cell">
                    Opened At
                  </th>
                  <th scope="col" className="px-6 py-3">
                    Message Preview
                  </th>
                  <th scope="col" className="px-6 py-3">
                    Simulate Ingestion
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 bg-white">
                {(() => {
                  const uniqueRecipients: RecipientLog[] = [];
                  const seenCustomers = new Set<string>();
                  recipients.forEach((rec) => {
                    if (!seenCustomers.has(rec.customer_name)) {
                      seenCustomers.add(rec.customer_name);
                      uniqueRecipients.push(rec);
                    }
                  });

                  if (uniqueRecipients.length > 0) {
                    return uniqueRecipients.map((rec) => {
                      const journey = getCustomerJourney(rec.customer_name);
                      const latestAttempt = journey[journey.length - 1] || rec;
                      return (
                        <tr
                          key={rec.id}
                          className="hover:bg-zinc-50/50 transition-colors"
                        >
                          <td className="whitespace-nowrap px-6 py-4 font-semibold text-zinc-900">
                            {rec.customer_name}
                          </td>
                          <td className="whitespace-nowrap px-6 py-4 text-zinc-500 font-medium hidden md:table-cell">
                            {latestAttempt.channel === "email"
                              ? latestAttempt.customer_email
                              : latestAttempt.customer_phone}
                          </td>
                          <td className="whitespace-nowrap px-6 py-4">
                            <div className="flex items-center gap-1.5">
                              {journey.map((item, idx) => (
                                <React.Fragment key={item.id}>
                                  {idx > 0 && (
                                    <span className="text-zinc-400 font-bold mx-0.5">
                                      ➔
                                    </span>
                                  )}
                                  <div className="flex flex-col items-start">
                                    {getChannelBadge(item.channel)}
                                    {idx > 0 && (
                                      <span className="text-4xs text-indigo-600 font-bold uppercase mt-0.5 tracking-wider">
                                        Fallback
                                      </span>
                                    )}
                                  </div>
                                </React.Fragment>
                              ))}
                            </div>
                          </td>
                          <td className="whitespace-nowrap px-6 py-4">
                            <div className="flex flex-col gap-1.5">
                              {journey.map((item, idx) => (
                                <div
                                  key={item.id}
                                  className="flex items-center gap-1.5 text-3xs text-zinc-500"
                                >
                                  <span className="font-semibold capitalize text-4xs">
                                    {item.channel}:
                                  </span>
                                  {getRecipientStatusBadge(item.status)}
                                  {idx === 0 &&
                                    journey.length > 1 &&
                                    ![
                                      "opened",
                                      "clicked",
                                      "purchased",
                                    ].includes(item.status) && (
                                      <span className="text-red-500 font-bold text-4xs lowercase italic">
                                        (unopened)
                                      </span>
                                    )}
                                </div>
                              ))}
                            </div>
                          </td>
                          <td className="whitespace-nowrap px-6 py-4 text-zinc-400 hidden sm:table-cell">
                            {latestAttempt.delivered_at
                              ? new Date(
                                  latestAttempt.delivered_at,
                                ).toLocaleTimeString()
                              : "-"}
                          </td>
                          <td className="whitespace-nowrap px-6 py-4 text-zinc-400 hidden sm:table-cell">
                            {latestAttempt.opened_at
                              ? new Date(
                                  latestAttempt.opened_at,
                                ).toLocaleTimeString()
                              : "-"}
                          </td>
                          <td className="whitespace-nowrap px-6 py-4">
                            <div className="flex flex-col gap-1.5">
                              {journey.map((item) => (
                                <button
                                  key={item.id}
                                  onClick={() => setSelectedRecipient(item)}
                                  className="inline-flex items-center gap-1 rounded border border-zinc-200 bg-white hover:bg-zinc-50 px-2 py-0.5 text-3xs font-semibold text-zinc-750 transition-colors shadow-3xs w-fit"
                                >
                                  <FileText className="h-3 w-3 text-zinc-400" />
                                  Preview {item.channel.toUpperCase()}
                                </button>
                              ))}
                            </div>
                          </td>
                          <td className="whitespace-nowrap px-6 py-4">
                            <div className="flex flex-col gap-1.5">
                              {journey.map((item) => (
                                <div
                                  key={item.id}
                                  className="h-6 flex items-center gap-1.5"
                                >
                                  {item.status === "sent" && (
                                    <button
                                      disabled={simulatingId !== null}
                                      onClick={() =>
                                        triggerSimulation(item.id, "delivered")
                                      }
                                      className="px-2 py-0.5 rounded border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 text-3xs font-semibold text-indigo-700 disabled:opacity-40 transition-colors shadow-3xs"
                                    >
                                      {simulatingId === `${item.id}-delivered`
                                        ? "Delivering..."
                                        : `Deliver ${item.channel.toUpperCase()}`}
                                    </button>
                                  )}
                                  {item.status === "delivered" && (
                                    <button
                                      disabled={simulatingId !== null}
                                      onClick={() =>
                                        triggerSimulation(item.id, "opened")
                                      }
                                      className="px-2 py-0.5 rounded border border-emerald-250 bg-emerald-50 hover:bg-emerald-100 text-3xs font-semibold text-emerald-750 disabled:opacity-40 transition-colors shadow-3xs"
                                    >
                                      {simulatingId === `${item.id}-opened`
                                        ? "Opening..."
                                        : `Open ${item.channel.toUpperCase()}`}
                                    </button>
                                  )}
                                  {item.status === "opened" && (
                                    <button
                                      disabled={simulatingId !== null}
                                      onClick={() =>
                                        triggerSimulation(item.id, "clicked")
                                      }
                                      className="px-2 py-0.5 rounded border border-blue-200 bg-blue-50 hover:bg-blue-100 text-3xs font-semibold text-blue-750 disabled:opacity-40 transition-colors shadow-3xs"
                                    >
                                      {simulatingId === `${item.id}-clicked`
                                        ? "Clicking..."
                                        : `Click ${item.channel.toUpperCase()}`}
                                    </button>
                                  )}
                                  {item.status === "clicked" && (
                                    <button
                                      disabled={simulatingId !== null}
                                      onClick={() =>
                                        triggerSimulation(item.id, "purchased")
                                      }
                                      className="px-2 py-0.5 rounded border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-3xs font-semibold text-emerald-750 disabled:opacity-40 transition-colors shadow-3xs"
                                    >
                                      {simulatingId === `${item.id}-purchased`
                                        ? "Purchasing..."
                                        : "Purchase"}
                                    </button>
                                  )}
                                  {["sent", "delivered"].includes(
                                    item.status,
                                  ) && (
                                    <button
                                      disabled={simulatingId !== null}
                                      onClick={() =>
                                        triggerSimulation(item.id, "failed")
                                      }
                                      className="px-2 py-0.5 rounded border border-red-200 bg-red-50 hover:bg-red-100 text-3xs font-semibold text-red-650 disabled:opacity-40 transition-colors shadow-3xs"
                                    >
                                      {simulatingId === `${item.id}-failed`
                                        ? "Failing..."
                                        : "Fail"}
                                    </button>
                                  )}
                                  {item.status === "queued" && (
                                    <span className="text-3xs text-zinc-400 font-medium italic">
                                      Pending...
                                    </span>
                                  )}
                                  {![
                                    "queued",
                                    "sent",
                                    "delivered",
                                    "opened",
                                    "clicked",
                                  ].includes(item.status) && (
                                    <span className="text-4xs text-zinc-400 font-medium italic">
                                      - Completed -
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      );
                    });
                  }
                  return (
                    <tr>
                      <td
                        colSpan={7}
                        className="px-6 py-8 text-center text-zinc-400 italic"
                      >
                        No customer communications logged yet. Dispatch starting
                        shortly...
                      </td>
                    </tr>
                  );
                })()}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Modal Popup for Personalized Message Preview */}
      {selectedRecipient && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/40 backdrop-blur-xs p-4 transition-all">
          <div className="bg-white rounded-lg border border-zinc-200 shadow-xl max-w-sm w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="bg-zinc-50 border-b border-zinc-200 px-4 py-3 flex items-center justify-between">
              <div>
                <h4 className="text-xs font-semibold text-zinc-900">
                  Personalized Message Preview
                </h4>
                <p className="text-4xs text-zinc-450 mt-0.5">
                  Recipient: {selectedRecipient.customer_name}
                </p>
              </div>
              <button
                onClick={() => setSelectedRecipient(null)}
                className="text-zinc-450 hover:text-zinc-650 font-semibold text-sm p-1.5 focus:outline-none"
              >
                ✕
              </button>
            </div>
            {/* Mock Container */}
            <div className="p-5 bg-zinc-100/50">
              {selectedRecipient.channel === "email" ? (
                <div className="border border-zinc-200 rounded-md bg-white shadow-3xs overflow-hidden text-2xs">
                  <div className="bg-zinc-50 border-b border-zinc-100 p-3 space-y-1 text-zinc-500 font-medium">
                    <div>
                      <span className="text-zinc-450 mr-1 font-medium">
                        To:
                      </span>{" "}
                      {selectedRecipient.customer_email || "customer@email.com"}
                    </div>
                    <div className="text-zinc-850">
                      <span className="text-zinc-450 mr-1 font-medium">
                        Subject:
                      </span>{" "}
                      {selectedRecipient.message.startsWith("SUBJECT:")
                        ? selectedRecipient.message
                            .split("|")[0]
                            .replace("SUBJECT:", "")
                            .trim()
                        : "Campaign Offer"}
                    </div>
                  </div>
                  <div className="p-4 min-h-[120px] text-zinc-750 leading-relaxed whitespace-pre-wrap font-sans">
                    {selectedRecipient.message.includes("BODY:")
                      ? selectedRecipient.message.split("BODY:")[1].trim()
                      : selectedRecipient.message}
                  </div>
                </div>
              ) : selectedRecipient.channel === "whatsapp" ? (
                <div className="border border-zinc-200 rounded-md bg-[#efeae2] shadow-3xs overflow-hidden">
                  <div className="bg-emerald-800 text-white px-3 py-2 text-2xs font-semibold flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 animate-pulse" />
                    WhatsApp Business
                  </div>
                  <div className="p-4 flex flex-col justify-end min-h-[140px]">
                    <div className="bg-white rounded-lg p-2.5 shadow-3xs border border-zinc-150/50 text-2xs text-zinc-800 relative max-w-[90%]">
                      <div className="absolute top-0 -left-1.5 w-0 h-0 border-t-[6px] border-t-white border-l-[6px] border-l-transparent" />
                      <p className="whitespace-pre-wrap leading-relaxed font-sans">
                        {selectedRecipient.message}
                      </p>
                      <span className="text-4xs text-zinc-450 block text-right mt-1 font-mono">
                        {new Date().toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="border border-zinc-200 rounded-md bg-white shadow-3xs overflow-hidden">
                  <div className="bg-zinc-50 border-b border-zinc-100 py-1.5 text-center text-4xs font-bold uppercase tracking-widest text-zinc-400">
                    Text Message
                  </div>
                  <div className="p-4 flex flex-col justify-end min-h-[140px] bg-zinc-50/20">
                    <div className="bg-zinc-100 rounded-xl px-3 py-2 text-2xs text-zinc-800 leading-relaxed self-start max-w-[85%] whitespace-pre-wrap font-sans">
                      {selectedRecipient.message}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
