#!/usr/bin/env bash
# config.sh — Configuratie voor kvk-cli
#
# Gebruikt dezelfde KvK Test API als de MCP-server (mcp/servers/kvk/server.py).
# In productie worden deze waarden via omgevingsvariabelen gezet.

KVK_API_BASE="${KVK_API_BASE:-https://api.kvk.nl/test/api}"
KVK_API_KEY="${KVK_API_KEY:-l7xx1f2691f2520d487b902f4e0b57a0b197}"
# Geen hardcoded demo-bedrijf (MVP-01/PDR-009): de host injecteert het
# sessie-KvK per aanroep via deze env-var. Leeg default => geen bedrijf voor
# iedereen; standalone CLI-gebruik vereist een expliciete KVK_SESSIE_NUMMER.
KVK_SESSIE_NUMMER="${KVK_SESSIE_NUMMER:-}"
KVK_AUDIT_LOG="${KVK_AUDIT_LOG:-}"
