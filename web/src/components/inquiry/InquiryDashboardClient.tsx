"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import type { InquiryMeta, OutputFile, SSEEvent } from "@/types/inquiry";

const STATUS_COLORS: Record<string, string> = {
  running: "text-yellow-400",
  completed: "text-green-400",
  failed: "text-red-400",
  planning: "text-zinc-400",
  waiting_for_input: "text-blue-400",
};

interface Props {
  initialMeta: InquiryMeta;
  initialFiles: OutputFile[];
  engineEventsUrl: string;
}

interface LogEntry {
  type: string;
  text: string;
  timestamp: Date;
}

export function InquiryDashboardClient({
  initialMeta,
  initialFiles,
  engineEventsUrl,
}: Props) {
  const [meta, setMeta] = useState<InquiryMeta>(initialMeta);
  const [files, setFiles] = useState<OutputFile[]>(initialFiles);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const logBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (meta.status === "completed" || meta.status === "failed") return;

    const es = new EventSource(engineEventsUrl);
    esRef.current = es;
    setConnected(true);

    es.onmessage = (e) => {
      try {
        const data: SSEEvent & Partial<InquiryMeta> = JSON.parse(e.data);

        // Update meta fields if present
        if (data.status) {
          setMeta((prev) => ({
            ...prev,
            status: data.status ?? prev.status,
            current_round: data.current_round ?? prev.current_round ?? null,
            current_participant:
              data.current_participant ?? prev.current_participant ?? null,
          }));
        }

        // Build log entry
        let text = "";
        switch (data.type) {
          case "started":
            text = `Inquiry started: ${data.title ?? ""}`;
            break;
          case "round_started":
            text = `▶ ${data.title ?? data.round}`;
            break;
          case "round_completed":
            text = `✓ ${data.title ?? data.round} complete`;
            break;
          case "participant_started":
            text = `  → ${data.display_name ?? data.participant}`;
            break;
          case "file_written":
            text = `  ${data.text ?? "file written"}`;
            // Refresh file list
            refreshFiles();
            break;
          case "completed":
            text = "Inquiry completed.";
            setConnected(false);
            es.close();
            refreshFiles();
            break;
          case "error":
            text = `Error: ${data.error}`;
            setConnected(false);
            es.close();
            break;
          default:
            return;
        }

        if (text) {
          setLog((prev) => [
            ...prev,
            { type: data.type ?? "info", text, timestamp: new Date() },
          ]);
        }
      } catch {
        // Malformed event — ignore
      }
    };

    es.onerror = () => {
      setConnected(false);
    };

    return () => {
      es.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function refreshFiles() {
    try {
      const res = await fetch(`/api/inquiries/${meta.id}`);
      if (res.ok) {
        const data = await res.json();
        if (data.files) setFiles(data.files);
        if (data.status) setMeta((prev) => ({ ...prev, status: data.status }));
      }
    } catch {
      // Ignore
    }
  }

  async function handleResume() {
    const res = await fetch(`/api/inquiries/${meta.id}`, {
      method: "POST",
    });
    if (res.ok) {
      setMeta((prev) => ({ ...prev, status: "running" }));
      window.location.reload();
    }
  }

  useEffect(() => {
    logBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log]);

  // Group files by directory (round)
  const fileGroups = groupFiles(files);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-start justify-between px-6 py-5 border-b border-zinc-800">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">{meta.title}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span
              className={`text-sm font-medium ${STATUS_COLORS[meta.status] ?? "text-zinc-400"}`}
            >
              {meta.status}
            </span>
            {meta.current_round && (
              <span className="text-sm text-zinc-500">
                {meta.current_round}
                {meta.current_participant && ` · ${meta.current_participant}`}
              </span>
            )}
            {connected && (
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-400" />
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {meta.status === "failed" && (
            <button
              onClick={handleResume}
              className="text-sm text-zinc-400 hover:text-zinc-200 border border-zinc-700 rounded-lg px-3 py-1.5"
            >
              Resume
            </button>
          )}
          {meta.status === "completed" && (
            <Link
              href={`/results/${meta.id}`}
              className="rounded-lg bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900 hover:bg-white transition-colors"
            >
              View Results →
            </Link>
          )}
          <Link href="/inquiry" className="text-sm text-zinc-500 hover:text-zinc-300">
            ← All inquiries
          </Link>
        </div>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Progress log */}
        <div className="flex flex-col w-72 border-r border-zinc-800 min-h-0">
          <div className="px-4 py-3 border-b border-zinc-800">
            <p className="text-xs uppercase tracking-widest text-zinc-500">
              Progress
            </p>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
            {log.length === 0 && meta.status !== "completed" && (
              <p className="text-xs text-zinc-600">
                {connected ? "Connecting..." : "Waiting to start..."}
              </p>
            )}
            {log.map((entry, i) => (
              <div key={i} className="text-xs">
                <span
                  className={
                    entry.type === "round_started"
                      ? "text-zinc-200 font-medium"
                      : entry.type === "completed"
                        ? "text-green-400"
                        : entry.type === "error"
                          ? "text-red-400"
                          : "text-zinc-500"
                  }
                >
                  {entry.text}
                </span>
              </div>
            ))}
            <div ref={logBottomRef} />
          </div>
        </div>

        {/* Output files */}
        <div className="flex flex-col flex-1 min-h-0">
          <div className="px-6 py-3 border-b border-zinc-800">
            <p className="text-xs uppercase tracking-widest text-zinc-500">
              Output Files
            </p>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {files.length === 0 ? (
              <p className="text-sm text-zinc-600">
                {meta.status === "running"
                  ? "Files will appear as rounds complete..."
                  : "No output files yet."}
              </p>
            ) : (
              <div className="space-y-6">
                {Object.entries(fileGroups).map(([group, groupFiles]) => (
                  <div key={group}>
                    {group !== "root" && (
                      <p className="text-xs uppercase tracking-widest text-zinc-500 mb-2">
                        {group}
                      </p>
                    )}
                    <ul className="space-y-1">
                      {groupFiles.map((f) => (
                        <li key={f.path}>
                          <FileLink inquiryId={meta.id} file={f} />
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FileLink({ inquiryId, file }: { inquiryId: string; file: OutputFile }) {
  const name = file.path.split("/").pop() ?? file.path;
  const isMarkdown = name.endsWith(".md");
  const isJson = name.endsWith(".json");

  return (
    <a
      href={`/api/inquiries/${inquiryId}/output?path=${encodeURIComponent(file.path)}`}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-zinc-800 transition-colors group"
    >
      <span className="text-sm text-zinc-300 group-hover:text-zinc-100">
        {name}
      </span>
      <span className="text-xs text-zinc-600">
        {isMarkdown ? "md" : isJson ? "json" : ""}
        {" · "}
        {(file.size / 1024).toFixed(1)}kb
      </span>
    </a>
  );
}

function groupFiles(files: OutputFile[]): Record<string, OutputFile[]> {
  const groups: Record<string, OutputFile[]> = {};
  for (const f of files) {
    const parts = f.path.split("/");
    const group = parts.length > 1 ? parts[0] : "root";
    if (!groups[group]) groups[group] = [];
    groups[group].push(f);
  }
  return groups;
}
