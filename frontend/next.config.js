/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: [
    "@deck.gl/core",
    "@deck.gl/layers",
    "@deck.gl/geo-layers",
    "@deck.gl/react",
    "@deck.gl/aggregation-layers",
    "@luma.gl/core",
    "@luma.gl/engine",
    "@luma.gl/shadertools",
    "@luma.gl/webgl",
    "@loaders.gl/core",
    "@loaders.gl/loader-utils",
    "maplibre-gl",
  ],
};

module.exports = nextConfig;
