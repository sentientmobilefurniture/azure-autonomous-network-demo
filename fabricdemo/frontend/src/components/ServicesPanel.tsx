import { useState, useEffect, useCallback, useRef } from 'react';
import { useClickOutside } from '../hooks/useClickOutside';
import { useScenario } from '../ScenarioContext';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type ItemStatus = 'idle' | 'checking' | 'ok' | 'error';

interface TreeItem {
  id: string;
  label: string;
  detail?: string;
  status: ItemStatus;
  elapsed?: number;
  /** true = probeable (●), false = display-only (○) */
  probeable: boolean;
  /** Health-check function (null for display-only items) */
  check?: () => Promise<boolean>;
  /** Sub-items (tools, delegates) — display only, not probeable */
  children?: { label: string }[];
}

interface TreeCategory {
  id: string;
  label: string;
  items: TreeItem[];
  collapsed: boolean;
  /** Show 🔄 Rediscover button */
  hasRediscover: boolean;
  /** Rediscover function */
  rediscover?: () => Promise<void>;
  rediscovering: boolean;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function worstStatus(items: TreeItem[]): ItemStatus {
  if (items.some(i => i.status === 'error')) return 'error';
  if (items.some(i => i.status === 'checking')) return 'checking';
  if (items.every(i => i.status === 'ok')) return 'ok';
  if (items.some(i => i.status === 'ok')) return 'ok';
  return 'idle';
}

function statusDot(s: ItemStatus, size = 'h-2 w-2'): string {
  const base = `${size} rounded-full flex-shrink-0 inline-block`;
  switch (s) {
    case 'idle':     return `${base} bg-text-muted`;
    case 'checking': return `${base} bg-status-warning animate-pulse`;
    case 'ok':       return `${base} bg-status-success`;
    case 'error':    return `${base} bg-status-error`;
  }
}

function statusChar(s: ItemStatus): string {
  switch (s) {
    case 'idle':     return '─';
    case 'checking': return '🟠';
    case 'ok':       return '🟢';
    case 'error':    return '🔴';
  }
}

/* ------------------------------------------------------------------ */
/*  ServicesPanel                                                       */
/* ------------------------------------------------------------------ */

interface ServicesPanelProps {
  open: boolean;
  onClose: () => void;
}

export function ServicesPanel({ open, onClose }: ServicesPanelProps) {
  const ref = useRef<HTMLDivElement>(null);
  const scenario = useScenario();
  const hasAutoRun = useRef(false);

  useClickOutside(ref, onClose, open);

  /* ── State ────────────────────────────────────────────────────── */
  const [categories, setCategories] = useState<TreeCategory[]>([]);
  const [checkingAll, setCheckingAll] = useState(false);

  /* ── Category updater helper ──────────────────────────────────── */
  const updateCategory = useCallback((catId: string, updater: (cat: TreeCategory) => TreeCategory) => {
    setCategories(prev => prev.map(c => c.id === catId ? updater(c) : c));
  }, []);

  const updateItem = useCallback((catId: string, itemId: string, updater: (item: TreeItem) => TreeItem) => {
    setCategories(prev => prev.map(c =>
      c.id === catId
        ? { ...c, items: c.items.map(i => i.id === itemId ? updater(i) : i) }
        : c
    ));
  }, []);

  /* ── Discovery functions ──────────────────────────────────────── */

  const discoverFabric = useCallback(async () => {
    updateCategory('fabric', c => ({ ...c, rediscovering: true }));
    try {
      const res = await fetch('/query/health/rediscover', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const items: TreeItem[] = [];

      // Graph (GQL) — probeable
      const graphModel = (data.workspace_items ?? []).find((w: any) => w.type === 'GraphModel');
      items.push({
        id: 'fabric-graph',
        label: 'Graph (GQL)',
        detail: graphModel?.displayName ?? data.graph_model_id ?? 'unknown',
        status: data.fabric_ready ? 'ok' : 'error',
        probeable: true,
        check: async () => {
          const r = await fetch(`/query/health/sources?scenario=${encodeURIComponent(scenario.name)}`);
          if (!r.ok) return false;
          const d = await r.json();
          const src = (d.sources ?? []).find((s: any) => s.source_type === 'graph');
          return src?.ok ?? false;
        },
      });

      // Eventhouse (KQL) — probeable
      const kqlDb = (data.workspace_items ?? []).find((w: any) => w.type === 'KQLDatabase');
      items.push({
        id: 'fabric-kql',
        label: 'Eventhouse (KQL)',
        detail: kqlDb?.displayName ?? data.kql_db_name ?? 'unknown',
        status: data.kql_ready ? 'ok' : 'error',
        probeable: true,
        check: async () => {
          const r = await fetch(`/query/health/sources?scenario=${encodeURIComponent(scenario.name)}`);
          if (!r.ok) return false;
          const d = await r.json();
          const src = (d.sources ?? []).find((s: any) => s.source_type === 'telemetry');
          return src?.ok ?? false;
        },
      });

      // Lakehouse — display-only
      const lakehouse = (data.workspace_items ?? []).find((w: any) => w.type === 'Lakehouse');
      if (lakehouse) {
        items.push({
          id: 'fabric-lakehouse',
          label: 'Lakehouse',
          detail: lakehouse.displayName,
          status: 'ok',
          probeable: false,
        });
      }

      // Ontology — display-only (same GraphModel item)
      if (graphModel) {
        items.push({
          id: 'fabric-ontology',
          label: 'Ontology',
          detail: graphModel.displayName,
          status: data.graph_model_id ? 'ok' : 'idle',
          probeable: false,
        });
      }

      updateCategory('fabric', c => ({ ...c, items, rediscovering: false }));
    } catch (err) {
      updateCategory('fabric', c => ({ ...c, rediscovering: false }));
    }
  }, [updateCategory, scenario.name]);

  const discoverAgents = useCallback(async () => {
    updateCategory('agents', c => ({ ...c, rediscovering: true }));
    try {
      const res = await fetch('/api/agents/rediscover', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const agents = data.agents ?? [];

      const items: TreeItem[] = agents.map((agent: any) => {
        const children: { label: string }[] = [];
        if (agent.tools?.length) {
          children.push(...agent.tools.map((t: any) => ({
            label: `${t.type === 'openapi' ? 'OpenAPI' : t.type === 'azure_ai_search' ? 'AI Search' : t.type}: ${t.spec_template ?? t.index_key ?? ''}`,
          })));
        }
        if (agent.connected_agents?.length) {
          children.push({ label: `delegates to: ${agent.connected_agents.join(', ')}` });
        }
        return {
          id: `agent-${agent.id}`,
          label: agent.name + (agent.is_orchestrator ? ' ⬡' : ''),
          detail: agent.is_orchestrator ? 'Orchestrator' : agent.role,
          status: agent.status === 'provisioned' ? 'ok' : agent.status === 'error' ? 'error' : 'idle',
          probeable: true,
          check: async () => agent.status === 'provisioned',
          children,
        };
      });

      updateCategory('agents', c => ({ ...c, items, rediscovering: false }));
    } catch (err) {
      updateCategory('agents', c => ({ ...c, rediscovering: false }));
    }
  }, [updateCategory]);

  const discoverModels = useCallback(async () => {
    try {
      const res = await fetch('/api/services/models');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const items: TreeItem[] = (data.models ?? []).map((m: any) => ({
        id: `model-${m.name}`,
        label: m.name,
        detail: m.type === 'llm' ? 'LLM deployment' : 'embedding deployment',
        status: m.status === 'ready' ? 'ok' : 'error',
        probeable: true,
        check: async () => m.status === 'ready',
      }));
      updateCategory('models', c => ({ ...c, items }));
    } catch {
      // fail silently
    }
  }, [updateCategory]);

  const discoverSearchAndCosmos = useCallback(async () => {
    try {
      // Sources endpoint gives search index health
      const [sourcesRes, healthRes] = await Promise.all([
        fetch(`/query/health/sources?scenario=${encodeURIComponent(scenario.name)}`),
        fetch('/api/services/health'),
      ]);

      // Search indexes
      if (sourcesRes.ok) {
        const sourcesData = await sourcesRes.json();
        const searchSources = (sourcesData.sources ?? []).filter((s: any) => s.source_type?.startsWith('search_indexes'));
        const searchItems: TreeItem[] = searchSources.map((s: any) => ({
          id: `search-${s.resource_name}`,
          label: s.resource_name,
          detail: s.ok ? s.detail : s.detail || 'not reachable',
          status: s.ok ? 'ok' : 'error',
          probeable: true,
          check: async () => {
            const r = await fetch(`/query/health/sources?scenario=${encodeURIComponent(scenario.name)}`);
            if (!r.ok) return false;
            const d = await r.json();
            const src = (d.sources ?? []).find((x: any) => x.resource_name === s.resource_name);
            return src?.ok ?? false;
          },
        }));
        updateCategory('search', c => ({ ...c, items: searchItems }));
      }

      // Cosmos + APIs from services/health
      if (healthRes.ok) {
        const healthData = await healthRes.json();
        const svcList = healthData.services ?? [];

        // Cosmos
        const cosmos = svcList.find((s: any) => s.name === 'Cosmos DB');
        if (cosmos) {
          updateCategory('cosmos', c => ({
            ...c,
            items: [{
              id: 'cosmos-interactions',
              label: 'interactions',
              detail: 'NoSQL database',
              status: cosmos.status === 'connected' ? 'ok' : 'error',
              probeable: true,
              check: async () => {
                const r = await fetch('/api/services/health');
                if (!r.ok) return false;
                const d = await r.json();
                return (d.services ?? []).find((x: any) => x.name === 'Cosmos DB')?.status === 'connected';
              },
            }],
          }));
        }

        // Graph Query API
        const gql = svcList.find((s: any) => s.name === 'Graph Query API');
        updateCategory('gqlapi', c => ({
          ...c,
          items: [{
            id: 'gqlapi-main',
            label: 'Graph Query API',
            detail: 'graph-query-api:8100',
            status: gql?.status === 'connected' ? 'ok' : 'error',
            probeable: true,
            check: async () => {
              const r = await fetch('/query/health');
              return r.ok;
            },
          }],
        }));

        // Main API
        updateCategory('mainapi', c => ({
          ...c,
          items: [{
            id: 'mainapi-main',
            label: 'Main API',
            detail: 'api:8000',
            status: 'idle',
            probeable: true,
            check: async () => {
              const r = await fetch('/health');
              return r.ok;
            },
          }],
        }));
      }
    } catch {
      // fail silently
    }
  }, [updateCategory, scenario.name]);

  /* ── Initialize categories ────────────────────────────────────── */
  useEffect(() => {
    setCategories([
      { id: 'fabric', label: 'Fabric', items: [], collapsed: false, hasRediscover: true, rediscovering: false },
      { id: 'agents', label: 'Foundry Agents', items: [], collapsed: false, hasRediscover: true, rediscovering: false },
      { id: 'models', label: 'Foundry Models', items: [], collapsed: false, hasRediscover: false, rediscovering: false },
      { id: 'search', label: 'Search Indexes', items: [], collapsed: false, hasRediscover: false, rediscovering: false },
      { id: 'cosmos', label: 'Cosmos DB', items: [], collapsed: false, hasRediscover: false, rediscovering: false },
      { id: 'gqlapi', label: '', items: [], collapsed: false, hasRediscover: false, rediscovering: false },
      { id: 'mainapi', label: '', items: [], collapsed: false, hasRediscover: false, rediscovering: false },
    ]);
  }, []);

  /* ── Full discovery + check all ───────────────────────────────── */
  const runDiscoveryAndCheckAll = useCallback(async () => {
    setCheckingAll(true);
    // Discovery pass — parallel
    await Promise.all([
      discoverFabric(),
      discoverAgents(),
      discoverModels(),
      discoverSearchAndCosmos(),
    ]);

    // Check all probeable items that are still idle
    setCategories(prev => {
      const updated = prev.map(c => ({
        ...c,
        items: c.items.map(item => {
          if (item.probeable && item.check && item.status === 'idle') {
            // Trigger check in background
            const itemId = item.id;
            const catId = c.id;
            item.check().then(ok => {
              setCategories(p => p.map(cc =>
                cc.id === catId
                  ? { ...cc, items: cc.items.map(ii => ii.id === itemId ? { ...ii, status: ok ? 'ok' : 'error' } : ii) }
                  : cc
              ));
            }).catch(() => {
              setCategories(p => p.map(cc =>
                cc.id === catId
                  ? { ...cc, items: cc.items.map(ii => ii.id === itemId ? { ...ii, status: 'error' } : ii) }
                  : cc
              ));
            });
            return { ...item, status: 'checking' as ItemStatus };
          }
          return item;
        }),
      }));
      return updated;
    });

    setCheckingAll(false);
  }, [discoverFabric, discoverAgents, discoverModels, discoverSearchAndCosmos]);

  /* ── Auto-run on first open (§4i) ─────────────────────────────── */
  useEffect(() => {
    if (open && !hasAutoRun.current) {
      hasAutoRun.current = true;
      runDiscoveryAndCheckAll();
    }
  }, [open, runDiscoveryAndCheckAll]);

  /* ── Check a single item ──────────────────────────────────────── */
  const checkItem = useCallback(async (catId: string, item: TreeItem) => {
    if (!item.probeable) {
      // Display-only — re-run parent rediscover
      if (catId === 'fabric') discoverFabric();
      if (catId === 'agents') discoverAgents();
      return;
    }
    if (!item.check) return;

    updateItem(catId, item.id, i => ({ ...i, status: 'checking', elapsed: 0 }));
    const t0 = Date.now();
    const timer = setInterval(() => {
      updateItem(catId, item.id, i => ({ ...i, elapsed: Math.round((Date.now() - t0) / 1000) }));
    }, 500);

    try {
      const ok = await item.check();
      clearInterval(timer);
      updateItem(catId, item.id, i => ({ ...i, status: ok ? 'ok' : 'error', elapsed: Math.round((Date.now() - t0) / 1000) }));
    } catch {
      clearInterval(timer);
      updateItem(catId, item.id, i => ({ ...i, status: 'error', elapsed: Math.round((Date.now() - t0) / 1000) }));
    }
  }, [updateItem, discoverFabric, discoverAgents]);

  /* ── Check All ────────────────────────────────────────────────── */
  const checkAll = useCallback(async () => {
    setCheckingAll(true);
    const promises: Promise<void>[] = [];
    for (const cat of categories) {
      for (const item of cat.items) {
        if (item.probeable && item.check) {
          promises.push(checkItem(cat.id, item));
        }
      }
    }
    await Promise.all(promises);
    setCheckingAll(false);
  }, [categories, checkItem]);

  /* ── Toggle collapse ──────────────────────────────────────────── */
  const toggleCollapse = useCallback((catId: string) => {
    updateCategory(catId, c => ({ ...c, collapsed: !c.collapsed }));
  }, [updateCategory]);

  /* ── Render ───────────────────────────────────────────────────── */
  if (!open) return null;

  // Compute overall status
  const allItems = categories.flatMap(c => c.items);
  const overallStatus = worstStatus(allItems);

  return (
    <>
      {/* Overlay backdrop */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />

      <div
        ref={ref}
        className="absolute top-full right-0 mt-1 w-[420px] max-h-[80vh] overflow-y-auto
                   bg-neutral-bg2 border border-border rounded-lg shadow-2xl z-50"
      >
        {/* Panel header */}
        <div className="sticky top-0 bg-neutral-bg2 border-b border-border px-4 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-text-primary">Services</span>
            <span className={statusDot(overallStatus, 'h-2 w-2')} />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={checkAll}
              disabled={checkingAll}
              className="text-[10px] px-2 py-0.5 rounded border border-border
                         text-text-muted hover:text-text-primary hover:bg-neutral-bg3
                         transition-colors disabled:opacity-50"
            >
              {checkingAll ? '⏳ Checking…' : '▶ Check All'}
            </button>
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-sm transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Tree body */}
        <div className="px-3 py-2 space-y-1">
          {categories.map(cat => {
            // Skip empty standalone categories (gqlapi, mainapi render as top-level items)
            if (!cat.label && cat.items.length === 0) return null;

            // Top-level standalone items (no category header)
            if (!cat.label && cat.items.length > 0) {
              return cat.items.map(item => (
                <ItemRow key={item.id} item={item} indent={0} onClick={() => checkItem(cat.id, item)} />
              ));
            }

            const catStatus = worstStatus(cat.items);

            return (
              <div key={cat.id}>
                {/* Category header */}
                <div
                  className="flex items-center justify-between py-1.5 cursor-pointer select-none
                             hover:bg-neutral-bg3 rounded px-1 -mx-1"
                >
                  <div
                    className="flex items-center gap-1.5 flex-1 min-w-0"
                    onClick={() => toggleCollapse(cat.id)}
                  >
                    <span className="text-[10px] text-text-muted">{cat.collapsed ? '▶' : '▼'}</span>
                    <span className="text-xs font-medium text-text-primary truncate">{cat.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {cat.hasRediscover && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (cat.id === 'fabric') discoverFabric();
                          if (cat.id === 'agents') discoverAgents();
                        }}
                        disabled={cat.rediscovering}
                        className="text-[10px] px-1.5 py-0.5 rounded border border-border
                                   text-text-muted hover:text-text-primary hover:bg-neutral-bg3
                                   transition-colors disabled:opacity-50"
                        title="Rediscover resources"
                      >
                        {cat.rediscovering ? '⏳' : '🔄'}
                      </button>
                    )}
                    <span className={statusDot(catStatus, 'h-1.5 w-1.5')} />
                  </div>
                </div>

                {/* Items */}
                {!cat.collapsed && (
                  <div className="ml-3 space-y-0.5">
                    {cat.items.length === 0 && (
                      <div className="text-[10px] text-text-muted italic py-1 pl-3">
                        No items discovered yet
                      </div>
                    )}
                    {cat.items.map(item => (
                      <div key={item.id}>
                        <ItemRow item={item} indent={1} onClick={() => checkItem(cat.id, item)} />
                        {/* Sub-items (tools, delegates) */}
                        {item.children?.map((child, idx) => (
                          <div key={idx} className="flex items-center gap-1.5 py-0.5 pl-8">
                            <span className="text-[10px] text-text-muted">↳</span>
                            <span className="text-[10px] text-text-muted truncate">{child.label}</span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  ItemRow                                                            */
/* ------------------------------------------------------------------ */

function ItemRow({ item, indent, onClick }: { item: TreeItem; indent: number; onClick: () => void }) {
  return (
    <div
      className={`flex items-center justify-between py-1 rounded cursor-pointer
                  hover:bg-neutral-bg3 transition-colors
                  ${indent === 0 ? 'px-1 -mx-1' : 'px-1'}`}
      onClick={onClick}
      title={item.probeable ? 'Click to health-check' : 'Display-only — click to rediscover'}
    >
      <div className="flex items-center gap-1.5 min-w-0 flex-1">
        <span className="text-[10px] text-text-muted flex-shrink-0">
          {item.probeable ? '●' : '○'}
        </span>
        <span className="text-xs text-text-primary truncate">{item.label}</span>
        {item.detail && (
          <span className="text-[10px] text-text-muted truncate">— {item.detail}</span>
        )}
      </div>
      <div className="flex items-center gap-1 flex-shrink-0 ml-2">
        {item.status === 'checking' && item.elapsed !== undefined && (
          <span className="text-[10px] text-status-warning font-mono">{item.elapsed}s</span>
        )}
        <span className={statusDot(item.status, 'h-1.5 w-1.5')} />
      </div>
    </div>
  );
}
