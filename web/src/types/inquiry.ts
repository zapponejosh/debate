// -----------------------------------------------------------------------
// Inquiry config types (mirrors scripts/inquiry_schema.py)
// -----------------------------------------------------------------------

export type RoundType =
  | "parallel_statements"
  | "paired_exchange"
  | "moderator_synthesis"
  | "panel_qa";

export type ModelChoice = "sonnet" | "opus" | "haiku";
export type PositionDirection = "for" | "against" | "neutral";
export type InquiryFormat = "debate" | "panel";

export interface TemperatureSettings {
  participants: number;
  moderator: number;
  verifier: number;
  language_tasks: number;
}

export interface Settings {
  anti_convergence: boolean;
  citation_protocol: boolean;
  temperature: TemperatureSettings;
}

export interface Pairing {
  questioner: string;
  target: string;
  tension: string;
}

export interface RoundConfig {
  key: string;
  title: string;
  type: RoundType;
  prompt_template: string;
  synthesis_prompt?: string;
  response_prompt?: string;
  model: ModelChoice;
  word_limit: number;
  verify_citations: boolean;
  run_moderation: boolean;
  generate_digest: boolean;
  generate_claim_ledger: boolean;
  pairings: Pairing[];
  required_texts: string[];
  reversed_speaking_order: boolean;
  use_compressed_context: boolean;
  user_prompt?: string;
}

export interface Participant {
  id: string;
  display_name: string;
  role: string;
  system_prompt: string;
  position_direction: PositionDirection;
}

export interface ModeratorConfig {
  system_prompt: string;
  fact_check_prompt?: string;
}

export interface InquiryDefinition {
  title: string;
  question: string;
  format: InquiryFormat;
  grounding_document?: string;
  grounding_document_label?: string;
  shared_context?: string;
}

export interface InquiryConfig {
  version: "2.0";
  inquiry: InquiryDefinition;
  participants: Participant[];
  moderator: ModeratorConfig;
  rounds: RoundConfig[];
  settings: Settings;
}

// -----------------------------------------------------------------------
// Inquiry run status (from server.py)
// -----------------------------------------------------------------------

export type InquiryStatus =
  | "planning"
  | "running"
  | "completed"
  | "failed"
  | "waiting_for_input";

export interface InquiryMeta {
  id: string;
  title: string;
  status: InquiryStatus;
  current_round: string | null;
  current_participant: string | null;
  created_at: string;
  output_dir: string;
  error?: string;
}

export interface OutputFile {
  path: string;
  size: number;
  modified: string;
}

// -----------------------------------------------------------------------
// SSE event types
// -----------------------------------------------------------------------

export type SSEEventType =
  | "started"
  | "round_started"
  | "round_completed"
  | "participant_started"
  | "file_written"
  | "completed"
  | "error"
  | "done";

export interface SSEEvent {
  type: SSEEventType;
  round?: string;
  title?: string;
  participant?: string;
  display_name?: string;
  text?: string;
  error?: string;
  status?: InquiryStatus;
}

// -----------------------------------------------------------------------
// Planning agent types
// -----------------------------------------------------------------------

export interface PlanningMessage {
  role: "user" | "assistant";
  content: string;
}

export interface PlanningSession {
  id: string;
  messages: PlanningMessage[];
  pending_config?: Partial<InquiryConfig>;
  created_at: string;
}

// -----------------------------------------------------------------------
// Verification types
// -----------------------------------------------------------------------

export type VerificationVerdict =
  | "VERIFIED"
  | "FABRICATED"
  | "NEEDS_REVIEW"
  | "UNVERIFIABLE";

export interface CitationVerification {
  citation_id: string;
  participant_id: string;
  round_key: string;
  claim: string;
  source: string;
  verdict: VerificationVerdict;
  pass1_result?: string;
  pass2_result?: string;
  pass3_result?: string;
  notes?: string;
}
