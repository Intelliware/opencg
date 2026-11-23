/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  transpilePackages: ["@opencg/shared"],
  // forbidden() renders src/app/forbidden.tsx when the pipeline answers 403.
  experimental: { authInterrupts: true },
};

export default nextConfig;
