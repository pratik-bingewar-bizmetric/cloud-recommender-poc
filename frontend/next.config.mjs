/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allows an isolated verification instance (NEXT_DIST_DIR) beside a running dev server.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  webpack: (config) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      "cytoscape-fcose": false,
    };
    return config;
  },
  async rewrites() {
    const backendUrl = process.env.INTERNAL_BACKEND_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
      {
        source: "/health/:path*",
        destination: `${backendUrl}/health/:path*`,
      },
      {
        source: "/docs",
        destination: `${backendUrl}/docs`,
      },
      {
        source: "/openapi.json",
        destination: `${backendUrl}/openapi.json`,
      },
    ];
  },
};

export default nextConfig;
