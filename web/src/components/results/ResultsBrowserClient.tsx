"use client";

import { useState } from "react";
import Link from "next/link";
import type { InquiryMeta, OutputFile } from "@/types/inquiry";

type View = "reading" | "overview";

const VERDICT_STYLES: Record<string, { dot: string; label: string }> = {
  VERIFIED: { dot: "bg-green-500", label: "Verified" },
  FABRICATED: { dot: "bg-red-500", label: "Fabricated" },
  NEEDS_REVIEW: { dot: "bg-yellow-500", label: "Needs review" },
  UNVERIFIABLE: { dot: "bg-zinc-500", label: "Unverifiable" },
};

interface Props {
  meta: InquiryMeta;
  files: OutputFile[];
  canonicalText: string;
  verifications: Array<Record<string, unknown>>;
  inquiryId: string;
}

export function ResultsBrowserClient({
  meta,
  files,
  canonicalText,
  verifications,
  inquiryId,
}: Props) {
  const [view, setView] = useState<View>(canonicalText ? "reading" : "overview");
  const [expandedCitation, setExpandedCitation] = useState<string | null>(null);

  // Aggregate verification stats
  const stats = computeStats(verifications);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">{meta.title}</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            {new Date(meta.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* View toggle */}
          <div className="flex rounded-lg border border-zinc-700 overflow-hidden text-sm">
            <button
              onClick={() => setView("reading")}
              className={`px-3 py-1.5 transition-colors ${
                view === "reading"
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Reading
            </button>
            <button
              onClick={() => setView("overview")}
              className={`px-3 py-1.5 transition-colors ${
                view === "overview"
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Overview
            </button>
          </div>
          <Link
            href={`/inquiry/${inquiryId}`}
            className="text-sm text-zinc-500 hover:text-zinc-300"
          >
            ← Dashboard
          </Link>
        </div>
      </div>

      {/* Verification stats bar */}
      {verifications.length > 0 && (
        <div className="flex items-center gap-6 px-6 py-3 border-b border-zinc-800 bg-zinc-900/40 text-sm">
          <span className="text-zinc-400">
            {verifications.length} citations verified
          </span>
          <StatPill
            color="bg-green-500"
            label="Verified"
            count={stats.VERIFIED}
            total={verifications.length}
          />
          <StatPill
            color="bg-yellow-500"
            label="Needs review"
            count={stats.NEEDS_REVIEW}
            total={verifications.length}
          />
          <StatPill
            color="bg-red-500"
            label="Fabricated"
            count={stats.FABRICATED}
            total={verifications.length}
          />
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {view === "reading" ? (
          <ReadingView
            canonicalText={canonicalText}
            verifications={verifications}
            expandedCitation={expandedCitation}
            onCitationClick={setExpandedCitation}
          />
        ) : (
          <OverviewView
            files={files}
            verifications={verifications}
            inquiryId={inquiryId}
            expandedCitation={expandedCitation}
            onCitationClick={setExpandedCitation}
          />
        )}
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------
// Reading view — annotated canonical record
// -----------------------------------------------------------------------

function ReadingView({
  canonicalText,
  verifications,
  expandedCitation,
  onCitationClick,
}: {
  canonicalText: string;
  verifications: Array<Record<string, unknown>>;
  expandedCitation: string | null;
  onCitationClick: (id: string | null) => void;
}) {
  if (!canonicalText) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
        Canonical record not yet available.
      </div>
    );
  }

  // Build citation lookup map
  const citationMap = new Map<string, Record<string, unknown>>();
  for (const v of verifications) {
    const cid = v.citation_id as string;
    if (cid) citationMap.set(cid, v);
  }

  // Render text with inline citation annotations
  const segments = parseTextWithCitations(canonicalText, citationMap);

  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <div className="prose prose-invert prose-zinc max-w-none">
        {segments.map((seg, i) => {
          if (seg.type === "text") {
            return (
              <span key={i} style={{ whiteSpace: "pre-wrap" }}>
                {seg.content}
              </span>
            );
          }

          const cid = seg.citationId!;
          const v = citationMap.get(cid);
          const verdict = (v?.verdict as string) ?? "UNVERIFIABLE";
          const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.UNVERIFIABLE;
          const isExpanded = expandedCitation === cid;

          return (
            <span key={i} className="inline-block relative">
              <button
                onClick={() => onCitationClick(isExpanded ? null : cid)}
                className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-zinc-800 transition-colors text-xs"
              >
                <span className={`h-2 w-2 rounded-full flex-shrink-0 ${style.dot}`} />
                <span className="text-zinc-400">{cid}</span>
              </button>
              {isExpanded && v && (
                <CitationDetail
                  verification={v}
                  onClose={() => onCitationClick(null)}
                />
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------
// Overview view — stats dashboard + file list + flagged citations
// -----------------------------------------------------------------------

function OverviewView({
  files,
  verifications,
  inquiryId,
  expandedCitation,
  onCitationClick,
}: {
  meta?: InquiryMeta;
  files: OutputFile[];
  verifications: Array<Record<string, unknown>>;
  inquiryId: string;
  expandedCitation: string | null;
  onCitationClick: (id: string | null) => void;
}) {
  const flagged = verifications.filter(
    (v) => v.verdict === "FABRICATED" || v.verdict === "NEEDS_REVIEW"
  );

  // Group verifications by participant
  const byParticipant = groupBy(verifications, (v) => v.participant_id as string);

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-10">
      {/* Per-participant breakdown */}
      {Object.keys(byParticipant).length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-zinc-300 mb-4">
            Citation Breakdown by Participant
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left pb-2 text-zinc-500 font-normal">Participant</th>
                  <th className="text-right pb-2 text-zinc-500 font-normal">Total</th>
                  <th className="text-right pb-2 text-zinc-500 font-normal text-green-500">Verified</th>
                  <th className="text-right pb-2 text-zinc-500 font-normal text-yellow-500">Review</th>
                  <th className="text-right pb-2 text-zinc-500 font-normal text-red-500">Flagged</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(byParticipant).map(([pid, pvs]) => {
                  const s = computeStats(pvs);
                  return (
                    <tr key={pid} className="border-b border-zinc-800/50">
                      <td className="py-2 text-zinc-300">{pid}</td>
                      <td className="py-2 text-right text-zinc-400">{pvs.length}</td>
                      <td className="py-2 text-right text-green-400">{s.VERIFIED}</td>
                      <td className="py-2 text-right text-yellow-400">{s.NEEDS_REVIEW}</td>
                      <td className="py-2 text-right text-red-400">{s.FABRICATED}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Flagged citations */}
      {flagged.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-zinc-300 mb-4">
            Flagged Citations ({flagged.length})
          </h2>
          <div className="space-y-2">
            {flagged.map((v, i) => {
              const cid = v.citation_id as string;
              const verdict = v.verdict as string;
              const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.UNVERIFIABLE;
              const isExpanded = expandedCitation === cid;
              return (
                <div
                  key={i}
                  className="rounded-lg border border-zinc-800 bg-zinc-900/50"
                >
                  <button
                    onClick={() => onCitationClick(isExpanded ? null : cid)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-800/50 transition-colors rounded-lg"
                  >
                    <span className={`h-2 w-2 rounded-full flex-shrink-0 ${style.dot}`} />
                    <span className="text-sm text-zinc-300 font-mono">{cid}</span>
                    <span className="text-xs text-zinc-500 ml-1">{style.label}</span>
                    <span className="ml-auto text-xs text-zinc-600">
                      {v.participant_id as string} · {v.round_key as string}
                    </span>
                  </button>
                  {isExpanded && (
                    <div className="px-4 pb-4">
                      <CitationDetail
                        verification={v}
                        onClose={() => onCitationClick(null)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Output files */}
      <section>
        <h2 className="text-sm font-medium text-zinc-300 mb-4">Output Files</h2>
        <ul className="space-y-1">
          {files.map((f) => (
            <li key={f.path}>
              <a
                href={`/api/inquiries/${inquiryId}/output?path=${encodeURIComponent(f.path)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex justify-between rounded-lg px-3 py-2 hover:bg-zinc-800 transition-colors text-sm"
              >
                <span className="text-zinc-300">{f.path}</span>
                <span className="text-zinc-600">
                  {(f.size / 1024).toFixed(1)}kb
                </span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// -----------------------------------------------------------------------
// Citation detail panel
// -----------------------------------------------------------------------

function CitationDetail({
  verification,
  onClose,
}: {
  verification: Record<string, unknown>;
  onClose: () => void;
}) {
  const verdict = verification.verdict as string;
  const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.UNVERIFIABLE;

  return (
    <div className="mt-2 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-4 text-sm space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
          <span className="font-medium text-zinc-200">{style.label}</span>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-300 text-xs"
        >
          close
        </button>
      </div>

      {(verification.claim as string | undefined) && (
        <div>
          <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">Claim</p>
          <p className="text-zinc-300">{verification.claim as string}</p>
        </div>
      )}

      {(verification.source as string | undefined) && (
        <div>
          <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">Source</p>
          <p className="text-zinc-300 font-mono text-xs">{verification.source as string}</p>
        </div>
      )}

      {(verification.pass1_result as string | undefined) && (
        <VerificationPass label="Pass 1 — Training knowledge triage" content={verification.pass1_result as string} />
      )}
      {(verification.pass2_result as string | undefined) && (
        <VerificationPass label="Pass 2 — Bibliographic search" content={verification.pass2_result as string} />
      )}
      {(verification.pass3_result as string | undefined) && (
        <VerificationPass label="Pass 3 — Deep investigation" content={verification.pass3_result as string} />
      )}

      {(verification.notes as string | undefined) && (
        <div>
          <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">Notes</p>
          <p className="text-zinc-400">{verification.notes as string}</p>
        </div>
      )}
    </div>
  );
}

function VerificationPass({ label, content }: { label: string; content: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">{label}</p>
      <p className="text-zinc-400 whitespace-pre-wrap text-xs leading-relaxed">{content}</p>
    </div>
  );
}

// -----------------------------------------------------------------------
// Stat pill
// -----------------------------------------------------------------------

function StatPill({
  color,
  label,
  count,
  total,
}: {
  color: string;
  label: string;
  count: number;
  total: number;
}) {
  if (count === 0) return null;
  const pct = Math.round((count / total) * 100);
  return (
    <span className="flex items-center gap-1.5 text-zinc-400">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {count} {label} ({pct}%)
    </span>
  );
}

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

type TextSegment =
  | { type: "text"; content: string }
  | { type: "citation"; citationId: string };

function parseTextWithCitations(
  text: string,
  citationMap: Map<string, Record<string, unknown>>
): TextSegment[] {
  // Match citation IDs like R1_EC_001 or R2_BS_003
  const CITATION_RE = /\b(R\d+_[A-Z]+_\d{3})\b/g;
  const segments: TextSegment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = CITATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    // Only annotate if we have verification data for this citation
    if (citationMap.has(match[1])) {
      segments.push({ type: "citation", citationId: match[1] });
    } else {
      segments.push({ type: "text", content: match[0] });
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    segments.push({ type: "text", content: text.slice(lastIndex) });
  }

  return segments;
}

function computeStats(verifications: Array<Record<string, unknown>>) {
  return {
    VERIFIED: verifications.filter((v) => v.verdict === "VERIFIED").length,
    FABRICATED: verifications.filter((v) => v.verdict === "FABRICATED").length,
    NEEDS_REVIEW: verifications.filter((v) => v.verdict === "NEEDS_REVIEW").length,
    UNVERIFIABLE: verifications.filter((v) => v.verdict === "UNVERIFIABLE").length,
  };
}

function groupBy<T>(
  arr: T[],
  keyFn: (item: T) => string
): Record<string, T[]> {
  const result: Record<string, T[]> = {};
  for (const item of arr) {
    const key = keyFn(item);
    if (!result[key]) result[key] = [];
    result[key].push(item);
  }
  return result;
}
