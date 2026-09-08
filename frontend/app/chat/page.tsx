"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Send, ArrowLeft, RefreshCw, Sparkles, HelpCircle, Cpu, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { v4 as uuidv4 } from "uuid";
import StepCard, { StepData } from "../../components/StepCard";
import PreviewPanel from "../../components/PreviewPanel";
import MarkdownRenderer from "../../components/MarkdownRenderer";

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  steps?: StepData[];
  timestamp: Date;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function ChatPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStatus, setThinkingStatus] = useState("Copilot is running campaign tools...");
  const [isLaunching, setIsLaunching] = useState(false);
  
  // Track selected variant preview text
  const [selectedVariantText, setSelectedVariantText] = useState<string | null>(null);

  const [mobileActiveTab, setMobileActiveTab] = useState<"chat" | "preview">("chat");
  const [agentFramework, setAgentFramework] = useState<"custom" | "langchain">("custom");

  // Track separate session states for Custom vs LangChain
  const [customSessionId, setCustomSessionId] = useState<string>("");
  const [customMessages, setCustomMessages] = useState<Message[]>([]);
  const [langchainSessionId, setLangchainSessionId] = useState<string>("");
  const [langchainMessages, setLangchainMessages] = useState<Message[]>([]);
  const [regeneratingMessageIds, setRegeneratingMessageIds] = useState<string[]>([]);

  const threadEndRef = useRef<HTMLDivElement>(null);
  const goalProcessed = useRef(false);

  // Initialize Session ID and check for deep-linked goal query param
  useEffect(() => {
    // Generate UUIDs for both sessions
    const activeCustomId = uuidv4();
    const activeLangchainId = uuidv4();
    
    // Initialize Custom state as active by default
    setCustomSessionId(activeCustomId);
    setSessionId(activeCustomId);
    
    // Initialize LangChain state in background
    setLangchainSessionId(activeLangchainId);

    // Initial Welcome Message for Custom Engine
    const welcomeMessageCustom: Message = {
      id: "welcome-custom",
      sender: "assistant",
      text: "Hi! I am your AI Campaign Copilot. Tell me your campaign goal or describe who you want to target (e.g., 'Win back customers who haven't ordered in 45 days'), and I'll assemble the audience, recommend a channel, write the message, and launch it for you.",
      timestamp: new Date(),
    };
    setCustomMessages([welcomeMessageCustom]);
    setMessages([welcomeMessageCustom]);

    // Initial Welcome Message for LangChain Engine
    const welcomeMessageLangchain: Message = {
      id: "welcome-langchain",
      sender: "assistant",
      text: "Hi! I am your AI Campaign Copilot running on the LangChain framework. Tell me your campaign goal or target audience, and I will set up the campaign using LangChain and LangGraph workflows.",
      timestamp: new Date(),
    };
    setLangchainMessages([welcomeMessageLangchain]);
  }, []);

  // Handle deep-linked goal from URL query parameter (pre-populates without auto-triggering)
  useEffect(() => {
    const goal = searchParams.get("goal");
    const isRetarget = searchParams.get("retarget") === "true";
    const targetCampaignId = searchParams.get("campaign_id");

    if (goal && sessionId && !goalProcessed.current) {
      goalProcessed.current = true;
      
      if (isRetarget && targetCampaignId) {
        // Fetch stats of the target campaign to get the actual count of non-responders
        const loadRetargetContext = async () => {
          setIsThinking(true);
          setThinkingStatus("Analyzing campaign non-responders...");
          try {
            const res = await fetch(`${API_BASE}/campaigns/${targetCampaignId}/stats`);
            if (res.ok) {
              const statsJson = await res.json();
              const campaignRes = await fetch(`${API_BASE}/campaigns/${targetCampaignId}`);
              const campaignJson = campaignRes.ok ? await campaignRes.json() : null;
              
              const channel = campaignJson?.channel || "whatsapp";
              // Non-openers = Delivered - Opened
              const nonOpeners = Math.max(0, (statsJson.delivered || 0) - (statsJson.opened || 0));
              const targetChannel = channel === "whatsapp" ? "SMS" : "WhatsApp";
              
              const proactiveMsg: Message = {
                id: uuidv4(),
                sender: "assistant",
                text: `I have analyzed your campaign "${statsJson.campaign_name}". I found ${nonOpeners} customers who received the message via ${channel} but did not open it. Should we retarget them using ${targetChannel} instead?`,
                timestamp: new Date(),
              };
              setMessages((prev) => [...prev, proactiveMsg]);
              setInputValue(`Yes, retarget non-responders from campaign ${statsJson.campaign_name} (ID: ${targetCampaignId}) using ${targetChannel.toLowerCase()}`);
            } else {
              throw new Error("Failed to load stats");
            }
          } catch (err) {
            console.error("Failed to load retarget context:", err);
            const fallbackProactiveMsg: Message = {
              id: uuidv4(),
              sender: "assistant",
              text: `I have found 120 users who received the WhatsApp message but didn't open it. Should we send them an SMS instead?`,
              timestamp: new Date(),
            };
            setMessages((prev) => [...prev, fallbackProactiveMsg]);
            setInputValue(`Yes, retarget non-responders from campaign (ID: ${targetCampaignId}) using SMS`);
          } finally {
            setIsThinking(false);
          }
        };
        loadRetargetContext();
      } else {
        setInputValue(goal);
      }
    }
  }, [searchParams, sessionId]);

  // Scroll conversation thread to bottom
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  // Extract the latest step from the message thread to update the preview panel
  const getLatestStep = (): StepData | null => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.steps && msg.steps.length > 0) {
        return msg.steps[msg.steps.length - 1];
      }
    }
    return null;
  };

  const latestStep = getLatestStep();

  // Keep track of the active template text for the visual phone mockup
  useEffect(() => {
    if (latestStep) {
      if (latestStep.step === "message_generated" || latestStep.step === "campaign_preview") {
        // Default to Variant A on initial generation
        setSelectedVariantText(latestStep.variant_a || "");
      }
    } else {
      setSelectedVariantText(null);
    }
  }, [latestStep]);

  // Auto-switch mobile view to preview when a preview-worthy step is generated
  useEffect(() => {
    if (latestStep) {
      setMobileActiveTab("preview");
    } else {
      setMobileActiveTab("chat");
    }
  }, [latestStep]);

  // Send message to copilot endpoint
  const handleSendMessage = async (textToSend?: string, editedTemplate?: string) => {
    const queryText = textToSend || inputValue.trim();
    if (!queryText) return;

    if (!textToSend) {
      setInputValue("");
    }

    // Append user bubble to thread
    const userMsg: Message = {
      id: uuidv4(),
      sender: "user",
      text: queryText,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsThinking(true);
    setThinkingStatus("Connecting to Copilot backend...");

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: queryText,
          edited_template: editedTemplate || null,
          agent_framework: agentFramework,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to communicate with AI Copilot");
      }

      const data = await response.json();
      const allSteps = data.steps || [];
      const finalMessageText = data.final_message || "Done.";

      if (allSteps.length === 0) {
        const assistantMsg: Message = {
          id: uuidv4(),
          sender: "assistant",
          text: finalMessageText,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setIsThinking(false);
        return;
      }

      // Shell for progressive/staggered rendering
      const assistantMsgId = uuidv4();
      const assistantMsg: Message = {
        id: assistantMsgId,
        sender: "assistant",
        text: "",
        steps: [],
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Loop and render cards progressively
      for (let i = 0; i < allSteps.length; i++) {
        const step = allSteps[i];
        
        if (step.step === "segment_built") {
          setThinkingStatus("Querying database to build segment...");
        } else if (step.step === "channel_suggested") {
          setThinkingStatus("Evaluating metrics to select recommended channel...");
        } else if (step.step === "message_generated") {
          setThinkingStatus("Generating copywriting variations with GPT-4o...");
        } else if (step.step === "campaign_preview") {
          setThinkingStatus("Assembling visual campaign previews...");
        } else if (step.step === "campaign_launched") {
          setThinkingStatus("Dispatching campaign async...");
        } else {
          setThinkingStatus("Copilot is executing tool: " + step.step);
        }

        let delay = 1000;
        if (step.step === "segment_built") delay = 1200;
        else if (step.step === "channel_suggested") delay = 800;
        else if (step.step === "message_generated") delay = 1500;
        else if (step.step === "campaign_preview") delay = 600;

        await new Promise((resolve) => setTimeout(resolve, delay));

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, steps: [...(msg.steps || []), step] }
              : msg
          )
        );
      }

      // Complete the flow with final message
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? { ...msg, text: finalMessageText }
            : msg
        )
      );

    } catch (err: any) {
      console.error(err);
      const errorMsg: Message = {
        id: uuidv4(),
        sender: "assistant",
        text: "I encountered an error connecting to the backend. Please ensure the CRM backend is running on port 8000 and try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsThinking(false);
      setThinkingStatus("Copilot is running campaign tools...");
    }
  };

  // Launch Campaign approval trigger
  const handleLaunchCampaign = async (variant: "A" | "B", templateText: string) => {
    setIsLaunching(true);
    // Submit approval message programmatically with the edited template
    const approvalText = `Launch the campaign using Variant ${variant}`;
    await handleSendMessage(approvalText, templateText);
    setIsLaunching(false);
  };

  // Trigger campaign message draft regeneration
  const handleRegenerateMessages = async (messageId: string, selectedTokens?: string[]) => {
    if (regeneratingMessageIds.includes(messageId)) return;
    
    // Add message ID to regenerating state
    setRegeneratingMessageIds(prev => [...prev, messageId]);

    let msgText = "Regenerate the message drafts";
    if (selectedTokens && selectedTokens.length > 0) {
      msgText += ` using variables: ${selectedTokens.join(", ")}`;
    }

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: msgText,
          edited_template: null,
          agent_framework: agentFramework,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to regenerate messages");
      }

      const data = await response.json();
      const allSteps = data.steps || [];

      // Extract new message_generated and campaign_preview steps
      const newGenStep = allSteps.find((s: any) => s.step === "message_generated");
      const newPreviewStep = allSteps.find((s: any) => s.step === "campaign_preview");

      if (newGenStep || newPreviewStep) {
        setMessages((prevMessages) =>
          prevMessages.map((msg) => {
            if (msg.id !== messageId) return msg;

            // Update original steps list, replacing message_generated/campaign_preview
            // and keeping segment_built/channel_suggested intact.
            const updatedSteps = (msg.steps || []).map((step) => {
              if (step.step === "message_generated" && newGenStep) {
                return { ...step, ...newGenStep };
              }
              if (step.step === "campaign_preview" && newPreviewStep) {
                return { ...step, ...newPreviewStep };
              }
              return step;
            });

            return {
              ...msg,
              steps: updatedSteps,
            };
          })
        );
      }
    } catch (err) {
      console.error("Failed to regenerate message in-place:", err);
    } finally {
      // Remove message ID from regenerating state
      setRegeneratingMessageIds(prev => prev.filter(id => id !== messageId));
    }
  };

  // Clear Session & Reset Conversation
  const handleResetSession = async () => {
    if (!sessionId) return;
    try {
      await fetch(`${API_BASE}/chat/${sessionId}`, { method: "DELETE" });
    } catch (err) {
      console.error("Failed to delete backend session:", err);
    }

    const nextSessionId = uuidv4();
    setSessionId(nextSessionId);
    goalProcessed.current = false;
    setInputValue("");
    setSelectedVariantText(null);

    const welcomeMessage: Message = {
      id: "welcome",
      sender: "assistant",
      text: "Session cleared. What campaign goal would you like to target next?",
      timestamp: new Date(),
    };
    setMessages([welcomeMessage]);
  };

  const handleToggleFramework = (target: "custom" | "langchain") => {
    if (target === agentFramework) return;

    if (agentFramework === "custom") {
      setCustomSessionId(sessionId);
      setCustomMessages(messages);

      setSessionId(langchainSessionId);
      setMessages(langchainMessages);
    } else {
      setLangchainSessionId(sessionId);
      setLangchainMessages(messages);

      setSessionId(customSessionId);
      setMessages(customMessages);
    }

    setAgentFramework(target);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex flex-col flex-1 h-[calc(100vh-6rem)]">
      {/* Chat Top Actions */}
      <div className="flex items-center justify-between border-b border-zinc-200/80 pb-4 mb-4">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="rounded-lg border border-zinc-200 bg-white p-1.5 text-zinc-500 hover:text-zinc-950 hover:bg-zinc-50 shadow-3xs transition-all hover:scale-[1.03] active:scale-[0.97]"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-sm font-semibold text-zinc-950 flex items-center gap-1.5">
              <Sparkles className="h-4 w-4 text-indigo-600 animate-pulse" />
              AI Campaign Copilot
            </h1>
            <p className="text-4xs text-zinc-400 font-mono tracking-wide uppercase mt-0.5">Session: {sessionId.slice(0, 8)}</p>
          </div>
        </div>

        {/* Mobile View Toggle */}
        <div className="flex lg:hidden rounded-lg border border-zinc-200 bg-zinc-50 p-0.5 shadow-3xs">
          <button
            onClick={() => setMobileActiveTab("chat")}
            className={`rounded px-2.5 py-1 text-3xs font-bold transition-all ${
              mobileActiveTab === "chat" ? "bg-white text-zinc-950 shadow-3xs" : "text-zinc-400 hover:text-zinc-650"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setMobileActiveTab("preview")}
            className={`rounded px-2.5 py-1 text-3xs font-bold transition-all flex items-center gap-1 ${
              mobileActiveTab === "preview" ? "bg-white text-zinc-950 shadow-3xs" : "text-zinc-400 hover:text-zinc-650"
            }`}
          >
            Preview
            {latestStep && (
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-600 animate-pulse" />
            )}
          </button>
        </div>

        {/* Agent Engine Toggle */}
        <div className="hidden sm:flex items-center gap-1 rounded-xl border border-zinc-200 bg-zinc-50 p-1 shadow-3xs">
          <button
            onClick={() => handleToggleFramework("custom")}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-4xs font-bold uppercase tracking-wider transition-all border ${
              agentFramework === "custom"
                ? "bg-white text-zinc-950 shadow-3xs border-zinc-200"
                : "text-zinc-400 hover:text-zinc-650 border-transparent bg-transparent"
            }`}
            title="Custom optimized pipeline (1 LLM call max, rotates keys, pronoun parser)"
          >
            <Sparkles className={`h-3 w-3 ${agentFramework === "custom" ? "text-indigo-600 animate-pulse" : ""}`} />
            Custom Engine
          </button>
          <button
            onClick={() => handleToggleFramework("langchain")}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-4xs font-bold uppercase tracking-wider transition-all border ${
              agentFramework === "langchain"
                ? "bg-white text-zinc-950 shadow-3xs border-zinc-200"
                : "text-zinc-400 hover:text-zinc-650 border-transparent bg-transparent"
            }`}
            title="LangChain / LangGraph prototype state machine"
          >
            <Cpu className={`h-3 w-3 ${agentFramework === "langchain" ? "text-emerald-600" : ""}`} />
            LangChain Engine
          </button>
        </div>

        <button
          onClick={handleResetSession}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-3xs font-semibold text-zinc-700 hover:bg-zinc-50 transition-all focus:outline-none shadow-3xs hover:scale-[1.01] active:scale-[0.99]"
        >
          <RefreshCw className="h-3 w-3" />
          Reset Chat
        </button>
      </div>

      {/* Main 60/40 Split Panels */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-10 gap-6 min-h-0">
        {/* Left Conversation Thread Panel (60%) */}
        <div className={`lg:col-span-6 flex flex-col rounded-xl border border-zinc-200 bg-white shadow-3xs overflow-hidden h-full ${
          mobileActiveTab === "chat" ? "flex" : "hidden lg:flex"
        }`}>
          <div 
            className="flex-1 overflow-y-auto p-5 space-y-6 custom-scrollbar bg-zinc-50/15"
            style={{ 
              backgroundImage: "radial-gradient(#e4e4e7 1px, transparent 1px)", 
              backgroundSize: "16px 16px" 
            }}
          >
            {messages.map((msg) => {
              const isUser = msg.sender === "user";
              return (
                <div key={msg.id} className="space-y-4">
                  {/* Text Message Bubble */}
                  <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[88%] rounded-2xl px-4 py-3 text-xs leading-relaxed transition-all duration-200 ${
                        isUser
                          ? "bg-gradient-to-br from-zinc-900 to-zinc-800 text-white font-medium shadow-sm border border-zinc-950/20 rounded-tr-none"
                          : "bg-white border border-zinc-200/80 text-zinc-800 shadow-3xs border-l-4 border-l-indigo-600 rounded-tl-none"
                      }`}
                    >
                      {isUser ? (
                        <p className="whitespace-pre-wrap">{msg.text}</p>
                      ) : (
                        <MarkdownRenderer content={msg.text} />
                      )}
                    </div>
                  </div>

                  {/* Render steps under assistant messages if available */}
                  {!isUser && msg.steps && msg.steps.length > 0 && (
                    <div className="space-y-4 max-w-[95%] pl-4 border-l-2 border-indigo-100/60 mt-2 animate-fade-in">
                      {msg.steps.map((step, idx) => (
                        <StepCard
                          key={`${msg.id}-step-${idx}`}
                          stepData={step}
                          onLaunch={handleLaunchCampaign}
                          isLaunching={isLaunching}
                          onActiveTemplateChange={setSelectedVariantText}
                          onRegenerate={(tokens) => handleRegenerateMessages(msg.id, tokens)}
                          isRegenerating={regeneratingMessageIds.includes(msg.id)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Thinking / Skeletal Loading State */}
            {isThinking && (
              <div className="space-y-4 max-w-[95%] pl-4 border-l-2 border-zinc-200 animate-pulse">
                <div className="flex items-center gap-2 text-2xs text-zinc-400 font-medium">
                  <div className="flex space-x-1">
                    <span className="h-1.5 w-1.5 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="h-1.5 w-1.5 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="h-1.5 w-1.5 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                  <span>{thinkingStatus}</span>
                </div>
                <div className="h-20 bg-zinc-50/50 rounded-xl border border-zinc-200/80" />
              </div>
            )}

            <div ref={threadEndRef} />
          </div>

          {/* Bottom Chat Bar input */}
          <div className="border-t border-zinc-150 p-4 bg-zinc-50/30">
            <div className="relative flex items-center">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder="Describe your campaign goal (e.g. 'Win back top churners')"
                rows={1}
                disabled={isThinking || isLaunching}
                className="w-full rounded-xl border border-zinc-250 bg-white py-3.5 pl-4 pr-12 text-xs text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-600/20 focus:border-indigo-600 transition-all resize-none min-h-[46px] max-h-[120px] custom-scrollbar shadow-3xs"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={isThinking || isLaunching || !inputValue.trim()}
                className="absolute right-2.5 rounded-lg bg-indigo-600 p-2 text-white hover:bg-indigo-700 transition-all disabled:opacity-30 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-indigo-500/20 shadow-3xs hover:scale-[1.03] active:scale-[0.97]"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
            
            {/* Suggested prompts helper / Info Badges */}
            <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2 border-t border-zinc-150/80 pt-3 text-4xs text-zinc-500">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700 border border-emerald-100/80">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  INR (₹) Templates Active
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-2 py-0.5 font-semibold text-indigo-700 border border-indigo-100/80">
                  <Sparkles className="h-3.5 w-3.5 text-indigo-600 animate-pulse" />
                  Personalization Active
                </span>
              </div>
              <div className="flex items-center gap-1 text-zinc-400 font-mono text-5xs bg-zinc-50 rounded-lg border border-zinc-200 px-2 py-0.5">
                <span>Variables:</span>
                <code className="text-indigo-600 bg-white border border-zinc-150 px-1 rounded font-bold">name</code>
                <code className="text-indigo-600 bg-white border border-zinc-150 px-1 rounded font-bold">last_order_date</code>
              </div>
            </div>
          </div>
        </div>

        {/* Right Preview Panel (40%) */}
        <div className={`lg:col-span-4 h-full min-h-[300px] lg:min-h-0 ${
          mobileActiveTab === "preview" ? "block" : "hidden lg:block"
        }`}>
          <PreviewPanel
            latestStep={latestStep}
            selectedVariantText={selectedVariantText}
          />
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={
      <div className="flex-1 flex flex-col justify-center items-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900" />
        <span className="mt-4 text-xs font-medium text-zinc-500">Initializing Copilot...</span>
      </div>
    }>
      <ChatPageContent />
    </Suspense>
  );
}
