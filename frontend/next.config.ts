import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Other package-lock.json files higher up the folder tree must not be treated as the workspace root.
  turbopack: { root: process.cwd() },
};

export default nextConfig;
