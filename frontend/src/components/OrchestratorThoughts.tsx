import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
    reasoning: string;
    expanded?: boolean;
    onToggle?: () => void;
}

export function OrchestratorThoughts({ reasoning, expanded: controlledExpanded, onToggle }: Props) {
    const [localExpanded, setLocalExpanded] = useState(false);
    const expanded = controlledExpanded ?? localExpanded;
    const toggleExpanded = onToggle ?? (() => setLocalExpanded((v) => !v));

    if (!reasoning) return null;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const motionProps = reducedMotion
        ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: 0.15 } }
        : { initial: { height: 0, opacity: 0 }, animate: { height: 'auto' as const, opacity: 1 }, exit: { height: 0, opacity: 0 }, transition: { duration: 0.2 } };

    return (
        <button
            className="glass-card w-full text-left mb-0 cursor-pointer
                       border-brand/15 bg-brand/[0.03]
                       hover:border-brand/25 hover:bg-brand/[0.06]
                       focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1
                       transition-all"
            onClick={() => toggleExpanded()}
            aria-expanded={expanded}
            aria-label="Orchestrator reasoning for this step"
        >
            {/* Header — always visible */}
            <div className="flex items-center justify-between px-3 py-1.5">
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-brand/60">◇</span>
                    <span className="text-[11px] font-medium text-text-muted">
                        Orchestrator Thoughts{expanded ? '' : '...'}
                    </span>
                </div>
                <span className="text-[10px] text-text-muted">
                    {expanded ? '▾' : '▸'}
                </span>
            </div>

            {/* Expanded content */}
            <AnimatePresence>
                {expanded && (
                    <motion.div
                        {...motionProps}
                        className="overflow-hidden"
                    >
                        <div className="px-3 pb-2 pt-0.5">
                            <p className="text-[11px] text-text-secondary leading-relaxed italic">
                                "{reasoning}"
                            </p>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </button>
    );
}
