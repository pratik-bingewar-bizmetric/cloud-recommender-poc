//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import react from '@vitejs/plugin-react-swc';
import { rayfinLocalDev } from '@microsoft/rayfin-local-dev/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, type PluginOption } from 'vite';
import license from 'rollup-plugin-license';

import { resolve } from 'path';
import { execSync } from 'node:child_process';

// Build identity: lets anyone prove which frontend build a deployment is serving. It is a commit
// SHA + UTC build time (no secrets), exposed three ways: `__BUILD_INFO__` in the bundle, a
// <meta name="finops-build"> tag in index.html, and /build-info.json in the output folder.
function git(args: string): string {
  try {
    return execSync(`git ${args}`, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    return '';
  }
}
const buildInfo = {
  commit: git('rev-parse --short=12 HEAD') || 'unknown',
  branch: git('rev-parse --abbrev-ref HEAD') || 'unknown',
  // true when the working tree had uncommitted changes at build time
  dirty: git('status --porcelain').length > 0,
  builtAt: new Date().toISOString(),
};
const buildInfoPlugin: PluginOption = {
  name: 'finops-build-info',
  transformIndexHtml() {
    return [
      {
        tag: 'meta',
        attrs: {
          name: 'finops-build',
          content: `${buildInfo.commit}${buildInfo.dirty ? '+dirty' : ''}@${buildInfo.builtAt}`,
        },
        injectTo: 'head',
      },
    ];
  },
  generateBundle() {
    this.emitFile({
      type: 'asset',
      fileName: 'build-info.json',
      source: JSON.stringify(buildInfo, null, 2),
    });
  },
};

const projectRoot = process.env.PROJECT_ROOT || import.meta.dirname;

// Dev-only middleware: makes the local Vite server compatible with browsers that
// enforce Local Network Access (LNA) checks when a public origin (the Fabric portal)
// embeds an iframe pointing at http://localhost. Sets the LNA opt-in response header
// on every response and short-circuits the corresponding preflight OPTIONS request.
// This is required for fetch/XHR subresources from the embedded app — top-level
// iframe navigations additionally require launching Chromium with the
// `--disable-features=...LocalNetworkAccessChecks` flag (a browser flag your test tooling must set).
const localNetworkAccessPlugin: PluginOption = {
  name: 'local-network-access-headers',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      res.setHeader('Access-Control-Allow-Private-Network', 'true');
      if (
        req.method === 'OPTIONS' &&
        req.headers['access-control-request-private-network']
      ) {
        const origin = req.headers.origin || '*';
        res.setHeader('Access-Control-Allow-Origin', origin);
        res.setHeader('Access-Control-Allow-Credentials', 'true');
        res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
        res.setHeader(
          'Access-Control-Allow-Headers',
          req.headers['access-control-request-headers'] || '*'
        );
        res.statusCode = 204;
        res.end();
        return;
      }
      next();
    });
  },
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    rayfinLocalDev({ autoLogin: true, sourceActivity: true }),
    localNetworkAccessPlugin,
    buildInfoPlugin,
  ],
  define: {
    __BUILD_INFO__: JSON.stringify(buildInfo),
  },
  resolve: {
    alias: {
      '@': resolve(projectRoot, 'src'),
    },
    // Capability packages are linked during monorepo development. Force their
    // React imports onto the app's instance so production builds cannot bundle
    // a second dispatcher and fail hooks at runtime.
    dedupe: ['react', 'react-dom'],
  },
  build: {
    commonjsOptions: {
      include: [/node_modules/],
    },
    rollupOptions: {
      // Sign-in helper pages (MSAL v5 redirect bridge and popup relay) are separate entries.
      input: {
        main: resolve(projectRoot, 'index.html'),
        redirect: resolve(projectRoot, 'redirect.html'),
        'popup-relay': resolve(projectRoot, 'popup-relay.html'),
      },
      plugins: [
        license({
          thirdParty: {
            multipleVersions: true,
            output: {
              file: resolve(projectRoot, 'dist', 'THIRD_PARTY_NOTICES.txt'),
              template(dependencies) {
                if (dependencies.length === 0) {
                  return 'No third-party dependencies.';
                }
                return (
                  'This file was auto-generated at build time.\n\n' +
                  dependencies
                    .map((dep) => {
                      const lines = [
                        `${dep.name}@${dep.version}`,
                        `License: ${dep.license || 'UNKNOWN'}`,
                      ];
                      if (dep.author) {
                        lines.push(
                          `Author: ${typeof dep.author === 'string' ? dep.author : dep.author.text()}`
                        );
                      }
                      if (dep.noticeText) {
                        lines.push('', 'NOTICE:', dep.noticeText.trim());
                      }
                      if (dep.licenseText) {
                        lines.push('', dep.licenseText.trim());
                      }
                      return lines.join('\n');
                    })
                    .join('\n\n' + '='.repeat(60) + '\n\n')
                );
              },
            },
          },
        }),
      ],
    },
  },
});
