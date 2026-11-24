/**
 * EdgeMind Backend REST API Endpoints.
 * Derived directly from core/api.py and router declarations.
 */

export const Endpoints = {
  HEALTH: '/health',
  ANALYZE: '/api/v1/analyze',
  EDGEMIND_ANALYZE: '/api/v1/edgemind/analyze',
  AGENT_ANALYZE: '/api/v1/agent/analyze',
  AGENT_STREAM: '/api/v1/agent/analyze/stream',
} as const;
