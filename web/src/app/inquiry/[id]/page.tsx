import { getInquiry, listOutputFiles } from "@/lib/engine-client";
import { InquiryDashboardClient } from "@/components/inquiry/InquiryDashboardClient";
import { notFound } from "next/navigation";

export default async function InquiryPage({
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

  return (
    <InquiryDashboardClient
      initialMeta={meta}
      initialFiles={files}
      engineEventsUrl={`/api/inquiries/${id}/events`}
    />
  );
}
