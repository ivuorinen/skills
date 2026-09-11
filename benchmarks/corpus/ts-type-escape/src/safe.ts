import { isUser, fetchRaw, User } from "./api";

export async function fetchUserChecked(url: string): Promise<User> {
  const body = await fetchRaw(url);
  if (!isUser(body)) {
    throw new Error("not a user");
  }
  return body;
}
