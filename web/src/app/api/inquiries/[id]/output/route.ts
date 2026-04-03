import { NextRequest, NextResponse } from "next/server";
import { getOutputFile } from "@/lib/engine-client";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const path = req.nextUrl.searchParams.get("path");

  if (!path) {
    return NextResponse.json({ error: "path required" }, { status: 400 });
  }

  try {
    const content = await getOutputFile(id, path);
    const isJson = path.endsWith(".json");
    return new NextResponse(content, {
      headers: {
        "Content-Type": isJson ? "application/json" : "text/plain; charset=utf-8",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 404 });
  }
}
