"use client";

import { useState, useEffect, useRef, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { PlanningMessage, InquiryConfig } from "@/types/inquiry";
import { ConfigPreview } from "@/components/planning/ConfigPreview";
import { normalizeConfig } from "@/lib/normalize-config";

function PlanPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [messages, setMessages] = useState<PlanningMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [pendingConfig, setPendingConfig] = useState<InquiryConfig | null>(null);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);

  // Seed the first user message from URL params
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    const q = searchParams.get("q");
    if (!q) return;

    const firstMessage: PlanningMessage = { role: "user", content: q };
    setMessages([firstMessage]);
    sendToAgent([firstMessage]);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  async function sendToAgent(history: PlanningMessage[]) {
    setStreaming(true);
    setError(null);

    // Always read grounding doc from sessionStorage so it's re-sent on every
    // turn and the API can keep it in the first message context window.
    const groundingDoc = sessionStorage.getItem("grounding_document") ?? undefined;
    const groundingLabel = sessionStorage.getItem("grounding_document_label") ?? undefined;

    // Append a placeholder for the assistant response
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          messages: history,
          grounding_document: groundingDoc || undefined,
          grounding_document_label: groundingLabel || undefined,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`API error: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6));

          if (data.text) {
            fullText += data.text;
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: fullText,
              };
              return updated;
            });
          }

          if (data.session_id) {
            setSessionId(data.session_id);
          }

          if (data.done) {
            // Check if the final message contains a JSON config block
            const config = extractConfig(fullText);
            if (config) setPendingConfig(config);
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setMessages((prev) => prev.slice(0, -1)); // remove empty assistant placeholder
    } finally {
      setStreaming(false);
    }
  }

  function extractConfig(text: string): InquiryConfig | null {
    const match = text.match(/```json\n([\s\S]*?)\n```/);
    if (!match) return null;
    try {
      return normalizeConfig(JSON.parse(match[1]));
    } catch {
      return null;
    }
  }

  async function handleSubmit(e: { preventDefault(): void }) {
    e.preventDefault();
    if (!input.trim() || streaming) return;

    const userMessage: PlanningMessage = { role: "user", content: input.trim() };
    const newHistory = [...messages, userMessage];
    setMessages(newHistory);
    setInput("");
    await sendToAgent(newHistory);
  }

  async function launchInquiry() {
    if (!pendingConfig) return;
    setLaunching(true);
    setError(null);

    try {
      const res = await fetch("/api/inquiries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: pendingConfig,
          session_id: sessionId,
        }),
      });

      if (!res.ok) {
        const body = await res.json();
        throw new Error(body.error ?? `Launch failed: ${res.status}`);
      }

      const { id } = await res.json();
      router.push(`/inquiry/${id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setLaunching(false);
    }
  }

  return (
    <div className="flex flex-1 h-screen overflow-hidden">
      {/* Chat panel */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div>
            <h1 className="text-sm font-medium text-zinc-300">Planning</h1>
            <p className="text-xs text-zinc-500 mt-0.5">
              Design your inquiry with the planning agent
            </p>
          </div>
          <a href="/" className="text-xs text-zinc-500 hover:text-zinc-300">
            ← Back
          </a>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {messages.map((msg, i) => (
            <ChatMessage key={i} message={msg} />
          ))}
          {error && (
            <div className="rounded-lg bg-red-900/30 border border-red-800 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Launch bar — appears when config is ready */}
        {pendingConfig && (
          <div className="border-t border-zinc-800 bg-zinc-900/60 px-6 py-3 flex items-center gap-3">
            <span className="text-sm text-zinc-400 flex-1">
              Config ready:{" "}
              <span className="text-zinc-200">{pendingConfig.inquiry.title}</span>
            </span>
            <button
              onClick={() => {
                setPendingConfig(null);
                setMessages((prev) => [
                  ...prev,
                  {
                    role: "user",
                    content: "Let me adjust a few things first.",
                  },
                ]);
              }}
              className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5"
            >
              Keep editing
            </button>
            <button
              onClick={launchInquiry}
              disabled={launching}
              className="rounded-lg bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-50 transition-colors"
            >
              {launching ? "Launching..." : "Launch Inquiry →"}
            </button>
          </div>
        )}

        {/* Input */}
        <div className="border-t border-zinc-800 px-6 py-4">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none"
              placeholder={streaming ? "Thinking..." : "Reply to the planning agent..."}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={streaming}
            />
            <button
              type="submit"
              disabled={!input.trim() || streaming}
              className="rounded-lg bg-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-100 hover:bg-zinc-600 disabled:opacity-40 transition-colors"
            >
              Send
            </button>
          </form>
        </div>
      </div>

      {/* Config preview sidebar */}
      {pendingConfig && (
        <div className="hidden lg:flex w-80 border-l border-zinc-800 overflow-y-auto">
          <ConfigPreview config={pendingConfig} />
        </div>
      )}
    </div>
  );
}

function ChatMessage({ message }: { message: PlanningMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-zinc-700 text-zinc-100"
            : "bg-zinc-900 border border-zinc-800 text-zinc-200"
        }`}
      >
        {message.content || (
          <span className="text-zinc-500 animate-pulse">●●●</span>
        )}
      </div>
    </div>
  );
}

export default function PlanPage() {
  return (
    <Suspense>
      <PlanPageInner />
    </Suspense>
  );
}
