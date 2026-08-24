export interface ApiError {
  code: string;
  detail: string;
  action?: string;
}

interface RequestErrorCopy {
  detail: string;
  action: string;
}

async function readError(
  response: Response,
  fallback: RequestErrorCopy,
): Promise<ApiError> {
  try {
    const body = (await response.json()) as Partial<ApiError>;
    return {
      code: body.code || "request_failed",
      detail: body.detail || fallback.detail,
      action: body.action,
    };
  } catch {
    return {
      code: "request_failed",
      detail: fallback.detail,
      action: fallback.action,
    };
  }
}

export async function requestJson<T>(
  input: string,
  fallback: RequestErrorCopy,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw {
      code: "network_error",
      detail: fallback.detail,
      action: fallback.action,
    } satisfies ApiError;
  }
  if (!response.ok) {
    throw await readError(response, fallback);
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw {
      code: "invalid_response",
      detail: "The server returned an unreadable response.",
      action: fallback.action,
    } satisfies ApiError;
  }
}
