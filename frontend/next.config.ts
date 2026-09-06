import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for the Docker image (server.js + minimal node_modules).
  output: "standalone",
};

export default nextConfig;
