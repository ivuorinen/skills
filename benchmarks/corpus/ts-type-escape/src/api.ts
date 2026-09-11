export interface User {
  id: string;
  email: string;
  admin: boolean;
}

export async function fetchRaw(url: string): Promise<unknown> {
  const res = await fetch(url);
  return res.json();
}

export async function fetchUser(url: string): Promise<User> {
  const body = await fetchRaw(url);
  return body as User;
}

export function isUser(value: unknown): value is User {
  const v = value as Record<string, unknown>;
  return typeof v?.id === "string" && typeof v?.email === "string";
}
