import type { NextConfig } from "next";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

const nextConfig: NextConfig = {
  compress: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiBase}/:path*` },
    ];
  },
};

export default nextConfig;
