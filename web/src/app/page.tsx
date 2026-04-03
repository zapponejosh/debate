"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.type === "text/plain") setFile(dropped);
  }

  async function handleStart(e: { preventDefault(): void }) {
    e.preventDefault();
    if (!question.trim()) return;

    // Read file content if provided
    let fileContent: string | undefined;
    let fileLabel: string | undefined;
    if (file) {
      fileContent = await file.text();
      fileLabel = file.name;
    }

    const params = new URLSearchParams({ q: question.trim() });
    if (fileContent) {
      // Pass via sessionStorage to avoid URL size limits
      sessionStorage.setItem("grounding_document", fileContent);
      sessionStorage.setItem("grounding_document_label", fileLabel ?? "");
      params.set("has_grounding", "1");
    }

    router.push(`/plan?${params.toString()}`);
  }

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-24">
      <div className="w-full max-w-2xl">
        <div className="mb-10">
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-100">
            Inquiry Framework
          </h1>
          <p className="mt-2 text-zinc-400">
            Multi-agent structured inquiry with citation verification. Enter a
            question and a planning agent will help you design the inquiry.
          </p>
        </div>

        <form onSubmit={handleStart} className="flex flex-col gap-4">
          <textarea
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none resize-none min-h-[100px]"
            placeholder="What question do you want to explore? Be as specific or as open-ended as you like."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />

          {/* Optional grounding document upload */}
          <div
            className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-4 text-sm cursor-pointer transition-colors ${
              dragging
                ? "border-zinc-400 bg-zinc-800"
                : "border-zinc-700 hover:border-zinc-600"
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".txt"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <span className="text-zinc-300">
                {file.name}{" "}
                <button
                  type="button"
                  className="ml-2 text-zinc-500 hover:text-zinc-300"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                  }}
                >
                  remove
                </button>
              </span>
            ) : (
              <span className="text-zinc-500">
                Optional: drop a .txt grounding document here
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={!question.trim()}
            className="self-end rounded-lg bg-zinc-100 px-6 py-2.5 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Start Planning →
          </button>
        </form>

        {/* Recent inquiries link — rendered only if there might be some */}
        <div className="mt-8 border-t border-zinc-800 pt-6">
          <a
            href="/inquiry"
            className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            View past inquiries →
          </a>
        </div>
      </div>
    </main>
  );
}
