import test from 'node:test';
import assert from 'node:assert/strict';

// Test Cloud Icons & Registry
import {
  CLOUD_ICON_REGISTRY,
  NEUTRAL_FALLBACK_ICON,
  PROVIDER_BRANDS,
  getServiceIcon,
  detectDiagramProvider,
  enrichMermaidWithIcons,
  svgToDataUri,
} from '../src/lib/cloudIcons';

// Test Diagram Export Builder
import {
  buildStandaloneExportSvg,
  generateExportFilename,
} from '../src/lib/diagramExport';

test('Provider Branding - Azure and GCP have official identities', () => {
  const azureBrand = PROVIDER_BRANDS.azure;
  assert.ok(azureBrand, 'Azure brand must be defined');
  assert.equal(azureBrand.id, 'azure');
  assert.equal(azureBrand.name, 'Microsoft Azure');
  assert.ok(azureBrand.svg.includes('<svg'), 'Azure brand must have valid SVG');
  assert.ok(azureBrand.dataUri.startsWith('data:image/svg+xml;base64,'), 'Azure brand must have dataUri');

  const gcpBrand = PROVIDER_BRANDS.gcp;
  assert.ok(gcpBrand, 'GCP brand must be defined');
  assert.equal(gcpBrand.id, 'gcp');
  assert.equal(gcpBrand.name, 'Google Cloud Platform');
  assert.ok(gcpBrand.svg.includes('<svg'), 'GCP brand must have valid SVG');
  assert.ok(gcpBrand.dataUri.startsWith('data:image/svg+xml;base64,'), 'GCP brand must have dataUri');
});

test('Service Icon Mapping - Azure core services', () => {
  const vmIcon = getServiceIcon('azure-virtual-machines');
  assert.equal(vmIcon.id, 'azure-virtual-machines');
  assert.equal(vmIcon.provider, 'azure');
  assert.equal(vmIcon.category, 'compute');

  const acaIcon = getServiceIcon('azure-container-apps');
  assert.equal(acaIcon.id, 'azure-container-apps');

  const appServiceIcon = getServiceIcon('Microsoft.Web/sites', 'azure');
  assert.equal(appServiceIcon.id, 'azure-app-service');

  const pgIcon = getServiceIcon('PostgreSQL Flexible Server', 'azure');
  assert.equal(pgIcon.id, 'azure-postgresql');

  const blobIcon = getServiceIcon('Azure Blob Storage', 'azure');
  assert.equal(blobIcon.id, 'azure-storage');

  const fdIcon = getServiceIcon('Azure Front Door', 'azure');
  assert.equal(fdIcon.id, 'azure-front-door');

  const kvIcon = getServiceIcon('Azure Key Vault', 'azure');
  assert.equal(kvIcon.id, 'azure-key-vault');

  const foundryIcon = getServiceIcon('Azure AI Foundry', 'azure');
  assert.equal(foundryIcon.id, 'azure-ai-foundry');

  const wafIcon = getServiceIcon('Azure WAF Policy', 'azure');
  assert.equal(wafIcon.id, 'azure-waf');

  const monIcon = getServiceIcon('Azure Monitor / Log Analytics', 'azure');
  assert.equal(monIcon.id, 'azure-monitor');
});

test('Service Icon Mapping - GCP core services', () => {
  const runIcon = getServiceIcon('gcp-cloud-run');
  assert.equal(runIcon.id, 'gcp-cloud-run');
  assert.equal(runIcon.provider, 'gcp');

  const sqlIcon = getServiceIcon('Cloud SQL for PostgreSQL', 'gcp');
  assert.equal(sqlIcon.id, 'gcp-cloud-sql');

  const gcsIcon = getServiceIcon('Google Cloud Storage', 'gcp');
  assert.equal(gcsIcon.id, 'gcp-cloud-storage');

  const cdnIcon = getServiceIcon('Cloud Load Balancing + CDN', 'gcp');
  assert.equal(cdnIcon.id, 'gcp-cloud-cdn');

  const armorIcon = getServiceIcon('Cloud Armor WAF', 'gcp');
  assert.equal(armorIcon.id, 'gcp-cloud-armor');

  const vertexIcon = getServiceIcon('Vertex AI (Gemini)', 'gcp');
  assert.equal(vertexIcon.id, 'gcp-vertex-ai');

  const secretIcon = getServiceIcon('Secret Manager', 'gcp');
  assert.equal(secretIcon.id, 'gcp-secret-manager');

  const monIcon = getServiceIcon('Cloud Monitoring', 'gcp');
  assert.equal(monIcon.id, 'gcp-cloud-monitoring');
});

test('Service Icon Mapping - Unknown and empty fallback', () => {
  const unknown1 = getServiceIcon('unsupported-custom-widget-1234');
  assert.equal(unknown1.id, NEUTRAL_FALLBACK_ICON.id);
  assert.equal(unknown1.provider, 'neutral');

  const unknown2 = getServiceIcon('');
  assert.equal(unknown2.id, NEUTRAL_FALLBACK_ICON.id);

  const unknown3 = getServiceIcon('   ');
  assert.equal(unknown3.id, NEUTRAL_FALLBACK_ICON.id);
});

test('Diagram Provider Detection', () => {
  assert.equal(detectDiagramProvider('flowchart TD\n subgraph Azure["Azure Blueprint"]', 'Topology'), 'azure');
  assert.equal(detectDiagramProvider('flowchart TD\n subgraph GCP["GCP Blueprint"]', 'Topology'), 'gcp');
  assert.equal(detectDiagramProvider('flowchart TD\n subgraph Azure\n end\n subgraph GCP\n end', 'Comparison'), 'multi');
  assert.equal(detectDiagramProvider('graph TD\n A --> B', 'Generic Topology'), 'neutral');
  assert.equal(detectDiagramProvider('graph TD\n A --> B', 'Generic', 'azure'), 'azure');
});

test('Mermaid DSL Enrichment with Icons', () => {
  const dsl = `flowchart TD
  subgraph Azure["Azure Architecture"]
    AFD["<b>Azure Front Door</b><br/>Standard Profile<br/><b>$40.50/mo</b>"]:::netNode
    ACA["<b>Azure Container Apps</b><br/>0.5 vCPU<br/><b>$32.40/mo</b>"]:::computeNode
    APSQL[("<b>PostgreSQL Flexible Server</b><br/>Standard_D2ds_v4 HA<br/><b>$164.25/mo</b>")]:::dbNode
    AFD --> ACA
    ACA --> APSQL
  end`;

  const enriched = enrichMermaidWithIcons(dsl, 'azure');

  // Verify icons were injected
  assert.ok(enriched.includes("class='cloud-node-icon'"), 'Must contain injected icon classes');
  assert.ok(enriched.includes(CLOUD_ICON_REGISTRY['azure-front-door'].dataUri), 'Must contain Front Door icon dataUri');
  assert.ok(enriched.includes(CLOUD_ICON_REGISTRY['azure-container-apps'].dataUri), 'Must contain Container Apps icon dataUri');
  assert.ok(enriched.includes(CLOUD_ICON_REGISTRY['azure-postgresql'].dataUri), 'Must contain PostgreSQL icon dataUri');

  // Verify relationships and classes are fully preserved
  assert.ok(enriched.includes('AFD --> ACA'), 'Must preserve AFD --> ACA edge');
  assert.ok(enriched.includes('ACA --> APSQL'), 'Must preserve ACA --> APSQL edge');
  assert.ok(enriched.includes(':::netNode'), 'Must preserve :::netNode class');
  assert.ok(enriched.includes(':::computeNode'), 'Must preserve :::computeNode class');
  assert.ok(enriched.includes(':::dbNode'), 'Must preserve :::dbNode class');

  // Calling enrich again should not double-inject
  const doubleEnriched = enrichMermaidWithIcons(enriched, 'azure');
  const count1 = (enriched.match(/cloud-node-icon/g) || []).length;
  const count2 = (doubleEnriched.match(/cloud-node-icon/g) || []).length;
  assert.equal(count1, count2, 'Must not duplicate icons on subsequent passes');
});

test('Standalone Export SVG Builder - Structure & Banner & Legend', () => {
  const sampleSvg = `<svg viewBox="0 0 800 500" width="100%" height="100%">
    <style>.node { fill: red; }</style>
    <g class="node"><rect width="100" height="40"/></g>
  </svg>`;

  const { standaloneSvg, width, height } = buildStandaloneExportSvg(sampleSvg, {
    title: 'Azure Production Subscription',
    provider: 'azure',
    includeBanner: true,
    includeLegend: true,
  });

  assert.ok(standaloneSvg.startsWith('<?xml version="1.0" encoding="UTF-8"?>'), 'Must include XML declaration');
  assert.ok(standaloneSvg.includes('<svg xmlns="http://www.w3.org/2000/svg"'), 'Must have root SVG and namespaces');
  assert.ok(standaloneSvg.includes('viewBox="0 0'), 'Must have explicit viewBox');
  assert.ok(standaloneSvg.includes('fill="#ffffff"'), 'Must include solid white canvas background');

  // Header Banner checks
  assert.ok(standaloneSvg.includes('Azure Production Subscription'), 'Must include diagram title in banner');
  assert.ok(standaloneSvg.includes('FinOps &amp; Infrastructure Intelligence Platform'), 'Must include platform branding');
  assert.ok(standaloneSvg.includes(PROVIDER_BRANDS.azure.dataUri), 'Must embed Azure provider brand logo');

  // Legend checks
  assert.ok(standaloneSvg.includes('Legend:'), 'Must include legend section');
  assert.ok(standaloneSvg.includes('Compute'), 'Legend must list Compute');
  assert.ok(standaloneSvg.includes('Database'), 'Legend must list Database');
  assert.ok(standaloneSvg.includes('Storage'), 'Legend must list Storage');
  assert.ok(standaloneSvg.includes('Network'), 'Legend must list Network');
  assert.ok(standaloneSvg.includes('Security'), 'Legend must list Security');
  assert.ok(standaloneSvg.includes('AI / ML'), 'Legend must list AI / ML');
  assert.ok(standaloneSvg.includes('Verified Link'), 'Legend must list Verified Link');
  assert.ok(standaloneSvg.includes('Inferred Tier'), 'Legend must list Inferred Tier');

  assert.ok(width > 800, 'Width must account for padding');
  assert.ok(height > 500, 'Height must account for banner and legend');
});

test('Export Filename Generator', () => {
  const azName = generateExportFilename('Production Azure Topology', 'azure', 'png');
  assert.ok(azName.startsWith('azure-production-azure-topology-'), 'Azure filename must include prefix and slug');
  assert.ok(azName.endsWith('.png'), 'Must have .png extension');

  const gcpSvgName = generateExportFilename('GCP Project Hierarchy', 'gcp', 'svg');
  assert.ok(gcpSvgName.startsWith('gcp-project-hierarchy-'), 'GCP filename must include prefix and slug');
  assert.ok(gcpSvgName.endsWith('.svg'), 'Must have .svg extension');
});

