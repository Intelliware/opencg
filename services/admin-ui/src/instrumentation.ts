// Runs once when the Next server starts.
export function register() {
  if (!process.env.OPENCG__ADMIN_UI__PASSWORD) {
    console.warn(
      "[opencg/admin-ui] WARNING: OPENCG__ADMIN_UI__PASSWORD is unset — the admin UI " +
        "is UNAUTHENTICATED (delete, ingest and graph-edit actions are open). " +
        "Keep it on loopback or set a password before exposing it.",
    );
  }
}
