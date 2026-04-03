// Re-export the appropriate client for each context.
// - Server components / API routes: import { createClient } from "@/utils/supabase/server"
// - Client components: import { createClient } from "@/utils/supabase/client"
//
// This module exports a singleton browser client for legacy use in API routes
// that don't need cookie-based session handling (all our current DB operations
// use the anon key and don't involve user auth).

export { createClient } from "@/utils/supabase/client";
