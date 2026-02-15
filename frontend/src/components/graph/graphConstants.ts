export const NODE_COLORS: Record<string, string> = {
  CoreRouter:     '#38BDF8', // sky-400
  AggSwitch:      '#FB923C', // orange-400
  BaseStation:    '#A78BFA', // violet-400
  TransportLink:  '#3B82F6', // blue-500
  MPLSPath:       '#C084FC', // purple-400
  Service:        '#CA8A04', // yellow-600
  SLAPolicy:      '#FB7185', // rose-400
  BGPSession:     '#F472B6', // pink-400
};

export const COLOR_PALETTE = [
  '#38BDF8', '#FB923C', '#A78BFA', '#3B82F6',
  '#C084FC', '#CA8A04', '#FB7185', '#F472B6',
  '#10B981', '#EF4444', '#6366F1', '#FBBF24',
];

export const NODE_SIZES: Record<string, number> = {
  CoreRouter:     10,  // largest — central hub
  AggSwitch:      7,
  BaseStation:    5,
  TransportLink:  7,
  MPLSPath:       6,
  Service:        8,   // important business context
  SLAPolicy:      6,
  BGPSession:     5,
};
