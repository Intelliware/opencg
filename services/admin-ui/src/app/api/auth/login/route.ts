import {
  SESSION_COOKIE,
  SESSION_TTL_MS,
  adminPassword,
  issueSession,
  passwordMatches,
  safeNext,
  seeOther,
} from "@/lib/session";

// HTML form POST from /login. Responds with 303 redirects so the browser
// follows up with a GET.
export async function POST(req: Request) {
  const form = await req.formData();
  const next = safeNext(form.get("next")?.toString());
  const password = adminPassword();
  if (!password) return seeOther(next);

  const submitted = form.get("password")?.toString() ?? "";
  if (!(await passwordMatches(submitted, password))) {
    return seeOther(`/login?${new URLSearchParams({ next, error: "1" })}`);
  }

  const proto = req.headers.get("x-forwarded-proto") ?? new URL(req.url).protocol.replace(":", "");
  const res = seeOther(next);
  res.cookies.set(SESSION_COOKIE, await issueSession(password), {
    httpOnly: true,
    sameSite: "lax",
    secure: proto === "https",
    path: "/",
    maxAge: SESSION_TTL_MS / 1000,
  });
  return res;
}
