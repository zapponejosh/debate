import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createClient } from "@/utils/supabase/server";
import { createInquiry, listInquiries } from "@/lib/engine-client";
import type { InquiryConfig } from "@/types/inquiry";

interface CreateRequest {
  config: InquiryConfig;
  session_id?: string;
  force?: boolean;
}

export async function POST(req: NextRequest) {
  const body: CreateRequest = await req.json();
  const { config, session_id, force = false } = body;

  if (!config) {
    return NextResponse.json({ error: "config required" }, { status: 400 });
  }

  // Start the inquiry on the Python engine
  let engineResult: { id: string; status: string };
  try {
    engineResult = await createInquiry(config, force);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: `Engine error: ${message}` },
      { status: 502 }
    );
  }

  const supabase = createClient(await cookies());
  const inquiryId = engineResult.id;

  const { error: dbError } = await supabase.from("inquiries").upsert({
    id: inquiryId,
    title: config.inquiry.title,
    question: config.inquiry.question,
    format: config.inquiry.format,
    status: "running",
    config,
    grounding_document: config.inquiry.grounding_document ?? null,
    grounding_document_label: config.inquiry.grounding_document_label ?? null,
  });

  if (dbError) {
    console.error("Supabase upsert failed:", dbError);
    // Non-fatal — engine is running, DB is just a mirror
  }

  if (session_id) {
    await supabase
      .from("planning_sessions")
      .update({ inquiry_id: inquiryId })
      .eq("id", session_id);
  }

  return NextResponse.json({ id: inquiryId, status: "running" });
}

export async function GET() {
  try {
    const inquiries = await listInquiries();
    return NextResponse.json(inquiries);
  } catch {
    const supabase = createClient(await cookies());
    const { data, error } = await supabase
      .from("inquiries")
      .select("id, title, status, format, created_at")
      .order("created_at", { ascending: false });

    if (error) {
      return NextResponse.json({ error: "Engine and DB unreachable" }, { status: 503 });
    }
    return NextResponse.json(data);
  }
}
