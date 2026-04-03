"use client";

import type { InquiryConfig } from "@/types/inquiry";

const ROUND_TYPE_LABELS: Record<string, string> = {
  parallel_statements: "Parallel Statements",
  paired_exchange: "Cross-Examination",
  moderator_synthesis: "Moderator Synthesis",
  panel_qa: "Panel Q&A",
};

export function ConfigPreview({ config }: { config: InquiryConfig }) {
  return (
    <div className="w-full px-5 py-6 space-y-6 text-sm">
      <div>
        <p className="text-xs uppercase tracking-widest text-zinc-500 mb-2">
          Inquiry
        </p>
        <p className="font-medium text-zinc-200">{config.inquiry.title}</p>
        <p className="text-zinc-400 mt-1 leading-relaxed">
          {config.inquiry.question}
        </p>
        <span className="mt-2 inline-block rounded px-2 py-0.5 text-xs bg-zinc-800 text-zinc-400 capitalize">
          {config.inquiry.format}
        </span>
      </div>

      <div>
        <p className="text-xs uppercase tracking-widest text-zinc-500 mb-3">
          Participants ({config.participants.length})
        </p>
        <ul className="space-y-2">
          {config.participants.map((p) => (
            <li key={p.id} className="flex items-start gap-2">
              <span className="mt-0.5 h-2 w-2 rounded-full bg-zinc-500 flex-shrink-0" />
              <div>
                <span className="text-zinc-200">{p.display_name}</span>
                <p className="text-xs text-zinc-500 mt-0.5">{p.role}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="text-xs uppercase tracking-widest text-zinc-500 mb-3">
          Rounds ({config.rounds.length})
        </p>
        <ol className="space-y-2">
          {config.rounds.map((r, i) => (
            <li key={r.key} className="flex items-start gap-2">
              <span className="text-zinc-600 text-xs mt-0.5 w-4 flex-shrink-0">
                {i + 1}.
              </span>
              <div>
                <span className="text-zinc-300">{r.title}</span>
                <p className="text-xs text-zinc-500 mt-0.5">
                  {ROUND_TYPE_LABELS[r.type] ?? r.type} · {r.model}
                  {r.verify_citations && " · citations verified"}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      {config.inquiry.grounding_document_label && (
        <div>
          <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">
            Grounding Document
          </p>
          <p className="text-zinc-400">{config.inquiry.grounding_document_label}</p>
        </div>
      )}
    </div>
  );
}
