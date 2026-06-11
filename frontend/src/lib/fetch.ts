import { isJsonObject, object, string } from "./validation.ts";

export class FetchError extends Error {}

export interface StructuredError {
  readonly error: string;
  readonly code?: string;
  readonly details?: Record<string, unknown>;
}

export class FetchHTTPError extends FetchError {
  readonly status: number;
  readonly code?: string;
  readonly details?: Record<string, unknown>;

  constructor(
    message: string | null,
    status: number,
    code?: string,
    details?: Record<string, unknown>,
  ) {
    super(
      message != null
        ? `HTTP ${status.toString()} - ${message}`
        : `HTTP ${status.toString()}`,
    );
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export class FetchInvalidResponseError extends FetchError {
  constructor(msg: string) {
    super(`Invalid response: ${msg}`);
  }
}

const error_message_validator = object({ error: string });

/**
 * Extract structured error info from a JSON response body if present.
 */
function extract_structured_error(
  json: unknown,
): { message: string; code?: string; details?: Record<string, unknown> } | null {
  if (!isJsonObject(json)) return null;
  const validated = error_message_validator(json);
  if (validated.isOk()) {
    const message = validated.value.error;
    const code = typeof json.code === "string" ? json.code : undefined;
    const details =
      json.details != null && typeof json.details === "object"
        ? (json.details as Record<string, unknown>)
        : undefined;
    return { message, code, details };
  }
  return null;
}

/**
 * Fetch JSON content, also handling an HTTP error status.
 *
 * Checks for an object at the top JSON level. For errors, looks
 * for an error message like `{ "error": "error message" }` as well
 * as optional `code` and `details` fields.
 */
export async function fetch_json(
  input: URL,
  init?: RequestInit,
): Promise<Record<string, unknown>> {
  const response = await fetch(input, init);
  const json: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const structured = extract_structured_error(json);
    throw new FetchHTTPError(
      structured?.message ?? null,
      response.status,
      structured?.code,
      structured?.details,
    );
  }
  if (!isJsonObject(json)) {
    throw new FetchInvalidResponseError("Not a valid JSON object");
  }
  return json;
}

/**
 * Fetch text content, also handling an HTTP error status.
 */
export async function fetch_text(
  input: string | URL,
  init?: RequestInit,
): Promise<string> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const message = await response.text().catch(() => null);
    throw new FetchHTTPError(message, response.status);
  }
  return response.text();
}
