/**
 * Platform Feature Flags
 *
 * Controls visibility and enablement of POC modules and experimental workflows.
 */

/**
 * AI Architect (Phase A Requirements-to-Architecture Generation).
 * Set to `false` to hide AI Architect from navigation and quick actions while preserving code.
 * See `docs/hidden-features.md` for architectural reference and re-enablement instructions.
 */
export const ENABLE_AI_ARCHITECT = false;

/**
 * Microsoft Fabric Lakehouse Integration (Phase B Analytics).
 * Preserved as explicitly disabled per operational guardrails.
 */
export const ENABLE_MICROSOFT_FABRIC = false;

/**
 * Amazon Web Services (AWS) Integration.
 * Deferred per operational guardrails.
 */
export const ENABLE_AWS = false;

