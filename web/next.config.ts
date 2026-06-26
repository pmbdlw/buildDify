import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 产出独立运行包(.next/standalone),便于 Docker 精简运行镜像
  output: "standalone",
};

export default nextConfig;
