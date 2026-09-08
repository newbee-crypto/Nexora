import React, { useState } from "react";
import { UserCheck, MessageSquare, FileText, Eye, Rocket, Check, AlertCircle, RefreshCw, Sparkles, Plus } from "lucide-react";
import Link from "next/link";

export interface StepData {
  step: "segment_built" | "channel_suggested" | "message_generated" | "campaign_preview" | "campaign_launched" | "error";
  filters?: any;
  count?: number;
  audience_count?: number;
  avg_spend?: number;
  sample_names?: string[];
  summary?: string;
  channel?: string;
  reason?: string;
  variant_a?: string;
  variant_b?: string;
  char_count?: number[];
  campaign_name?: string;
  campaign_id?: string;
  communications_queued?: number;
  ready_to_launch?: boolean;
  channel_reason?: string;
  segment_filters?: any;
  error?: string;
}

interface StepCardProps {
  stepData: StepData;
  onLaunch?: (variant: "A" | "B", templateText: string) => void;
  isLaunching?: boolean;
  onActiveTemplateChange?: (text: string) => void;
  onRegenerate?: (selectedTokens?: string[]) => void;
  isRegenerating?: boolean;
}

export default function StepCard({ stepData, onLaunch, isLaunching, onActiveTemplateChange, onRegenerate, isRegenerating = false }: StepCardProps) {
  const [activeTab, setActiveTab] = useState<"A" | "B">("A");
  const [editedA, setEditedA] = useState<string | null>(null);
  const [editedB, setEditedB] = useState<string | null>(null);

  // Reset edited template states when variants are regenerated from backend
  React.useEffect(() => {
    setEditedA(null);
    setEditedB(null);
  }, [stepData.variant_a, stepData.variant_b]);

  const currentEditedA = editedA !== null ? editedA : (stepData.variant_a || "");
  const currentEditedB = editedB !== null ? editedB : (stepData.variant_b || "");
  
  const activeTemplate = activeTab === "A" ? currentEditedA : currentEditedB;

  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const personalizationVariables = [
    { token: "{{first_name}}", label: "First Name", description: "Customer's first name only, e.g. Naksh" },
    { token: "{{total_spent}}", label: "Total Spent", description: "Customer's total spent formatted, e.g. ₹12,450" },
    { token: "{{total_orders}}", label: "Total Orders", description: "Total orders count, e.g. 5" },
    { token: "{{discount_code}}", label: "Discount Code", description: "Deterministic coupon code based on campaign/customer" },
    { token: "{{last_order_date}}", label: "Last Order Date", description: "Date of last purchase, e.g. 15 April" },
  ];

  const [selectedTokens, setSelectedTokens] = useState<string[]>([]);

  React.useEffect(() => {
    const defaultTokens = personalizationVariables
      .map(v => v.token)
      .filter(t => (stepData.variant_a || "").includes(t) || (stepData.variant_b || "").includes(t));
    setSelectedTokens(defaultTokens);
  }, [stepData.variant_a, stepData.variant_b]);

  const toggleTokenSelection = (token: string) => {
    setSelectedTokens(prev => 
      prev.includes(token) ? prev.filter(t => t !== token) : [...prev, token]
    );
  };

  const insertVariable = (variable: string) => {
    const el = textareaRef.current;
    if (!el) {
      if (activeTab === "A") {
        setEditedA(prev => (prev !== null ? prev : (stepData.variant_a || "")) + variable);
      } else {
        setEditedB(prev => (prev !== null ? prev : (stepData.variant_b || "")) + variable);
      }
      return;
    }

    const isFocused = document.activeElement === el;
    const start = isFocused ? el.selectionStart : el.value.length;
    const end = isFocused ? el.selectionEnd : el.value.length;
    const currentValue = el.value;
    const newValue = currentValue.substring(0, start) + variable + currentValue.substring(end);

    if (activeTab === "A") {
      setEditedA(newValue);
    } else {
      setEditedB(newValue);
    }

    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + variable.length, start + variable.length);
    }, 0);
  };

  // Sync active template change with parent component (for right mockup panel)
  React.useEffect(() => {
    if (onActiveTemplateChange && (stepData.step === "message_generated" || stepData.step === "campaign_preview")) {
      onActiveTemplateChange(activeTemplate);
    }
  }, [activeTemplate, stepData.step, onActiveTemplateChange]);

  // Format token placeholders with visual highlights
  const formatMessageText = (text: string) => {
    if (!text) return "";
    const parts = text.split(/(\{\{[a-zA-Z_]+\}\})/g);
    return parts.map((part, index) => {
      if (part.startsWith("{{") && part.endsWith("}}")) {
        return (
          <span
            key={index}
            className="inline-block rounded border border-zinc-200 bg-zinc-100 px-1 font-mono text-2xs font-medium text-zinc-800"
          >
            {part}
          </span>
        );
      }
      return part;
    });
  };

  switch (stepData.step) {
    case "segment_built":
      return (
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-md border border-zinc-200 bg-zinc-50 p-1.5 text-zinc-600">
              <UserCheck className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-zinc-900">Audience Segment Built</h4>
              <p className="mt-1 text-xs text-zinc-600 leading-relaxed">
                {stepData.summary || `Filtered customer database to find matching audience.`}
              </p>

              {stepData.filters && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {Object.entries(stepData.filters).map(([key, value]) => (
                    <span
                      key={key}
                      className="inline-flex items-center rounded-md border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-3xs font-medium text-zinc-600"
                    >
                      <span className="capitalize text-zinc-400 mr-1">{key.replace("_", " ")}:</span>
                      {Array.isArray(value) ? value.join(", ") : String(value)}
                    </span>
                  ))}
                </div>
              )}

              {stepData.sample_names && stepData.sample_names.length > 0 && (
                <p className="mt-2.5 text-3xs text-zinc-400 italic">
                  Sample: {stepData.sample_names.join(", ")}
                </p>
              )}
            </div>
          </div>
        </div>
      );

    case "channel_suggested":
      return (
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-md border border-zinc-200 bg-zinc-50 p-1.5 text-zinc-600">
              <MessageSquare className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-zinc-900">Delivery Channel Recommended</h4>
              <div className="mt-2 flex items-center gap-2">
                <span className="inline-flex items-center rounded-md bg-indigo-50 border border-indigo-200/50 px-2 py-0.5 text-3xs font-semibold uppercase tracking-wider text-indigo-700">
                  {stepData.channel}
                </span>
                <span className="text-3xs text-zinc-400 font-medium">
                  {stepData.audience_count} targeted customers
                </span>
              </div>
              <p className="mt-2 text-xs text-zinc-600 leading-relaxed">
                {stepData.reason}
              </p>
            </div>
          </div>
        </div>
      );

    case "message_generated":
      return (
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-md border border-zinc-200 bg-zinc-50 p-1.5 text-zinc-600">
              <FileText className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-zinc-900">Personalized Message Drafts</h4>
              <p className="mt-1 text-xs text-zinc-500">
                Generated 2 copywriting variants for {stepData.channel}. Toggle tabs to preview.
              </p>

              <div className="mt-3 flex items-center justify-between border-b border-zinc-100">
                <div className="flex">
                  <button
                    onClick={() => setActiveTab("A")}
                    className={`border-b px-3 py-1.5 text-2xs font-semibold focus:outline-none transition-colors ${
                      activeTab === "A"
                        ? "border-zinc-900 text-zinc-900"
                        : "border-transparent text-zinc-400 hover:text-zinc-600"
                    }`}
                  >
                    Variant A
                  </button>
                  <button
                    onClick={() => setActiveTab("B")}
                    className={`border-b px-3 py-1.5 text-2xs font-semibold focus:outline-none transition-colors ${
                      activeTab === "B"
                        ? "border-zinc-900 text-zinc-900"
                        : "border-transparent text-zinc-400 hover:text-zinc-600"
                    }`}
                  >
                    Variant B
                  </button>
                </div>
                {onRegenerate && (
                  <button
                    disabled={isRegenerating}
                    onClick={() => onRegenerate(selectedTokens)}
                    className="flex items-center gap-1.5 px-2.5 py-1 text-3xs font-semibold text-indigo-650 hover:text-indigo-850 hover:bg-zinc-50 border border-zinc-200 bg-white rounded-md transition-colors shadow-3xs disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <RefreshCw className={`h-3 w-3 ${isRegenerating ? "animate-spin text-indigo-500" : ""}`} />
                    {isRegenerating ? "Regenerating..." : "Regenerate"}
                  </button>
                )}
              </div>

              <div className="mt-3">
                <textarea
                  ref={textareaRef}
                  value={activeTab === "A" ? currentEditedA : currentEditedB}
                  onChange={(e) => {
                    if (activeTab === "A") {
                      setEditedA(e.target.value);
                    } else {
                      setEditedB(e.target.value);
                    }
                  }}
                  rows={4}
                  className="w-full rounded-md border border-zinc-200 bg-zinc-50/30 p-3 text-xs text-zinc-800 focus:outline-none focus:ring-1 focus:ring-zinc-950 focus:border-zinc-950 transition-all resize-y font-sans leading-relaxed shadow-3xs"
                  placeholder="Enter message template..."
                />
              </div>

              {/* Personalization Variable Selector */}
              <div className="mt-3 border border-indigo-100/60 rounded-xl bg-indigo-50/10 p-3.5 shadow-3xs">
                <div className="flex items-center gap-1.5 text-4xs font-bold uppercase tracking-wider text-indigo-700/80 mb-2.5">
                  <Sparkles className="h-3.5 w-3.5 text-indigo-650 animate-pulse" />
                  <span>Personalization Tokens (Toggle to select for AI / click + to insert)</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {personalizationVariables.map((v) => (
                    <button
                      key={v.token}
                      type="button"
                      onClick={() => toggleTokenSelection(v.token)}
                      title={`${v.description} (Click to select/deselect for AI generation)`}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-3xs font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] cursor-pointer shadow-3xs border-solid ${
                        selectedTokens.includes(v.token)
                          ? "bg-indigo-600 text-white border-indigo-700 hover:bg-indigo-750 font-bold"
                          : "bg-white text-indigo-700/90 border-indigo-100 hover:bg-indigo-50/60"
                      }`}
                    >
                      <span className="font-mono">{v.token}</span>
                      <span className={selectedTokens.includes(v.token) ? "text-indigo-200 font-normal" : "text-zinc-400 font-normal"}>
                        ({v.label})
                      </span>
                      <span
                        onClick={(e) => {
                          e.stopPropagation();
                          insertVariable(v.token);
                        }}
                        title="Insert directly at cursor position"
                        className={`ml-1 pl-1.5 border-l flex items-center hover:scale-110 active:scale-95 transition-transform ${
                          selectedTokens.includes(v.token) ? "border-indigo-500 text-indigo-150" : "border-indigo-100 text-indigo-400"
                        }`}
                      >
                        <Plus className="h-2.5 w-2.5 font-bold" />
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-2 flex items-center justify-between text-3xs text-zinc-400">
                <span className="italic">Tip: You can edit this text directly.</span>
                <span>
                  Length:{" "}
                  {activeTab === "A"
                    ? currentEditedA.length
                    : currentEditedB.length}{" "}
                  characters
                </span>
              </div>
            </div>
          </div>
        </div>
      );

    case "campaign_preview":
      return (
        <div className="rounded-lg border border-zinc-300 bg-white p-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-md border border-zinc-200 bg-zinc-50 p-1.5 text-zinc-600">
              <Eye className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-zinc-900">Campaign Final Preview</h4>
              <p className="mt-1 text-2xs text-zinc-400">
                Review segment parameters and message copy before launching.
              </p>

              <div className="mt-4 space-y-3 rounded-lg border border-zinc-200/80 bg-zinc-50/20 p-4 text-2xs">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  <div>
                    <span className="text-zinc-400 block font-medium">Campaign Name</span>
                    <span className="font-semibold text-zinc-800 tracking-tight mt-0.5 block">{stepData.campaign_name}</span>
                  </div>
                  <div>
                    <span className="text-zinc-400 block font-medium">Channel</span>
                    <span className="font-semibold text-zinc-800 capitalize mt-0.5 block">{stepData.channel}</span>
                  </div>
                  <div>
                    <span className="text-zinc-400 block font-medium">Audience Size</span>
                    <span className="font-semibold text-zinc-800 mt-0.5 block">{stepData.audience_count} customers</span>
                  </div>
                  <div>
                    <span className="text-zinc-400 block font-medium">Est. Campaign Cost</span>
                    <span className="font-semibold text-indigo-600 mt-0.5 block">
                      ₹{((stepData.audience_count || 0) * (stepData.channel === 'whatsapp' ? 0.80 : stepData.channel === 'sms' ? 0.20 : 0.05)).toFixed(2)}
                      <span className="text-3xs text-zinc-400 font-normal ml-1">
                        (₹{stepData.channel === 'whatsapp' ? '0.80' : stepData.channel === 'sms' ? '0.20' : '0.05'}/msg)
                      </span>
                    </span>
                  </div>
                  <div className="sm:col-span-2">
                    <span className="text-zinc-400 block font-medium">Channel Reason</span>
                    <span className="font-medium text-zinc-500 mt-0.5 block line-clamp-1" title={stepData.channel_reason}>
                      {stepData.channel_reason || "Best match"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-4">
                <div className="flex items-center justify-between border-b border-zinc-100 pb-1.5 mb-2">
                  <span className="text-2xs font-semibold text-zinc-800">Selected Copy Template</span>
                  <div className="flex items-center gap-3">
                    {onRegenerate && (
                      <button
                        disabled={isRegenerating}
                        onClick={() => onRegenerate(selectedTokens)}
                        className="flex items-center gap-1 text-3xs font-semibold text-indigo-650 hover:text-indigo-850 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <RefreshCw className={`h-2.5 w-2.5 ${isRegenerating ? "animate-spin text-indigo-500" : "animate-duration-75"}`} />
                        {isRegenerating ? "Regenerating..." : "Regenerate"}
                      </button>
                    )}
                    <div className="flex rounded border border-zinc-200 bg-zinc-50 p-0.5">
                      <button
                        onClick={() => setActiveTab("A")}
                        className={`rounded px-2 py-0.5 text-3xs font-medium focus:outline-none transition-colors ${
                          activeTab === "A" ? "bg-white text-zinc-900 shadow-3xs" : "text-zinc-400"
                        }`}
                      >
                        A
                      </button>
                      <button
                        onClick={() => setActiveTab("B")}
                        className={`rounded px-2 py-0.5 text-3xs font-medium focus:outline-none transition-colors ${
                          activeTab === "B" ? "bg-white text-zinc-900 shadow-3xs" : "text-zinc-400"
                        }`}
                      >
                        B
                      </button>
                    </div>
                  </div>
                </div>
                <div className="mt-2">
                  <textarea
                    ref={textareaRef}
                    value={activeTemplate || ""}
                    onChange={(e) => {
                      if (activeTab === "A") {
                        setEditedA(e.target.value);
                      } else {
                        setEditedB(e.target.value);
                      }
                    }}
                    rows={4}
                    className="w-full rounded-md border border-zinc-200 bg-zinc-50/20 p-3 text-2xs text-zinc-700 focus:outline-none focus:ring-1 focus:ring-zinc-950 focus:border-zinc-950 transition-all resize-y font-sans leading-relaxed shadow-3xs"
                    placeholder="Enter message template..."
                  />
                </div>

                {/* Personalization Variable Selector */}
                <div className="mt-3.5 border border-indigo-100/60 rounded-xl bg-indigo-50/10 p-3.5 shadow-3xs">
                  <div className="flex items-center gap-1.5 text-4xs font-bold uppercase tracking-wider text-indigo-700/80 mb-2.5">
                    <Sparkles className="h-3.5 w-3.5 text-indigo-650 animate-pulse" />
                    <span>Personalization Tokens (Toggle to select for AI / click + to insert)</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {personalizationVariables.map((v) => (
                      <button
                        key={v.token}
                        type="button"
                        onClick={() => toggleTokenSelection(v.token)}
                        title={`${v.description} (Click to select/deselect for AI generation)`}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-3xs font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] cursor-pointer shadow-3xs border-solid ${
                          selectedTokens.includes(v.token)
                            ? "bg-indigo-600 text-white border-indigo-700 hover:bg-indigo-750 font-bold"
                            : "bg-white text-indigo-700/90 border-indigo-100 hover:bg-indigo-50/60"
                        }`}
                      >
                        <span className="font-mono">{v.token}</span>
                        <span className={selectedTokens.includes(v.token) ? "text-indigo-200 font-normal" : "text-zinc-400 font-normal"}>
                          ({v.label})
                        </span>
                        <span
                          onClick={(e) => {
                            e.stopPropagation();
                            insertVariable(v.token);
                          }}
                          title="Insert directly at cursor position"
                          className={`ml-1 pl-1.5 border-l flex items-center hover:scale-110 active:scale-95 transition-transform ${
                            selectedTokens.includes(v.token) ? "border-indigo-500 text-indigo-150" : "border-indigo-100 text-indigo-400"
                          }`}
                        >
                          <Plus className="h-2.5 w-2.5 font-bold" />
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mt-1.5 flex items-center justify-between text-3xs text-zinc-400">
                  <span className="italic">Tip: You can edit this text directly.</span>
                  <span>Length: {activeTemplate?.length || 0} characters</span>
                </div>
              </div>

              {stepData.ready_to_launch && onLaunch && (
                <div className="space-y-4">
                  {stepData.audience_count === 0 && (
                    <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-2xs text-amber-800 flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                      <span>
                        <strong>Cannot Launch Campaign:</strong> No customers match the selected segment filters. Please modify your query to target at least 1 customer before launching.
                      </span>
                    </div>
                  )}
                  <button
                    disabled={isLaunching || stepData.audience_count === 0}
                    onClick={() => onLaunch(activeTab, activeTemplate || "")}
                    className="mt-5 flex w-full items-center justify-center gap-2 rounded-md bg-indigo-600 px-3.5 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-1 focus:ring-indigo-950 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Rocket className="h-3.5 w-3.5" />
                    {isLaunching ? "Launching Campaign..." : "Launch Campaign"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      );

    case "campaign_launched":
      return (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/20 p-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-md border border-emerald-200 bg-emerald-50 p-1.5 text-emerald-600">
              <Rocket className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-emerald-950">Campaign Launched Successfully</h4>
              <p className="mt-1.5 text-xs text-zinc-700 leading-relaxed">
                {stepData.summary}
              </p>
              {stepData.campaign_id && (
                <div className="mt-4 flex items-center justify-between border-t border-emerald-100/60 pt-3">
                  <span className="text-3xs text-emerald-700/80 font-medium">
                    Queue: {stepData.communications_queued} messages
                  </span>
                  <Link
                    href={`/campaigns/${stepData.campaign_id}`}
                    className="inline-flex items-center gap-1 text-2xs font-semibold text-emerald-700 hover:text-emerald-800 transition-colors"
                  >
                    Track Live Funnel
                    <Check className="h-3.5 w-3.5" />
                  </Link>
                </div>
              )}
            </div>
          </div>
        </div>
      );

    case "error":
      return (
        <div className="rounded-lg border border-red-200 bg-red-50/20 p-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-md border border-red-200 bg-red-50 p-1.5 text-red-600">
              <AlertCircle className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-red-950">Agent Step Error</h4>
              <p className="mt-1 text-xs text-red-700 leading-relaxed">
                {stepData.error || "An unexpected error occurred while executing the agent step."}
              </p>
            </div>
          </div>
        </div>
      );

    default:
      return null;
  }
}
