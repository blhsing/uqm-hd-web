import { sites } from '@openai/sites-vite-plugin';
import tailwindcss from '@tailwindcss/postcss';
import vinext from 'vinext';
import { defineConfig, type Plugin } from 'vite';
import hostingConfig from './.openai/hosting.json';

const SITE_CREATOR_PLACEHOLDER_DATABASE_ID =
  '00000000-0000-4000-8000-000000000000';

const { d1, r2 } = hostingConfig;

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === 'seatbelt';

const localBindingConfig = {
  main: 'vinext/server/app-router-entry',
  compatibility_flags: ['nodejs_compat'],
  d1_databases: d1
    ? [
        {
          binding: d1,
          database_name: 'site-creator-d1',
          database_id: SITE_CREATOR_PLACEHOLDER_DATABASE_ID,
        },
      ]
    : [],
  r2_buckets: r2
    ? [
        {
          binding: r2,
          bucket_name: 'site-creator-r2',
        },
      ]
    : [],
};

export default defineConfig(async ({ command }) => {
  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= 'false';
  process.env.WRANGLER_LOG_PATH ??= '.wrangler/logs';
  process.env.MINIFLARE_REGISTRY_PATH ??= '.wrangler/registry';

  // Wrangler snapshots its log path while the Cloudflare plugin is imported.
  const cloudflarePlugin =
    command === 'build'
      ? (await import('@cloudflare/vite-plugin')).cloudflare({
          viteEnvironment: { name: 'rsc', childEnvironments: ['ssr'] },
          config: localBindingConfig,
        })
      : null;

  const isolationHeaders = {
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Embedder-Policy': 'require-corp',
    'Cross-Origin-Resource-Policy': 'same-origin',
  };
  const isolationPlugin: Plugin = {
    name: 'uqm-cross-origin-isolation',
    configureServer(server) {
      server.middlewares.use((_request, response, next) => {
        const applyHeaders = () => {
          for (const [name, value] of Object.entries(isolationHeaders)) {
            response.setHeader(name, value);
          }
        };
        const writeHead = response.writeHead.bind(response);
        response.writeHead = ((...args: Parameters<typeof response.writeHead>) => {
          applyHeaders();
          return writeHead(...args);
        }) as typeof response.writeHead;
        applyHeaders();
        next();
      });
    },
  };
  const publicDirectory: string | false = process.env.SITES_BUILD === '1'
    ? false
    : 'public';

  return {
    // The Sites launcher embeds the full Azure game engine. Its build must not
    // duplicate the ignored 760 MiB local game output into the worker bundle.
    publicDir: publicDirectory,
    css: { postcss: { plugins: [tailwindcss()] } },
    server: {
      headers: isolationHeaders,
      ...(isCodexSeatbeltSandbox
        ? { watch: { useFsEvents: false, usePolling: true } }
        : {}),
    },
    preview: { headers: isolationHeaders },
    plugins: [
      isolationPlugin,
      vinext(),
      sites(),
      ...(cloudflarePlugin ? [cloudflarePlugin] : []),
    ],
  };
});
