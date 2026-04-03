import { listInquiries } from "@/lib/engine-client";
import type { InquiryMeta } from "@/types/inquiry";
import Link from "next/link";

const STATUS_COLORS: Record<string, string> = {
  running: "bg-yellow-500/20 text-yellow-300",
  completed: "bg-green-500/20 text-green-300",
  failed: "bg-red-500/20 text-red-300",
  planning: "bg-zinc-700 text-zinc-400",
  waiting_for_input: "bg-blue-500/20 text-blue-300",
};

export default async function InquiriesListPage() {
  let inquiries: InquiryMeta[] = [];
  try {
    inquiries = await listInquiries();
  } catch {
    // Engine might be offline — render empty list
  }

  return (
    <main className="flex flex-col flex-1 px-6 py-10 max-w-3xl mx-auto w-full">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-xl font-semibold text-zinc-100">Inquiries</h1>
        <Link
          href="/"
          className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          + New Inquiry
        </Link>
      </div>

      {inquiries.length === 0 ? (
        <p className="text-zinc-500 text-sm">
          No inquiries yet.{" "}
          <Link href="/" className="text-zinc-300 hover:underline">
            Start one →
          </Link>
        </p>
      ) : (
        <ul className="space-y-3">
          {inquiries.map((inq) => (
            <li key={inq.id}>
              <Link
                href={`/inquiry/${inq.id}`}
                className="flex items-start justify-between rounded-xl border border-zinc-800 bg-zinc-900 px-5 py-4 hover:border-zinc-700 transition-colors"
              >
                <div>
                  <p className="font-medium text-zinc-200">{inq.title}</p>
                  <p className="text-xs text-zinc-500 mt-1">
                    {new Date(inq.created_at).toLocaleString()}
                  </p>
                </div>
                <span
                  className={`ml-4 flex-shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    STATUS_COLORS[inq.status] ?? "bg-zinc-700 text-zinc-400"
                  }`}
                >
                  {inq.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
