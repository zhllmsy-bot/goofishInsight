export function requestUrl(input: RequestInfo | URL): URL {
  if (typeof input === 'string') {
    return new URL(input, 'http://localhost');
  }
  if (input instanceof URL) {
    return new URL(input.toString(), 'http://localhost');
  }
  return new URL(input.url, 'http://localhost');
}

export function requestBodyText(body: BodyInit | null | undefined): string {
  if (body === null || body === undefined) {
    return '{}';
  }
  if (typeof body === 'string') {
    return body;
  }
  if (body instanceof URLSearchParams) {
    return body.toString();
  }
  if (body instanceof FormData) {
    return JSON.stringify(Object.fromEntries(body.entries()));
  }
  return '{}';
}
