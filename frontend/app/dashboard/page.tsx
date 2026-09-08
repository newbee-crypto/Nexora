"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TrendingUp, Users, Inbox, ArrowRight, Activity, Layers, Database, RefreshCw, Trash2, X, AlertTriangle, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import OpportunityCard, { Opportunity } from "../../components/OpportunityCard";
import FunnelChart from "../../components/FunnelChart";

interface CampaignSummary {
  id: string;
  name: string;
  goal: string;
  channel: string;
  status: string;
  segment_size: number;
  created_at: string;
  launched_at: string | null;
}

interface OpportunityResponse {
  opportunities: Opportunity[];
  summary: {
    total_opportunities: number;
    total_addressable_audience: number;
    total_estimated_recovery_inr: number;
  };
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
  conversion_rate?: number;
  estimated_cost?: number;
  estimated_revenue?: number;
  roi_percentage?: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DashboardPage() {
  const router = useRouter();
  const [oppData, setOppData] = useState<OpportunityResponse | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [oppLoading, setOppLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshingOpportunities, setIsRefreshingOpportunities] = useState(false);

  const handleRefreshOpportunities = async () => {
    setIsRefreshingOpportunities(true);
    try {
      const res = await fetch(`${API_BASE}/opportunities?refresh=true`);
      if (!res.ok) throw new Error("Failed to refresh opportunities");
      const json = await res.json();
      setOppData(json);
    } catch (err) {
      console.error(err);
    } finally {
      setIsRefreshingOpportunities(false);
    }
  };

  // Latest campaign stats for live dashboard analytics
  const [latestLaunchedCampaign, setLatestLaunchedCampaign] = useState<CampaignSummary | null>(null);
  const [latestStats, setLatestStats] = useState<CampaignStats | null>(null);

  // Manage database states
  const [isManageModalOpen, setIsManageModalOpen] = useState(false);
  const [resetType, setResetType] = useState<"campaigns" | "database" | null>(null);
  const [confirmInput, setConfirmInput] = useState("");
  const [resetting, setResetting] = useState(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const resetState = () => {
    setResetType(null);
    setConfirmInput("");
    setResetting(false);
    setActionSuccess(null);
    setActionError(null);
  };

  const fetchOpportunities = async (showLoading = true) => {
    if (showLoading) setOppLoading(true);
    try {
      const oppRes = await fetch(`${API_BASE}/opportunities`);
      if (!oppRes.ok) throw new Error("Failed to fetch opportunities");
      const oppJson = await oppRes.json();
      setOppData(oppJson);
    } catch (err) {
      console.error("Failed to fetch opportunities:", err);
    } finally {
      if (showLoading) setOppLoading(false);
    }
  };

  const fetchDashboardData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      // Fetch campaigns
      const campRes = await fetch(`${API_BASE}/campaigns`);
      if (!campRes.ok) throw new Error("Failed to fetch campaigns");
      const campJson = await campRes.json();
      setCampaigns(campJson);

      // Find the most recently launched/completed campaign for dashboard analytics
      const launched = campJson.find((c: CampaignSummary) => c.status !== "draft");
      if (launched) {
        setLatestLaunchedCampaign(launched);
        // Fetch stats for this campaign
        const statsRes = await fetch(`${API_BASE}/campaigns/${launched.id}/stats`);
        if (statsRes.ok) {
          const statsJson = await statsRes.json();
          setLatestStats(statsJson);
        } else {
          setLatestStats(null);
        }
      } else {
        setLatestLaunchedCampaign(null);
        setLatestStats(null);
      }
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Something went wrong. Make sure the CRM backend is running on port 8000.");
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const fetchData = async (showLoading = true) => {
    fetchDashboardData(showLoading);
    fetchOpportunities(showLoading);
  };

  useEffect(() => {
    fetchData(true);
  }, []);

  const handleExecuteReset = async () => {
    if (!resetType) return;
    try {
      setResetting(true);
      setActionError(null);
      const endpoint = resetType === "campaigns" ? "/campaigns/reset" : "/campaigns/reset-db";
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Reset operation failed");
      }

      const json = await res.json();
      setActionSuccess(json.message || "Reset completed successfully.");
      
      // Reload dashboard data in the background
      await fetchData(false);
    } catch (err: any) {
      console.error(err);
      setActionError(err.message || "Something went wrong during reset.");
    } finally {
      setResetting(false);
    }
  };


  // Poll stats for the latest campaign if active
  useEffect(() => {
    let interval: NodeJS.Timeout;
    async function fetchLatestStats() {
      if (!latestLaunchedCampaign) return;
      try {
        const res = await fetch(`${API_BASE}/campaigns/${latestLaunchedCampaign.id}/stats`);
        if (res.ok) {
          const json = await res.json();
          setLatestStats(json);
        }
      } catch (err) {
        console.error("Failed to fetch dashboard funnel stats:", err);
      }
    }

    if (latestLaunchedCampaign && latestLaunchedCampaign.status === "launched") {
      fetchLatestStats(); // Immediate fetch
      interval = setInterval(fetchLatestStats, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [latestLaunchedCampaign]);

  const handleOpportunitySelect = (goal: string) => {
    // Redirect to chat with pre-filled goal query param
    router.push(`/chat?goal=${encodeURIComponent(goal)}`);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "launched":
        return (
          <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
            Launched
          </span>
        );
      case "completed":
        return (
          <span className="inline-flex items-center rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-700 ring-1 ring-inset ring-zinc-600/20">
            Completed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-600/20">
            Draft
          </span>
        );
    }
  };

  const getChannelBadge = (channel: string) => {
    switch (channel) {
      case "whatsapp":
        return (
          <span className="inline-flex items-center rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-700/10">
            WhatsApp
          </span>
        );
      case "email":
        return (
          <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 ring-1 ring-inset ring-blue-700/10">
            Email
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded-md bg-zinc-50 px-2 py-1 text-xs font-medium text-zinc-700 ring-1 ring-inset ring-zinc-700/10">
            SMS
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col justify-center items-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900" />
        <span className="mt-4 text-xs font-medium text-zinc-500">Loading dashboard data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50/50 p-6 text-center max-w-xl mx-auto my-10">
        <h3 className="text-sm font-semibold text-red-950">Connection Error</h3>
        <p className="mt-2 text-xs text-red-700 leading-relaxed">
          {error}
        </p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-white border border-zinc-200 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 transition-colors"
        >
          Try Again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-10">
      {/* Dashboard Top Header & Summary Card */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6 border-b border-zinc-200/80 pb-6">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-900">Campaign Dashboard</h1>
          <p className="text-xs text-zinc-500 mt-1">Overview of AI opportunities and customer engagement campaigns</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setIsManageModalOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-white border border-zinc-200 px-3.5 py-2 text-xs font-semibold text-zinc-700 shadow-xs hover:bg-zinc-50 hover:border-zinc-300 transition-all cursor-pointer"
          >
            <Database className="h-3.5 w-3.5 text-zinc-500" />
            Manage Database
          </button>
          <Link
            href="/chat"
            className="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 py-2 text-xs font-semibold text-white shadow-xs hover:bg-zinc-800 transition-colors"
          >
            Launch Copilot Chat
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>

      {/* Aggregate Stats Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="rounded-lg border border-zinc-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500">Addressable Recovery</span>
            <div className="rounded-md border border-zinc-150 p-1 bg-zinc-50">
              <TrendingUp className="h-4 w-4 text-zinc-600" />
            </div>
          </div>
          <div className="mt-3">
            {oppLoading ? (
              <div className="space-y-2">
                <div className="h-8 w-28 bg-zinc-100 animate-pulse rounded" />
                <div className="h-3 w-40 bg-zinc-100 animate-pulse rounded" />
              </div>
            ) : (
              <>
                <span className="text-2xl font-semibold tracking-tight text-zinc-950">
                  ₹{oppData?.summary.total_estimated_recovery_inr.toLocaleString() || "0"}
                </span>
                <p className="text-3xs text-zinc-400 mt-1">Projected revenue across {oppData?.summary.total_opportunities || 0} segments</p>
              </>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500">Targetable Audience</span>
            <div className="rounded-md border border-zinc-150 p-1 bg-zinc-50">
              <Users className="h-4 w-4 text-zinc-600" />
            </div>
          </div>
          <div className="mt-3">
            {oppLoading ? (
              <div className="space-y-2">
                <div className="h-8 w-24 bg-zinc-100 animate-pulse rounded" />
                <div className="h-3 w-44 bg-zinc-100 animate-pulse rounded" />
              </div>
            ) : (
              <>
                <span className="text-2xl font-semibold tracking-tight text-zinc-950">
                  {oppData?.summary.total_addressable_audience.toLocaleString() || "0"}
                </span>
                <p className="text-3xs text-zinc-400 mt-1">Total active customer profiles targeted</p>
              </>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500">Total Campaigns</span>
            <div className="rounded-md border border-zinc-150 p-1 bg-zinc-50">
              <Layers className="h-4 w-4 text-zinc-600" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-semibold tracking-tight text-zinc-950">
              {campaigns.length}
            </span>
            <p className="text-3xs text-zinc-400 mt-1">Draft, launched, and completed workflows</p>
          </div>
        </div>
      </div>

      {/* Analytics & Opportunities Section */}
      <div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
        {/* Left: Latest Campaign Funnel (60%) */}
        <div className="lg:col-span-6 space-y-4">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-zinc-400" />
            <h2 className="text-sm font-semibold text-zinc-900">Latest Campaign Performance</h2>
          </div>
          {latestLaunchedCampaign ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-zinc-200 bg-white p-4 flex justify-between items-center text-xs">
                <div className="min-w-0 flex-1 pr-4">
                  <span className="font-semibold text-zinc-900 block truncate">{latestLaunchedCampaign.name}</span>
                  <span className="text-zinc-500 text-3xs mt-0.5 block truncate">Goal: {latestLaunchedCampaign.goal}</span>
                </div>
                <Link
                  href={`/campaigns/${latestLaunchedCampaign.id}`}
                  className="shrink-0 rounded border border-zinc-200 bg-white px-2.5 py-1.5 font-semibold text-indigo-600 hover:text-indigo-850 hover:bg-zinc-50 transition-colors text-3xs"
                >
                  View Full Analytics
                </Link>
              </div>
              {latestStats ? (
                <FunnelChart stats={latestStats} />
              ) : (
                <div className="h-48 bg-white border border-zinc-200 rounded-lg animate-pulse flex items-center justify-center text-xs text-zinc-400">
                  Loading latest campaign stats...
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-zinc-200 bg-white p-8 text-center text-zinc-400 text-xs h-[320px] flex flex-col justify-center items-center">
              <Activity className="h-8 w-8 text-zinc-300 mb-3" />
              <p className="font-semibold text-zinc-700">No campaigns launched yet</p>
              <p className="mt-1 max-w-xs text-3xs text-zinc-450 leading-relaxed">
                Launch your first campaign using the AI Campaign Copilot to view live funnel tracking and conversion statistics here.
              </p>
              <Link
                href="/chat"
                className="mt-4 rounded-md bg-zinc-900 px-3.5 py-1.5 font-semibold text-white hover:bg-zinc-800 transition-colors text-3xs"
              >
                Launch Copilot Chat
              </Link>
            </div>
          )}
        </div>

        {/* Right: Recommended Opportunities (40%) */}
        <div className="lg:col-span-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-zinc-450" />
              <h2 className="text-sm font-semibold text-zinc-900">Recommended Opportunities</h2>
            </div>
            <button
              onClick={handleRefreshOpportunities}
              disabled={isRefreshingOpportunities || oppLoading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-4xs font-bold text-zinc-650 hover:bg-zinc-50 hover:text-zinc-950 transition-colors disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2 cursor-pointer shadow-3xs"
              title="Generate new dynamic campaign opportunities using AI"
            >
              <RefreshCw className={`h-3 w-3 ${isRefreshingOpportunities || oppLoading ? "animate-spin text-indigo-600" : ""}`} />
              {isRefreshingOpportunities || oppLoading ? "Refreshing..." : "AI Refresh"}
            </button>
          </div>
          <div className="flex flex-col gap-4 relative min-h-[150px]">
            {isRefreshingOpportunities && (
              <div className="absolute inset-0 bg-white/70 backdrop-blur-xs flex items-center justify-center z-10 rounded-lg">
                <div className="flex flex-col items-center gap-2 text-zinc-600 text-3xs font-semibold">
                  <RefreshCw className="h-5 w-5 animate-spin text-indigo-600" />
                  <span>AI is scanning directory patterns...</span>
                </div>
              </div>
            )}
            {oppLoading ? (
              <div className="flex flex-col gap-4 w-full">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="border border-zinc-200 bg-white rounded-lg p-5 animate-pulse space-y-4">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <div className="h-6 w-6 bg-zinc-100 rounded-md animate-pulse" />
                        <div className="h-4 w-24 bg-zinc-100 rounded animate-pulse" />
                      </div>
                      <div className="text-right space-y-1">
                        <div className="h-2 w-12 bg-zinc-100 rounded ml-auto animate-pulse" />
                        <div className="h-4 w-16 bg-zinc-100 rounded ml-auto animate-pulse" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="h-4 w-1/3 bg-zinc-150 rounded animate-pulse" />
                      <div className="h-3 w-full bg-zinc-100 rounded animate-pulse" />
                      <div className="h-3 w-5/6 bg-zinc-100 rounded animate-pulse" />
                    </div>
                    <div className="h-8 w-full bg-zinc-100 rounded-md mt-4 animate-pulse" />
                  </div>
                ))}
              </div>
            ) : oppData?.opportunities && oppData.opportunities.length > 0 ? (
              oppData.opportunities.slice(0, 3).map((opp) => (
                <OpportunityCard
                  key={opp.id}
                  opportunity={opp}
                  onSelect={handleOpportunitySelect}
                />
              ))
            ) : (
              <div className="border border-dashed border-zinc-200 rounded-lg p-6 text-center bg-white text-zinc-400 text-xs">
                No revenue opportunities detected. Seeding data is required.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Campaigns Section */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Inbox className="h-4 w-4 text-zinc-400" />
          <h2 className="text-sm font-semibold text-zinc-900">Recent Campaigns</h2>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-left text-xs">
              <thead className="bg-zinc-50 text-zinc-500 font-medium uppercase tracking-wider text-3xs border-b border-zinc-200">
                <tr>
                  <th scope="col" className="px-6 py-3">Campaign Name</th>
                  <th scope="col" className="px-6 py-3">Channel</th>
                  <th scope="col" className="px-6 py-3">Audience Size</th>
                  <th scope="col" className="px-6 py-3">Status</th>
                  <th scope="col" className="px-6 py-3 hidden sm:table-cell">Launch Date</th>
                  <th scope="col" className="px-6 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 bg-white">
                {campaigns.length > 0 ? (
                  campaigns.map((camp) => (
                    <tr key={camp.id} className="hover:bg-zinc-50/50 transition-colors">
                      <td className="whitespace-nowrap px-6 py-4 font-semibold text-zinc-900">
                        {camp.name}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        {getChannelBadge(camp.channel)}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 font-medium text-zinc-650">
                        {camp.segment_size} customers
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        {getStatusBadge(camp.status)}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-zinc-500 hidden sm:table-cell">
                        {camp.launched_at
                          ? new Date(camp.launched_at).toLocaleString()
                          : "Not launched"}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-right">
                        {camp.status !== "draft" ? (
                          <Link
                            href={`/campaigns/${camp.id}`}
                            className="inline-flex items-center gap-1 font-semibold text-indigo-600 hover:text-indigo-850 transition-colors"
                          >
                            View Funnel
                            <ArrowRight className="h-3 w-3" />
                          </Link>
                        ) : (
                          <span className="text-zinc-400 italic">Draft state</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="px-6 py-10 text-center text-zinc-400">
                      No campaigns have been created yet. Launch the Copilot Chat to get started.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Manage Database Modal */}
      {isManageModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="w-full max-w-lg rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl animate-in fade-in duration-200 text-left">
            <div className="flex items-center justify-between border-b border-zinc-150 pb-4 mb-5">
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-zinc-900" />
                <h2 className="text-base font-bold text-zinc-900">Manage System Database</h2>
              </div>
              <button
                onClick={() => {
                  if (!resetting) {
                    setIsManageModalOpen(false);
                    resetState();
                  }
                }}
                className="rounded-lg p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 transition-colors cursor-pointer"
                disabled={resetting}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {actionSuccess ? (
              <div className="space-y-4 py-4 text-center">
                <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200">
                  <CheckCircle2 className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-zinc-900">Success!</h3>
                  <p className="text-xs text-zinc-500 mt-1">{actionSuccess}</p>
                </div>
                <button
                  onClick={() => {
                    setIsManageModalOpen(false);
                    resetState();
                  }}
                  className="w-full rounded-md bg-zinc-900 py-2 text-xs font-semibold text-white hover:bg-zinc-800 transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            ) : resetType ? (
              <div className="space-y-5">
                <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-xs text-amber-800 flex gap-2.5">
                  <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" />
                  <div>
                    <span className="font-semibold block">Warning: Destructive Action</span>
                    <p className="mt-1 text-zinc-600 leading-relaxed">
                      {resetType === "campaigns"
                        ? "This will permanently delete all campaigns, communication dispatches, and receipt history logs. Customer records and orders will be preserved."
                        : "This will completely wipe all customers, orders, campaigns, and logs, then re-seed the system with the clean baseline 400 Indian customer profiles and orders."}
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-700 block">
                    Type <span className="font-mono text-zinc-900 bg-zinc-100 px-1.5 py-0.5 rounded border border-zinc-200">{resetType === "campaigns" ? "RESET" : "RESEED"}</span> to confirm:
                  </label>
                  <input
                    type="text"
                    value={confirmInput}
                    onChange={(e) => setConfirmInput(e.target.value)}
                    placeholder={resetType === "campaigns" ? "RESET" : "RESEED"}
                    className="w-full rounded-lg border border-zinc-200 px-3.5 py-2 text-xs bg-zinc-50/50 focus:bg-white focus:outline-none focus:ring-1 focus:ring-zinc-900 transition-all font-mono"
                    disabled={resetting}
                  />
                </div>

                {actionError && (
                  <p className="text-xs text-red-650 font-medium">{actionError}</p>
                )}

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => {
                      setResetType(null);
                      setConfirmInput("");
                      setActionError(null);
                    }}
                    className="flex-1 rounded-md border border-zinc-200 bg-white py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 transition-colors cursor-pointer"
                    disabled={resetting}
                  >
                    Back
                  </button>
                  <button
                    onClick={handleExecuteReset}
                    disabled={resetting || confirmInput !== (resetType === "campaigns" ? "RESET" : "RESEED")}
                    className={`flex-1 rounded-md py-2 text-xs font-semibold text-white transition-colors flex items-center justify-center gap-1.5 cursor-pointer ${
                      confirmInput === (resetType === "campaigns" ? "RESET" : "RESEED")
                        ? "bg-red-600 hover:bg-red-700"
                        : "bg-zinc-300 cursor-not-allowed"
                    }`}
                  >
                    {resetting ? (
                      <>
                        <RefreshCw className="h-3 w-3 animate-spin" />
                        Resetting...
                      </>
                    ) : (
                      <>
                        <Trash2 className="h-3.5 w-3.5" />
                        Confirm Reset
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                <p className="text-xs text-zinc-500 leading-relaxed">
                  Select one of the system reset options below. Make sure to back up any necessary data before proceeding.
                </p>

                <div className="grid grid-cols-1 gap-4">
                  <button
                    onClick={() => setResetType("campaigns")}
                    className="flex flex-col text-left p-4 rounded-lg border border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50/40 transition-colors group cursor-pointer"
                  >
                    <span className="text-xs font-semibold text-zinc-900 flex items-center gap-1.5">
                      <Trash2 className="h-3.5 w-3.5 text-zinc-500 group-hover:text-red-500 transition-colors" />
                      Reset Campaign History to Zero
                    </span>
                    <span className="text-3xs text-zinc-500 mt-1 leading-relaxed">
                      Clears all campaigns, dispatched messages, and live webhook logs. Keeps customer and order history untouched.
                    </span>
                  </button>

                  <button
                    onClick={() => setResetType("database")}
                    className="flex flex-col text-left p-4 rounded-lg border border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50/40 transition-colors group cursor-pointer"
                  >
                    <span className="text-xs font-semibold text-zinc-900 flex items-center gap-1.5">
                      <RefreshCw className="h-3.5 w-3.5 text-zinc-500 group-hover:text-indigo-650 transition-colors" />
                      Full Database Re-seed
                    </span>
                    <span className="text-3xs text-zinc-500 mt-1 leading-relaxed">
                      Truncates all tables and re-seeds the database with 400 default Indian customer profiles and historical orders.
                    </span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

