import { useState, useEffect, useCallback } from 'react';
import type { ChatMessage, ThinkingState } from '../types';

/**
 * Auto-scroll hook for the chat thread.
 *
 * Uses window-level scroll (not panel scroll). Automatically scrolls to
 * the bottom of the page when new messages arrive, unless the user has
 * scrolled up. Provides a `isNearBottom` flag and `scrollToBottom` function
 * for a "scroll to bottom" FAB.
 */
export function useAutoScroll(messages: ChatMessage[], currentThinking: ThinkingState | null) {
  const [isNearBottom, setIsNearBottom] = useState(true);

  const scrollToBottom = useCallback(() => {
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: 'smooth',
    });
  }, []);

  // Track if user is near the bottom
  useEffect(() => {
    const handleScroll = () => {
      const threshold = 200;
      const scrollBottom = window.innerHeight + window.scrollY;
      const docHeight = document.documentElement.scrollHeight;
      setIsNearBottom(docHeight - scrollBottom < threshold);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Auto-scroll when new messages arrive (unless user has scrolled up)
  useEffect(() => {
    if (isNearBottom) {
      scrollToBottom();
    }
  }, [messages, currentThinking, isNearBottom, scrollToBottom]);

  return { isNearBottom, scrollToBottom };
}
