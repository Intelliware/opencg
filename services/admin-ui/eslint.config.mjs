// ESLint flat config for the admin UI. Next 16 ships native flat configs in
// eslint-config-next, so no FlatCompat shim is needed.
import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  {
    ignores: [".next/**", "storybook-static/**", "playwright-report/**", "test-results/**", "next-env.d.ts"],
  },
  ...coreWebVitals,
  ...typescript,
  {
    // Node scripts run with plain `node`, outside the Next build.
    files: ["scripts/**/*.cjs"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
];

export default config;
