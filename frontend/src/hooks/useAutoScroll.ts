import { useState, useEffect, useCallback, useRef } from 'react';
import type { ChatMessage, ThinkingState } from '../types';

/**
 * Auto-scroll hook for the chat thread.
 *
 * Targets the chat scroll container (the overflow-y-auto div wrapping ChatPanel).
 * Returns a ref to attach to that container.
 */
export function useAutoScroll(messages: ChatMessage[], currentThinking: ThinkingState | null) {
  const [isNearBottom, setIsNearBottom] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  // Track if user is near the bottom of the scroll container
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handleScroll = () => {
      const threshold = 200;
      const scrollBottom = el.scrollTop + el.clientHeight;
      setIsNearBottom(el.scrollHeight - scrollBottom < threshold);
    };
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  // Auto-scroll when new messages arrive (unless user has scrolled up)
  useEffect(() => {
    if (isNearBottom) {
      scrollToBottom();
    }
  }, [messages, currentThinking, isNearBottom, scrollToBottom]);

  return { isNearBottom, scrollToBottom, scrollRef };
}
