import type { NextConfig } from 'next';

const azureStaticBuild = process.env.AZURE_STATIC_BUILD === '1';

const nextConfig: NextConfig = {
  ...(azureStaticBuild
    ? {
        output: 'export' as const,
        basePath: '/starcontrol2',
        assetPrefix: '/starcontrol2',
        trailingSlash: true,
      }
    : {
        async headers() {
          return [
            {
              source: '/:path*',
              headers: [
                { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
                { key: 'Cross-Origin-Embedder-Policy', value: 'require-corp' },
                { key: 'Cross-Origin-Resource-Policy', value: 'same-origin' },
                { key: 'X-Content-Type-Options', value: 'nosniff' },
              ],
            },
          ];
        },
      }),
};

export default nextConfig;
