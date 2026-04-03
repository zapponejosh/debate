/**
 * HTTP client for the Python engine (server.py).
 * All calls go through the ENGINE_URL env var (default: http://localhost:8000).
 */

import type {
  InquiryConfig,
  InquiryMeta,
  OutputFile,
} from "@/types/inquiry";

const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8000";

async function engineFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${ENGINE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Engine ${path} → ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export async function createInquiry(
  config: InquiryConfig,
  force = false
): Promise<{ id: string; status: string }> {
  return engineFetch("/inquiries", {
    method: "POST",
    body: JSON.stringify({ config, force }),
  });
}

export async function listInquiries(): Promise<InquiryMeta[]> {
  return engineFetch("/inquiries");
}

export async function getInquiry(id: string): Promise<InquiryMeta> {
  return engineFetch(`/inquiries/${id}`);
}

export async function listOutputFiles(id: string): Promise<OutputFile[]> {
  return engineFetch(`/inquiries/${id}/files`);
}

export async function getOutputFile(
  id: string,
  path: string
): Promise<string> {
  const res = await fetch(`${ENGINE_URL}/inquiries/${id}/outputs/${path}`);
  if (!res.ok) throw new Error(`Engine output ${path} → ${res.status}`);
  return res.text();
}

export async function resumeInquiry(
  id: string
): Promise<{ id: string; status: string }> {
  return engineFetch(`/inquiries/${id}/resume`, { method: "POST" });
}

/** Returns the SSE URL for an inquiry (used client-side via EventSource). */
export function inquiryEventsUrl(id: string): string {
  return `${ENGINE_URL}/inquiries/${id}/events`;
}
