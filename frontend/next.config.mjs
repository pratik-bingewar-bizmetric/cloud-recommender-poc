/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      "cytoscape-fcose": false,
    };
    return config;
  },
};

export default nextConfig;
