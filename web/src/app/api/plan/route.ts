import Anthropic from "@anthropic-ai/sdk";
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { PLANNING_SYSTEM_PROMPT } from "@/lib/planning-prompt";
import { createClient } from "@/utils/supabase/server";
import type { PlanningMessage } from "@/types/inquiry";

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

interface PlanRequest {
  session_id?: string;          // omit on first message (session created here)
  messages: PlanningMessage[];  // full history from client
  grounding_document?: string;  // optional text content of uploaded doc
  grounding_document_label?: string;
}

export async function POST(req: NextRequest) {
  const body: PlanRequest = await req.json();
  const { messages, grounding_document, grounding_document_label } = body;
  let { session_id } = body;

  if (!messages || messages.length === 0) {
    return NextResponse.json({ error: "messages required" }, { status: 400 });
  }

  const supabase = createClient(await cookies());

  // Create a new planning session in Supabase if this is the first message
  if (!session_id) {
    const { data, error } = await supabase
      .from("planning_sessions")
      .insert({})
      .select("id")
      .single();
    if (error) {
      console.error("Failed to create planning session:", error);
      // Non-fatal — continue without persisting
    } else {
      session_id = data.id;
    }
  }

  // Build message list for Anthropic — inject grounding doc as first user turn if present
  let anthropicMessages: Anthropic.MessageParam[] = messages.map((m) => ({
    role: m.role,
    content: m.content,
  }));

  if (grounding_document) {
    // Inject grounding doc into the first user message of the history.
    // This is re-applied on every call so later turns retain the document context.
    const label = grounding_document_label ?? "the provided document";
    const firstUser = anthropicMessages.findIndex((m) => m.role === "user");
    if (firstUser !== -1) {
      anthropicMessages = [...anthropicMessages];
      anthropicMessages[firstUser] = {
        role: "user",
        content: `${String(anthropicMessages[firstUser].content)}\n\n---\nGrounding document (${label}):\n\n${grounding_document}`,
      };
    }
  }

  // Stream the response
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      let fullContent = "";

      try {
        const response = await anthropic.messages.create({
          model: "claude-opus-4-6",
          max_tokens: 4096,
          system: PLANNING_SYSTEM_PROMPT,
          messages: anthropicMessages,
          stream: true,
        });

        for await (const chunk of response) {
          if (
            chunk.type === "content_block_delta" &&
            chunk.delta.type === "text_delta"
          ) {
            const text = chunk.delta.text;
            fullContent += text;
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify({ text })}\n\n`)
            );
          }
        }

        // Persist the assistant message to Supabase
        if (session_id) {
          // Save the user message first, then the assistant response
          const lastUserMessage = messages[messages.length - 1];
          if (lastUserMessage.role === "user") {
            await supabase.from("planning_messages").insert([
              { session_id, role: "user", content: lastUserMessage.content },
              { session_id, role: "assistant", content: fullContent },
            ]);
          }
        }

        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ done: true, session_id })}\n\n`
          )
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ error: message })}\n\n`)
        );
      } finally {
        controller.close();
      }
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
