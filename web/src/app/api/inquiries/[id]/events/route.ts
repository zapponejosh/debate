import { NextRequest } from "next/server";

const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8000";

/**
 * SSE proxy: browser connects here, we forward to the engine.
 * This ensures the browser only needs to reach Next.js, not the engine directly.
 * The engine URL may be an internal Docker network address inaccessible to browsers.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const engineRes = await fetch(`${ENGINE_URL}/inquiries/${id}/events`, {
    headers: { Accept: "text/event-stream" },
  });

  if (!engineRes.ok || !engineRes.body) {
    return new Response("Engine SSE unavailable", { status: 502 });
  }

  // Stream the engine's SSE response directly to the client
  return new Response(engineRes.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no", // Disable nginx buffering if deployed behind it
    },
  });
}
