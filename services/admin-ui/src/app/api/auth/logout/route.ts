import { SESSION_COOKIE, seeOther } from "@/lib/session";

export async function POST() {
  const res = seeOther("/login");
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
