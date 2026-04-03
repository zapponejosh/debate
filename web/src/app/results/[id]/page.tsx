import { getInquiry, getOutputFile, listOutputFiles } from "@/lib/engine-client";
import { ResultsBrowserClient } from "@/components/results/ResultsBrowserClient";
import { notFound } from "next/navigation";

export default async function ResultsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let meta, files;
  try {
    [meta, files] = await Promise.all([getInquiry(id), listOutputFiles(id)]);
  } catch {
    notFound();
  }

  // Load the canonical record (main readable document)
  const canonicalFile = files.find(
    (f) => f.path.endsWith("canonical_record.md") || f.path.endsWith("canonical_record.txt")
  );
  let canonicalText = "";
  if (canonicalFile) {
    try {
      canonicalText = await getOutputFile(id, canonicalFile.path);
    } catch {
      // Not yet generated — ok
    }
  }

  // Load verification summary JSONs
  const verificationFiles = files.filter(
    (f) => f.path.includes("verification") && f.path.endsWith(".json")
  );
  const verifications: Array<Record<string, unknown>> = [];
  for (const vf of verificationFiles) {
    try {
      const raw = await getOutputFile(id, vf.path);
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        verifications.push(...parsed);
      } else {
        verifications.push(parsed);
      }
    } catch {
      // Skip malformed files
    }
  }

  return (
    <ResultsBrowserClient
      meta={meta}
      files={files}
      canonicalText={canonicalText}
      verifications={verifications}
      inquiryId={id}
    />
  );
}
