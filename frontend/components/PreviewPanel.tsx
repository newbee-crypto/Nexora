import React from "react";
import { Database, Phone, Mail, User, TrendingUp, Sparkles } from "lucide-react";
import { StepData } from "./StepCard";

interface PreviewPanelProps {
  latestStep: StepData | null;
  selectedVariantText: string | null;
}

export default function PreviewPanel({ latestStep, selectedVariantText }: PreviewPanelProps) {
  // Render empty state if there's no step yet
  if (!latestStep) {
    return (
      <div className="flex h-full flex-col items-center justify-center border border-dashed border-zinc-200 rounded-lg p-8 text-center bg-white">
        <div className="rounded-full bg-zinc-50 border border-zinc-200 p-3 text-zinc-400">
          <Sparkles className="h-6 w-6" />
        </div>
        <h3 className="mt-4 text-xs font-semibold text-zinc-950">AI Copilot Side Preview</h3>
        <p className="mt-2 text-2xs text-zinc-400 max-w-[240px] leading-relaxed">
          Start chatting with the copilot. A real-time visual preview of your audience segment and message mockup will appear here.
        </p>
      </div>
    );
  }

  const renderSegmentDetails = () => {
    return (
      <div className="flex h-full flex-col border border-zinc-200 rounded-lg bg-white overflow-hidden">
        <div className="border-b border-zinc-100 bg-zinc-50/50 px-4 py-3">
          <h3 className="flex items-center gap-2 text-xs font-semibold text-zinc-900">
            <Database className="h-4 w-4 text-zinc-500" />
            Audience Query Results
          </h3>
        </div>
        <div className="flex-1 p-5 overflow-y-auto space-y-5">
          <div>
            <span className="text-3xs text-zinc-400 font-medium uppercase tracking-wider block">Audience Count</span>
            <span className="text-3xl font-semibold text-zinc-950 tracking-tight block mt-1">
              {latestStep.count?.toLocaleString() || 0}
            </span>
            <span className="text-3xs text-zinc-400 mt-1 block">customers matching segment logic</span>
          </div>

          <div className="grid grid-cols-2 gap-4 border-y border-zinc-100 py-4">
            <div>
              <span className="text-3xs text-zinc-400 font-medium block">Average Spend</span>
              <span className="text-sm font-semibold text-zinc-800 mt-1 block">₹{(latestStep.avg_spend || 0).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-3xs text-zinc-400 font-medium block">Urgency</span>
              <span className="text-sm font-semibold text-zinc-800 mt-1 block capitalize">Medium</span>
            </div>
          </div>

          <div>
            <span className="text-3xs text-zinc-400 font-medium uppercase tracking-wider block mb-2">Filters Applied</span>
            <div className="space-y-1.5">
              {latestStep.filters ? (
                Object.entries(latestStep.filters).map(([key, val]) => (
                  <div key={key} className="flex justify-between text-2xs border-b border-zinc-50 pb-1.5">
                    <span className="text-zinc-400 capitalize">{key.replace("_", " ")}</span>
                    <span className="font-medium text-zinc-800">{String(val)}</span>
                  </div>
                ))
              ) : (
                <span className="text-2xs text-zinc-400 italic">No filters provided</span>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderMessageMockup = () => {
    const channel = latestStep.channel || "whatsapp";
    const bodyText = selectedVariantText || "Preview message copy will appear here.";

    if (channel === "whatsapp") {
      return (
        <div className="flex h-full flex-col border border-zinc-200 rounded-lg bg-zinc-100 overflow-hidden">
          {/* WhatsApp Header */}
          <div className="flex items-center gap-3 bg-emerald-800 px-4 py-3 text-white">
            <Phone className="h-4 w-4" />
            <div>
              <span className="text-xs font-semibold block leading-tight">Brand Notification</span>
              <span className="text-4xs text-emerald-200/80 tracking-wide block uppercase font-medium">WhatsApp Business</span>
            </div>
          </div>

          {/* WhatsApp Body Container */}
          <div className="flex-1 p-4 flex flex-col justify-end bg-[#efeae2] overflow-y-auto">
            <div className="max-w-[85%] bg-white rounded-lg shadow-3xs p-3 text-zinc-900 border border-zinc-150/60 relative">
              {/* WhatsApp Green arrow */}
              <div className="absolute top-0 -left-1.5 w-0 h-0 border-t-[8px] border-t-white border-l-[8px] border-l-transparent" />
              <p className="text-xs leading-relaxed whitespace-pre-wrap">{bodyText}</p>
              <div className="mt-1 flex items-center justify-between text-4xs text-zinc-400/90 font-medium">
                <span>Official Business</span>
                <span>{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (channel === "sms") {
      return (
        <div className="flex h-full flex-col border border-zinc-200 rounded-lg bg-zinc-100 overflow-hidden">
          {/* SMS Header */}
          <div className="flex items-center justify-center border-b border-zinc-200 bg-white py-3">
            <span className="text-2xs font-semibold text-zinc-900 uppercase tracking-widest">iMessage</span>
          </div>

          {/* SMS chat window */}
          <div className="flex-1 p-4 flex flex-col justify-end bg-white overflow-y-auto">
            <div className="max-w-[80%] bg-zinc-100 rounded-2xl px-4 py-2.5 text-zinc-900 text-xs leading-relaxed self-start whitespace-pre-wrap">
              {bodyText}
            </div>
            <div className="mt-1 text-4xs text-zinc-400/95 ml-2">
              SMS • Today {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
          </div>
        </div>
      );
    }

    // Email Mockup
    return (
      <div className="flex h-full flex-col border border-zinc-200 rounded-lg bg-white overflow-hidden">
        {/* Email Header */}
        <div className="border-b border-zinc-150 bg-zinc-50/50 p-4 text-2xs space-y-2">
          <div className="flex justify-between border-b border-zinc-100/50 pb-2">
            <span className="text-zinc-400"><strong className="text-zinc-500 font-medium">To:</strong> customer@email.com</span>
            <span className="text-zinc-400">Draft</span>
          </div>
          <div className="font-medium text-zinc-800 leading-normal">
            <span className="text-zinc-400 mr-2 font-medium">Subject:</span>
            {bodyText.startsWith("SUBJECT:") ? bodyText.split("|")[0].replace("SUBJECT:", "").trim() : "Campaign Announcement"}
          </div>
        </div>

        {/* Email Body */}
        <div className="flex-1 p-5 overflow-y-auto bg-white">
          <div className="text-xs text-zinc-800 leading-relaxed whitespace-pre-wrap">
            {bodyText.includes("BODY:") ? bodyText.split("BODY:")[1].trim() : bodyText}
          </div>
        </div>
      </div>
    );
  };

  const renderSuccessState = () => {
    return (
      <div className="flex h-full flex-col items-center justify-center border border-zinc-200 rounded-lg p-8 text-center bg-white space-y-4">
        <div className="rounded-full bg-emerald-50 border border-emerald-200 p-3 text-emerald-600">
          <TrendingUp className="h-6 w-6" />
        </div>
        <h3 className="text-xs font-semibold text-zinc-950">Campaign Active</h3>
        <p className="text-2xs text-zinc-400 max-w-[240px] leading-relaxed">
          The campaign dispatcher is currently executing. Track progress and analytics on the campaign live stats page.
        </p>
        {latestStep.campaign_id && (
          <a
            href={`/campaigns/${latestStep.campaign_id}`}
            className="inline-flex items-center gap-2 rounded border border-zinc-200 bg-white px-3 py-1.5 text-2xs font-semibold text-zinc-700 transition-colors hover:bg-zinc-50"
          >
            Go to Campaign Page
          </a>
        )}
      </div>
    );
  };

  switch (latestStep.step) {
    case "segment_built":
      return renderSegmentDetails();
    case "channel_suggested":
      return renderSegmentDetails(); // Keep segment details visible
    case "message_generated":
    case "campaign_preview":
      return renderMessageMockup();
    case "campaign_launched":
      return renderSuccessState();
    default:
      return (
        <div className="flex h-full flex-col items-center justify-center border border-dashed border-zinc-200 rounded-lg p-8 text-center bg-white">
          <div className="rounded-full bg-zinc-50 border border-zinc-200 p-3 text-zinc-400 animate-pulse">
            <User className="h-6 w-6" />
          </div>
          <h3 className="mt-4 text-xs font-semibold text-zinc-950">Processing...</h3>
          <p className="mt-2 text-2xs text-zinc-400 max-w-[200px] leading-relaxed">
            The copilot is working on the next step.
          </p>
        </div>
      );
  }
}
