import { redirect } from "next/navigation";

import { LoginForm } from "@/components/LoginForm";
import { adminPassword, safeNext } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const params = await searchParams;
  const next = safeNext(params.next);
  // Nothing to sign in to when the gate is disabled.
  if (!adminPassword()) redirect(next);
  return <LoginForm next={next} error={params.error === "1"} />;
}
