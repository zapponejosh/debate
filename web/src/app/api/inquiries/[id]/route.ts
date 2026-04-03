import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createClient } from "@/utils/supabase/server";
import { getInquiry, listOutputFiles, resumeInquiry } from "@/lib/engine-client";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const [meta, files] = await Promise.all([
      getInquiry(id),
      listOutputFiles(id),
    ]);
    return NextResponse.json({ ...meta, files });
  } catch {
    const supabase = createClient(await cookies());
    const { data, error } = await supabase
      .from("inquiries")
      .select("*")
      .eq("id", id)
      .single();
    if (error || !data) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json(data);
  }
}

// POST /api/inquiries/[id] → resume the inquiry
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const result = await resumeInquiry(id);
    const supabase = createClient(await cookies());
    await supabase
      .from("inquiries")
      .update({ status: "running", error: null })
      .eq("id", id);
    return NextResponse.json(result);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
