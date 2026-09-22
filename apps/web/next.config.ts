import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The local workbench uses the lower-left corner for persistent navigation.
  // Runtime and build errors still surface through Next.js' error overlay.
  devIndicators: false,
};

export default nextConfig;
