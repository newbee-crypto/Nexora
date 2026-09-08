"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Sparkles,
  Database,
  MessageSquare,
  Route,
  RefreshCw,
  Send,
  CheckCircle2,
  TrendingUp,
} from "lucide-react";

interface SampleGoal {
  id: string;
  title: string;
  goalText: string;
  filters: any;
  audienceCount: number;
  avgSpend: number;
  channel: string;
  channelReason: string;
  variantA: string;
  variantB: string;
  estimatedCost: number;
  conversions: number;
  revenue: number;
  roi: number;
}

const SAMPLE_GOALS: SampleGoal[] = [
  {
    id: "winback",
    title: "Win Back Inactive Customers",
    goalText: "Win back customers who haven't ordered in 45 days",
    filters: { inactive_days: 45, min_orders: 1 },
    audienceCount: 180,
    avgSpend: 2450,
    channel: "whatsapp",
    channelReason:
      "WhatsApp is recommended for smaller segments (< 500) to ensure high open rates (55%+ in India).",
    variantA:
      "Hi {{name}}, we miss you! It's been a while since your last purchase on {{last_order_date}}. Use code {{discount_code}} for 15% off to welcome you back!",
    variantB:
      "Hey {{name}}! We noticed you haven't shopped in a bit. Here is a special 15% discount code: {{discount_code}} valid for 48 hours. Last order: {{last_order_date}}.",
    estimatedCost: 144.0, // 180 * 0.80
    conversions: 18, // 10% conversion
    revenue: 44100, // 18 * 2450
    roi: 30525, // (44100-144)/144 * 100
  },
  {
    id: "loyalty",
    title: "Reward Frequent Loyal Buyers",
    goalText: "Send a free gift to customers who bought more than 3 times",
    filters: { min_orders: 3 },
    audienceCount: 247,
    avgSpend: 5983,
    channel: "whatsapp",
    channelReason:
      "High-value small segment (average spend ₹5,983). WhatsApp delivers a premium, personal touch.",
    variantA:
      "Hi {{name}}! 🎁 As one of our top customers, we have a special free gift waiting for you on your next order! Use code {{discount_code}} to claim it.",
    variantB:
      "Hey {{name}}! Thank you for shopping with us more than 3 times. Claim your exclusive free gift using code {{discount_code}} today. Last ordered: {{last_order_date}}.",
    estimatedCost: 197.6,
    conversions: 37,
    revenue: 221371,
    roi: 111930,
  },
  {
    id: "vip",
    title: "Offer High-Value Spenders 50% Off",
    goalText: "send a 50 percent discount to vip customers who spent over 5000",
    filters: { min_spent: 5000, tags: ["vip"] },
    audienceCount: 125,
    avgSpend: 8420,
    channel: "sms",
    channelReason:
      "Configured for direct, high-urgency notifications. Reaches customer devices instantly.",
    variantA:
      "Nexora: Hi {{name}}, enjoy VIP-only 50% off your next purchase. Use code {{discount_code}}. Reply STOP to opt out",
    variantB:
      "Nexora: Hey {{name}}! Thank you for your loyalty. Get 50% off your purchase with code {{discount_code}}. Reply STOP to opt out",
    estimatedCost: 25.0, // 125 * 0.20
    conversions: 15,
    revenue: 126300,
    roi: 505100,
  },
];

export default function MarketingLandingPage() {
  const [activeStep, setActiveStep] = useState(0);
  const [selectedGoal, setSelectedGoal] = useState<SampleGoal>(SAMPLE_GOALS[0]);
  const [typedMessage, setTypedMessage] = useState(SAMPLE_GOALS[0].goalText);

  const handleSelectGoal = (goal: SampleGoal) => {
    setSelectedGoal(goal);
    setTypedMessage(goal.goalText);
    setActiveStep(1); // Auto advance to Segment step to show database response
  };

  const steps = [
    {
      label: "1. Define Goal",
      icon: <MessageSquare className="h-4 w-4" />,
      description: "Write your campaign objective in plain English.",
    },
    {
      label: "2. Query Segment",
      icon: <Database className="h-4 w-4" />,
      description: "AI extracts SQL parameters and queries the DB.",
    },
    {
      label: "3. Choose Channel",
      icon: <Route className="h-4 w-4" />,
      description: "Intelligent routing based on audience metrics.",
    },
    {
      label: "4. Generate Copy",
      icon: <Sparkles className="h-4 w-4" />,
      description: "AI drafts personalized A/B variations.",
    },
    {
      label: "5. Dispatch & Funnel",
      icon: <Send className="h-4 w-4" />,
      description: "Asynchronous delivery and live ROI webhooks.",
    },
  ];

  return (
    <div className="space-y-0 -mt-4 pb-16">
      {/* Hero Section with Premium dot-grid and ambient glows */}
      <section className="relative isolate overflow-hidden text-center max-w-5xl mx-auto px-4 py-20 sm:py-28 rounded-2xl border border-zinc-200/35 bg-white/50 backdrop-blur-xs shadow-[0_1px_3px_rgba(0,0,0,0.02)] mb-12">
        {/* Subtle dot grid pattern */}
        <div className="absolute inset-0 -z-10 [mask-image:radial-gradient(100%_100%_at_top_center,white,transparent)] pointer-events-none select-none">
          <svg
            className="absolute inset-0 h-full w-full fill-zinc-350/12"
            aria-hidden="true"
          >
            <defs>
              <pattern
                id="dot-grid"
                width={20}
                height={20}
                patternUnits="userSpaceOnUse"
                x="50%"
                y={-1}
              >
                <circle cx={1.5} cy={1.5} r={0.75} />
              </pattern>
            </defs>
            <rect
              width="100%"
              height="100%"
              strokeWidth={0}
              fill="url(#dot-grid)"
            />
          </svg>
        </div>

        {/* Ambient Glowing Blobs */}
        <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-[350px] h-[350px] bg-indigo-200/15 rounded-full blur-3xl -z-10 pointer-events-none select-none" />
        <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-[350px] h-[350px] bg-purple-200/15 rounded-full blur-3xl -z-10 pointer-events-none select-none" />

        <div className="relative z-10 max-w-4xl mx-auto">
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-zinc-950 leading-tight">
            AI-Native Campaign Orchestration &amp; <br />
            <span className="inline-block px-1 pb-1 bg-gradient-to-r from-indigo-650 via-indigo-600 to-purple-650 bg-clip-text text-transparent">
              Real-Time Nexoran CRM
            </span>
          </h1>
          <p className="mt-6 text-sm sm:text-base text-zinc-500 max-w-2xl mx-auto leading-relaxed">
            Nexora is a chat-first CRM designed to automate customer engagement.
            Marketers state their campaign goals in plain English, and our
            system takes care of the segmentation, copywriting, and
            multi-channel dispatches automatically.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row justify-center items-center gap-4 max-w-sm sm:max-w-none mx-auto w-full px-4">
            <Link
              href="/chat"
              className="inline-flex items-center justify-center gap-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-750 px-6.5 py-3.5 text-sm font-extrabold text-white shadow-lg shadow-indigo-600/10 hover:shadow-indigo-600/20 hover:from-indigo-650 hover:to-indigo-800 transition-all w-full sm:w-auto hover:scale-[1.02] active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2"
            >
              Launch Copilot Chat
              <Sparkles className="h-4 w-4 text-indigo-200" />
            </Link>
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2.5 rounded-xl border border-zinc-350 bg-white px-6.5 py-3.5 text-sm font-bold text-zinc-700 hover:bg-zinc-50 hover:border-zinc-400 transition-all w-full sm:w-auto hover:scale-[1.02] active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-zinc-650 focus-visible:ring-offset-2"
            >
              Open App Dashboard
              <ArrowRight className="h-4 w-4 text-zinc-500" />
            </Link>
          </div>
        </div>
      </section>

      {/* Interactive Tour Section */}
      <section className="max-w-5xl mx-auto px-4 py-16 sm:py-20 border-t border-zinc-200/80 space-y-8">
        <div className="border-b border-zinc-200 pb-4">
          <h2 className="text-xl font-extrabold text-zinc-950">
            How It Works: Interactive Tour
          </h2>
          <p className="text-xs text-zinc-500 mt-1">
            Select a campaign scenario below and step through the pipeline
            stages to see how our AI and backend handle execution.
          </p>
        </div>

        {/* Goal Selector Quick Buttons */}
        <div className="flex flex-wrap gap-3">
          {SAMPLE_GOALS.map((goal) => (
            <button
              key={goal.id}
              onClick={() => handleSelectGoal(goal)}
              className={`rounded-lg border px-4 py-2.5 text-left text-xs font-bold transition-all ${
                selectedGoal.id === goal.id
                  ? "border-indigo-600 bg-indigo-50/50 text-indigo-750 shadow-3xs"
                  : "border-zinc-200 bg-white text-zinc-650 hover:bg-zinc-50"
              }`}
            >
              {goal.title}
              <span className="block text-4xs font-normal text-zinc-400 mt-1 truncate max-w-[200px]">
                &quot;{goal.goalText}&quot;
              </span>
            </button>
          ))}
        </div>

        {/* Step Navigation Tabs */}
        <div className="flex overflow-x-auto no-scrollbar gap-4 border-b border-zinc-200/60 pb-3 whitespace-nowrap">
          {steps.map((step, idx) => (
            <button
              key={idx}
              onClick={() => setActiveStep(idx)}
              className={`flex items-center gap-2 border-b-2 pb-2 text-2xs font-bold transition-all text-left shrink-0 ${
                activeStep === idx
                  ? "border-indigo-600 text-indigo-650"
                  : "border-transparent text-zinc-400 hover:text-zinc-650"
              }`}
            >
              {step.icon}
              <div className="min-w-0">
                <div className="truncate">{step.label}</div>
                <div className="text-4xs font-normal text-zinc-400 truncate hidden md:block">
                  {step.description}
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Tour Stage Viewer */}
        <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-xs min-h-[300px] flex flex-col justify-between">
          {/* STAGE 1: DEFINE GOAL */}
          {activeStep === 0 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <span className="text-4xs font-bold uppercase tracking-wider text-indigo-600">
                  Stage 1: Goal Definition
                </span>
                <h3 className="text-sm font-bold text-zinc-900">
                  Marketer Inputs Campaign Goal
                </h3>
                <p className="text-2xs text-zinc-500 leading-relaxed">
                  Marketers type their business target in plain English. The AI
                  Copilot accepts the objective and uses regex rules to identify
                  database variables and theme properties.
                </p>
              </div>

              <div className="border border-zinc-200 rounded-lg p-4 bg-zinc-50 space-y-4">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-3xs">
                    M
                  </div>
                  <span className="text-3xs font-semibold text-zinc-500">
                    Marketer Input Prompt:
                  </span>
                </div>
                <textarea
                  value={typedMessage}
                  onChange={(e) => setTypedMessage(e.target.value)}
                  className="w-full rounded border border-zinc-200 p-2.5 text-xs text-zinc-800 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white resize-none"
                  rows={2}
                />
                <button
                  onClick={() => {
                    const matched =
                      SAMPLE_GOALS.find((g) =>
                        typedMessage.toLowerCase().includes(g.id),
                      ) || selectedGoal;
                    setSelectedGoal({ ...matched, goalText: typedMessage });
                    setActiveStep(1);
                  }}
                  className="rounded bg-indigo-600 px-3 py-1.5 text-3xs font-bold text-white hover:bg-indigo-700 transition-colors"
                >
                  Analyze &amp; Segment
                </button>
              </div>
            </div>
          )}

          {/* STAGE 2: SEGMENT AUDIENCE */}
          {activeStep === 1 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <span className="text-4xs font-bold uppercase tracking-wider text-indigo-600">
                  Stage 2: Customer Segmentation
                </span>
                <h3 className="text-sm font-bold text-zinc-900">
                  SQL Filter Mapping &amp; DB Execution
                </h3>
                <p className="text-2xs text-zinc-500 leading-relaxed">
                  The application maps natural language goals to structured
                  filters. It translates parameters (like minimum spending or
                  orders) into denormalized SQL filters to query the database.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Extracted JSON Parameters */}
                <div className="border border-zinc-150 rounded-lg p-4 bg-zinc-50 font-mono text-3xs space-y-3">
                  <span className="text-zinc-400 font-semibold block uppercase tracking-wider text-4xs">
                    Extracted Parameters
                  </span>
                  <pre className="text-indigo-600 bg-white border border-zinc-150 p-2 rounded overflow-x-auto">
                    {JSON.stringify(selectedGoal.filters, null, 2)}
                  </pre>
                  <p className="text-zinc-500 font-sans leading-relaxed text-4xs">
                    Denormalized variables like{" "}
                    <code className="bg-zinc-200 px-1 rounded">
                      last_order_date
                    </code>{" "}
                    and{" "}
                    <code className="bg-zinc-200 px-1 rounded">
                      total_spent
                    </code>{" "}
                    are indexed on the customer model for fast query
                    performance.
                  </p>
                </div>
                {/* DB Response Summary */}
                <div className="border border-zinc-150 rounded-lg p-4 bg-zinc-50 flex flex-col justify-between">
                  <div className="space-y-2">
                    <span className="text-zinc-400 font-semibold block uppercase tracking-wider text-4xs">
                      Database Query Result
                    </span>
                    <span className="text-2xl font-semibold text-zinc-950 block">
                      {selectedGoal.audienceCount} customers
                    </span>
                    <p className="text-3xs text-zinc-500 leading-relaxed">
                      Found {selectedGoal.audienceCount} matching profiles.
                      Average spend is ₹{selectedGoal.avgSpend.toLocaleString()}
                      .
                    </p>
                  </div>
                  <div className="flex gap-1.5 items-center mt-3 text-4xs font-bold text-zinc-400">
                    <span className="bg-white border border-zinc-150 px-1.5 py-0.5 rounded">
                      Gagan Sami
                    </span>
                    <span className="bg-white border border-zinc-150 px-1.5 py-0.5 rounded">
                      Ayushman Chander
                    </span>
                    <span className="bg-white border border-zinc-150 px-1.5 py-0.5 rounded">
                      Saumya Mall
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STAGE 3: SELECT CHANNEL */}
          {activeStep === 2 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <span className="text-4xs font-bold uppercase tracking-wider text-indigo-600">
                  Stage 3: Intelligent Channel Routing
                </span>
                <h3 className="text-sm font-bold text-zinc-900">
                  Rule-Based Routing Selection
                </h3>
                <p className="text-2xs text-zinc-500 leading-relaxed">
                  Our routing engine selects the best delivery channel based on
                  segment size, average spend, and marketer intent.
                </p>
              </div>

              <div className="border border-zinc-150 rounded-lg p-5 bg-zinc-50 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="space-y-2">
                  <span className="text-zinc-400 font-semibold block uppercase tracking-wider text-4xs">
                    Recommended Channel
                  </span>
                  <span className="inline-flex items-center rounded-md bg-indigo-50 px-3 py-1 font-bold text-xs text-indigo-700 capitalize border border-indigo-150/50">
                    {selectedGoal.channel}
                  </span>
                  <p className="text-3xs text-zinc-500 max-w-xl leading-relaxed">
                    {selectedGoal.channelReason}
                  </p>
                </div>

                <div className="border-t md:border-t-0 md:border-l border-zinc-200/80 pt-4 md:pt-0 md:pl-6 text-3xs font-semibold text-zinc-400 space-y-2">
                  <div>
                    WhatsApp:{" "}
                    <span className="text-zinc-650 font-bold">
                      &lt; 500 Segment &amp; High Spend
                    </span>
                  </div>
                  <div>
                    Email:{" "}
                    <span className="text-zinc-650 font-bold">
                      &gt;= 500 Segment or Policy Msg
                    </span>
                  </div>
                  <div>
                    SMS:{" "}
                    <span className="text-zinc-650 font-bold">
                      Fallback / Short Alert Msg
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STAGE 4: GENERATE MESSAGE */}
          {activeStep === 3 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <span className="text-4xs font-bold uppercase tracking-wider text-indigo-600">
                  Stage 4: Dynamic Copywriting
                </span>
                <h3 className="text-sm font-bold text-zinc-900">
                  Context-Aware Copy Generation
                </h3>
                <p className="text-2xs text-zinc-500 leading-relaxed">
                  The copywriter generates two message drafts tailored to
                  channel constraints. Tokens (like{" "}
                  <code className="bg-zinc-200 px-1 rounded">{"{{name}}"}</code>{" "}
                  and{" "}
                  <code className="bg-zinc-200 px-1 rounded">
                    {"{{discount_code}}"}
                  </code>
                  ) are resolved dynamically on campaign dispatch.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Variant A */}
                <div className="border border-zinc-150 rounded-lg p-4 bg-zinc-50 space-y-3">
                  <span className="text-3xs font-bold text-zinc-500">
                    Variant A (Primary Draft)
                  </span>
                  <div className="bg-white border border-zinc-200 rounded p-3 text-2xs text-zinc-750 min-h-[70px] leading-relaxed whitespace-pre-wrap">
                    {selectedGoal.variantA}
                  </div>
                </div>
                {/* Variant B */}
                <div className="border border-zinc-150 rounded-lg p-4 bg-zinc-50 space-y-3">
                  <span className="text-3xs font-bold text-zinc-500">
                    Variant B (Urgency Draft)
                  </span>
                  <div className="bg-white border border-zinc-200 rounded p-3 text-2xs text-zinc-750 min-h-[70px] leading-relaxed whitespace-pre-wrap">
                    {selectedGoal.variantB}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STAGE 5: DISPATCH & FUNNEL */}
          {activeStep === 4 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <span className="text-4xs font-bold uppercase tracking-wider text-indigo-600">
                  Stage 5: Async Dispatch &amp; Webhook Funnel
                </span>
                <h3 className="text-sm font-bold text-zinc-900">
                  Non-Blocking Sending &amp; ROI Calculations
                </h3>
                <p className="text-2xs text-zinc-500 leading-relaxed">
                  FastAPI background workers dispatch messages concurrently to
                  the Channel Stub. Webhook callbacks stream events like
                  delivered, opened, clicked, and purchased to calculate
                  campaign ROI in real-time.
                </p>
              </div>

              <div className="border border-zinc-150 rounded-lg p-4 bg-zinc-50 space-y-4">
                {/* Funnel Pipeline */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                  <div className="bg-white border border-zinc-200 rounded p-3">
                    <span className="text-zinc-400 text-3xs font-medium block">
                      Segment Cost
                    </span>
                    <span className="text-xs font-extrabold text-zinc-800 block mt-1">
                      ₹{selectedGoal.estimatedCost.toFixed(2)}
                    </span>
                  </div>
                  <div className="bg-white border border-zinc-200 rounded p-3">
                    <span className="text-zinc-400 text-3xs font-medium block">
                      Purchases
                    </span>
                    <span className="text-xs font-extrabold text-zinc-850 block mt-1">
                      {selectedGoal.conversions} orders
                    </span>
                  </div>
                  <div className="bg-white border border-zinc-200 rounded p-3">
                    <span className="text-zinc-400 text-3xs font-medium block">
                      Revenue Recaptured
                    </span>
                    <span className="text-xs font-extrabold text-zinc-900 block mt-1">
                      ₹{selectedGoal.revenue.toLocaleString()}
                    </span>
                  </div>
                  <div className="bg-white border border-zinc-200 rounded p-3">
                    <span className="text-indigo-550 text-3xs font-bold block">
                      Net ROI Factor
                    </span>
                    <span className="text-xs font-extrabold text-indigo-700 block mt-1">
                      +{selectedGoal.roi.toLocaleString()}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Bottom Navigation Control Buttons */}
          <div className="border-t border-zinc-100 pt-4 flex justify-between items-center text-xs">
            <button
              onClick={() => setActiveStep((prev) => Math.max(0, prev - 1))}
              disabled={activeStep === 0}
              className="px-3 py-1.5 border border-zinc-200 rounded-lg hover:bg-zinc-50 text-zinc-550 disabled:opacity-40"
            >
              Previous Stage
            </button>
            <div className="flex gap-1.5">
              {steps.map((_, idx) => (
                <span
                  key={idx}
                  onClick={() => setActiveStep(idx)}
                  className={`h-1.5 w-1.5 rounded-full cursor-pointer transition-all ${
                    activeStep === idx
                      ? "bg-indigo-600 scale-125"
                      : "bg-zinc-200 hover:bg-zinc-350"
                  }`}
                />
              ))}
            </div>
            {activeStep < 4 ? (
              <button
                onClick={() => setActiveStep((prev) => Math.min(4, prev + 1))}
                className="px-3 py-1.5 bg-zinc-900 text-white rounded-lg hover:bg-zinc-800"
              >
                Next Stage
              </button>
            ) : (
              <Link
                href="/dashboard"
                className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-semibold"
              >
                Open Dashboard
              </Link>
            )}
          </div>
        </div>
      </section>

      {/* Interactive Architecture Simulation */}
      <section className="max-w-5xl mx-auto px-4 py-16 sm:py-20 border-t border-zinc-200/80 space-y-6">
        <div className="border-b border-zinc-200 pb-4 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h2 className="text-xl font-extrabold text-zinc-950">
              Interactive System Architecture &amp; Runtime Simulation
            </h2>
            <p className="text-xs text-zinc-500 mt-1">
              Trace the live request pipelines, thread-safe rotator locks,
              priority webhooks, and database ACID transactions in real-time.
            </p>
          </div>
          <Link
            href="/simulation"
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-2xs font-bold text-zinc-700 hover:bg-zinc-50 hover:text-zinc-900 transition-colors shadow-3xs shrink-0 self-start md:self-auto"
          >
            <span>Open Fullscreen</span>
            <ArrowRight className="h-3.5 w-3.5 text-zinc-450" />
          </Link>
        </div>
        <div className="relative w-full rounded-xl border border-zinc-200 bg-white overflow-hidden shadow-xs h-[500px] sm:h-[660px]">
          <iframe
            src="/conversio_simulation.html"
            className="absolute inset-0 w-full h-full border-0"
            title="Nexora System Architecture Simulation"
          />
        </div>
      </section>

      {/* Core Technical Capabilities Showcase */}
      <section className="max-w-5xl mx-auto px-4 py-16 sm:py-20 border-t border-zinc-200/80 grid grid-cols-1 md:grid-cols-3 gap-8">
        <div className="space-y-2 border border-zinc-150 rounded-xl p-5 bg-white">
          <div className="rounded-lg bg-indigo-50 p-2 text-indigo-700 w-fit">
            <Database className="h-4.5 w-4.5" />
          </div>
          <h3 className="text-xs font-bold text-zinc-950 uppercase tracking-wider">
            Fast Denormalized Schema
          </h3>
          <p className="text-3xs text-zinc-500 leading-relaxed">
            Variables like order history, total spent, and last order dates are
            denormalized onto the customer record. This guarantees segmentation
            queries compile instantly without SQL table joins.
          </p>
        </div>

        <div className="space-y-2 border border-zinc-150 rounded-xl p-5 bg-white">
          <div className="rounded-lg bg-emerald-50 p-2 text-emerald-700 w-fit">
            <CheckCircle2 className="h-4.5 w-4.5" />
          </div>
          <h3 className="text-xs font-bold text-zinc-950 uppercase tracking-wider">
            Priority Ingestion Guards
          </h3>
          <p className="text-3xs text-zinc-500 leading-relaxed">
            Webhook receipts are processed with strict priority validation.
            Inbound delivery updates cannot downgrade existing status logs (e.g.
            click receipts cannot be overwritten by out-of-order deliveries).
          </p>
        </div>

        <div className="space-y-2 border border-zinc-150 rounded-xl p-5 bg-white">
          <div className="rounded-lg bg-purple-50 p-2 text-purple-700 w-fit">
            <TrendingUp className="h-4.5 w-4.5" />
          </div>
          <h3 className="text-xs font-bold text-zinc-950 uppercase tracking-wider">
            Active ROI &amp; AOV joins
          </h3>
          <p className="text-3xs text-zinc-500 leading-relaxed">
            Revenue aggregates are calculated dynamically by summing the
            historical average order value of customers who reached the
            purchased status. Cost rates are generated per channel for true ROI.
          </p>
        </div>
      </section>
    </div>
  );
}
