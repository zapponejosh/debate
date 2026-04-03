import type { InquiryConfig } from "@/types/inquiry";

/**
 * Normalize a config object that may use field names hallucinated by the
 * planning agent (e.g. central_question, name, round_number) into the
 * canonical InquiryConfig shape the engine expects.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function normalizeConfig(raw: any): InquiryConfig {
  // --- inquiry ---
  const rawInquiry = raw.inquiry ?? {};
  const inquiry = {
    title: rawInquiry.title ?? rawInquiry.central_question ?? rawInquiry.topic ?? "",
    question: rawInquiry.question ?? rawInquiry.central_question ?? rawInquiry.topic ?? "",
    format: rawInquiry.format ?? raw.format ?? "debate",
    ...(rawInquiry.shared_context ? { shared_context: rawInquiry.shared_context } : {}),
    ...(rawInquiry.grounding_document ? { grounding_document: rawInquiry.grounding_document } : {}),
    ...(rawInquiry.grounding_document_label
      ? { grounding_document_label: rawInquiry.grounding_document_label }
      : {}),
  };

  // --- participants ---
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const participants = (raw.participants ?? []).map((p: any) => ({
    id: p.id ?? p.role?.toLowerCase().replace(/\s+/g, "_") ?? "participant",
    display_name: p.display_name ?? p.name ?? p.id ?? "Participant",
    role: p.role ?? p.display_name ?? p.name ?? "",
    system_prompt: p.system_prompt ?? "",
    position_direction: p.position_direction ?? "neutral",
  }));

  // --- moderator ---
  // The agent sometimes puts a "moderator" participant in the participants
  // array but omits the top-level moderator field. Extract it either way.
  const rawMod = raw.moderator ??
    raw.participants?.find((p: any) => p.id === "moderator" || p.role?.toLowerCase().includes("moderator")) ??
    {};
  const moderator = {
    system_prompt: rawMod.system_prompt ?? "",
    ...(rawMod.fact_check_prompt ? { fact_check_prompt: rawMod.fact_check_prompt } : {}),
  };

  // --- rounds ---
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rounds = (raw.rounds ?? []).map((r: any, i: number) => ({
    key: r.key ?? r.id ?? `round_${i + 1}`,
    title: r.title ?? r.name ?? `Round ${i + 1}`,
    type: r.type ?? "parallel_statements",
    prompt_template: r.prompt_template ?? r.prompt ?? r.description ?? "",
    ...(r.synthesis_prompt ? { synthesis_prompt: r.synthesis_prompt } : {}),
    ...(r.response_prompt ? { response_prompt: r.response_prompt } : {}),
    model: r.model ?? "sonnet",
    word_limit: r.word_limit ?? r.max_tokens_per_response ?? 400,
    verify_citations: r.verify_citations ?? false,
    run_moderation: r.run_moderation ?? false,
    generate_digest: r.generate_digest ?? false,
    generate_claim_ledger: r.generate_claim_ledger ?? false,
    pairings: (r.pairings ?? []).map((pair: any) =>
      typeof pair === "object"
        ? { questioner: pair.questioner ?? "", target: pair.target ?? "", tension: pair.tension ?? "" }
        : { questioner: "", target: "", tension: "" }
    ),
    required_texts: [],
    reversed_speaking_order: r.reversed_speaking_order ?? false,
    use_compressed_context: r.use_compressed_context ?? false,
    ...(r.user_prompt ? { user_prompt: r.user_prompt } : {}),
  }));

  // --- settings ---
  const rawSettings = raw.settings ?? {};
  const rawTemp = rawSettings.temperature ?? {};
  const settings = {
    anti_convergence: rawSettings.anti_convergence ?? true,
    citation_protocol: rawSettings.citation_protocol ?? true,
    temperature: {
      participants: rawTemp.participants ?? 0.9,
      moderator: rawTemp.moderator ?? 0.7,
      verifier: rawTemp.verifier ?? 0.3,
      language_tasks: rawTemp.language_tasks ?? 0.3,
    },
  };

  return { version: "2.0", inquiry, participants, moderator, rounds, settings };
}
