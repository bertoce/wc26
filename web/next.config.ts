import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Tell Turbopack the workspace root is this directory, not the system one it
  // inferred from a stray ~/package-lock.json upstream.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
