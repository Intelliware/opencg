import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface LoginFormProps {
  /** Same-origin path to return to after signing in. */
  next: string;
  /** Show the "incorrect password" message. */
  error?: boolean;
}

// Plain HTML form (no client JS) posting to /api/auth/login.
export function LoginForm({ next, error = false }: LoginFormProps) {
  return (
    <Card className="mx-auto mt-16 max-w-sm">
      <CardContent className="space-y-4 p-6">
        <div className="space-y-1">
          <h1 className="text-lg font-semibold">Sign in to openCG</h1>
          <p className="text-sm text-muted-foreground">
            This admin UI is protected by a shared access password.
          </p>
        </div>
        <form method="post" action="/api/auth/login" className="space-y-3">
          <input type="hidden" name="next" value={next} />
          <div className="space-y-1.5">
            <Label htmlFor="password">Access password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              autoFocus
            />
          </div>
          {error ? (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              Incorrect password.
            </p>
          ) : null}
          <Button type="submit" className="w-full">
            Sign in
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
